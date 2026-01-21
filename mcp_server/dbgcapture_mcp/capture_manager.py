"""
Capture Manager - Manages the debug capture subprocess and ring buffer.

Spawns dbgcapture.exe, reads JSON lines from stdout, stores entries in a
ring buffer, and provides filtered views via sessions.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from collections import deque

import psutil


@dataclass
class DebugEntry:
    """A single debug output entry."""
    seq: int
    time: int  # Windows FILETIME
    pid: int
    text: str
    process_name: Optional[str] = None


@dataclass
class FilterSet:
    """Filter configuration for a session."""
    include_patterns: list[re.Pattern] = field(default_factory=list)
    exclude_patterns: list[re.Pattern] = field(default_factory=list)
    process_names: list[re.Pattern] = field(default_factory=list)
    process_pids: list[int] = field(default_factory=list)
    
    def matches(self, entry: DebugEntry) -> bool:
        """Check if an entry matches this filter set."""
        # Check process filters first
        if self.process_pids and entry.pid not in self.process_pids:
            return False
        
        if self.process_names:
            if not entry.process_name:
                return False
            name_match = any(p.search(entry.process_name) for p in self.process_names)
            if not name_match:
                return False
        
        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if pattern.search(entry.text):
                return False
        
        # Check include patterns (if any defined, at least one must match)
        if self.include_patterns:
            if not any(p.search(entry.text) for p in self.include_patterns):
                return False
        
        return True


@dataclass
class Session:
    """A capture session with its own filters and read cursor."""
    id: str
    name: str
    filters: FilterSet
    cursor: int  # Sequence number of last read entry
    created_at: float


class CaptureManager:
    """
    Singleton manager for debug output capture.
    
    Spawns a single dbgcapture.exe subprocess, buffers all output in a ring
    buffer, and provides filtered views via sessions.
    """
    
    _instance: Optional["CaptureManager"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "CaptureManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._buffer: deque[DebugEntry] = deque(maxlen=100000)  # 100K entries
        self._buffer_lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        self._sessions_lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._process_cache: dict[int, str] = {}  # PID -> process name cache
        self._cache_lock = threading.Lock()
        self._current_seq = 0
        
        # Find dbgcapture.exe
        self._capture_exe = self._find_capture_exe()
    
    def _find_capture_exe(self) -> Path:
        """Locate the dbgcapture.exe binary."""
        # Look relative to this module
        module_dir = Path(__file__).parent
        candidates = [
            # Embedded in package (pip install)
            module_dir / "dbgcapture.exe",
            # Development: sibling directory
            module_dir.parent.parent / "dbgcapture" / "dbgcapture.exe",
            # Development: repo root
            module_dir.parent.parent.parent / "dbgcapture" / "dbgcapture.exe",
            # Current directory
            Path("dbgcapture.exe"),
        ]
        
        for path in candidates:
            if path.exists():
                return path.resolve()
        
        # Default - will fail at runtime if not found
        return candidates[0].resolve()
    
    def _get_process_name(self, pid: int) -> Optional[str]:
        """Get process name for a PID, with caching."""
        with self._cache_lock:
            if pid in self._process_cache:
                return self._process_cache[pid]
        
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            with self._cache_lock:
                self._process_cache[pid] = name
            return name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
    
    def _reader_loop(self):
        """Background thread that reads from dbgcapture.exe stdout."""
        while self._running:
            process = self._process
            if process is None or process.poll() is not None:
                break
            try:
                line = self._process.stdout.readline()
                if not line:
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    entry = DebugEntry(
                        seq=data["seq"],
                        time=data["time"],
                        pid=data["pid"],
                        text=data["text"],
                        process_name=self._get_process_name(data["pid"])
                    )
                    
                    with self._buffer_lock:
                        self._buffer.append(entry)
                        self._current_seq = entry.seq
                        
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed lines
                    pass
                    
            except Exception:
                if self._running:
                    time.sleep(0.1)
    
    def start_capture(self, global_capture: bool = False) -> bool:
        """Start the capture subprocess if not already running."""
        if self._process is not None and self._process.poll() is None:
            return True  # Already running
        
        if not self._capture_exe.exists():
            raise FileNotFoundError(f"dbgcapture.exe not found at {self._capture_exe}")
        
        args = [str(self._capture_exe)]
        if global_capture:
            args.append("--global")
        
        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            
            self._running = True
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            
            return True
            
        except Exception as e:
            raise RuntimeError(f"Failed to start capture: {e}")
    
    def stop_capture(self):
        """Stop the capture subprocess."""
        self._running = False
        
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        
        if self._reader_thread:
            self._reader_thread.join(timeout=2)
            self._reader_thread = None
    
    def is_running(self) -> bool:
        """Check if capture is currently running."""
        return self._process is not None and self._process.poll() is None
    
    def create_session(self, name: Optional[str] = None) -> str:
        """Create a new capture session."""
        # Start capture if this is the first session
        if not self._sessions:
            self.start_capture()
        
        session_id = str(uuid.uuid4())[:8]
        session = Session(
            id=session_id,
            name=name or f"session-{session_id}",
            filters=FilterSet(),
            cursor=self._current_seq,
            created_at=time.time()
        )
        
        with self._sessions_lock:
            self._sessions[session_id] = session
        
        return session_id
    
    def destroy_session(self, session_id: str) -> bool:
        """Destroy a capture session."""
        with self._sessions_lock:
            if session_id not in self._sessions:
                return False
            del self._sessions[session_id]
            
            # Stop capture if no sessions left
            if not self._sessions:
                self.stop_capture()
        
        return True
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        with self._sessions_lock:
            return self._sessions.get(session_id)
    
    def set_filters(
        self,
        session_id: str,
        include: Optional[list[str]] = None,
        exclude: Optional[list[str]] = None,
        process_names: Optional[list[str]] = None,
        process_pids: Optional[list[int]] = None
    ) -> bool:
        """Set filters for a session."""
        session = self.get_session(session_id)
        if not session:
            return False
        
        filters = FilterSet()
        
        if include:
            filters.include_patterns = [re.compile(p, re.IGNORECASE) for p in include]
        
        if exclude:
            filters.exclude_patterns = [re.compile(p, re.IGNORECASE) for p in exclude]
        
        if process_names:
            filters.process_names = [re.compile(p, re.IGNORECASE) for p in process_names]
        
        if process_pids:
            filters.process_pids = process_pids
        
        session.filters = filters
        return True
    
    def get_output(
        self,
        session_id: str,
        limit: int = 100,
        since_seq: Optional[int] = None
    ) -> tuple[list[dict], int]:
        """
        Get filtered output for a session.
        
        Returns (entries, next_seq) where next_seq should be passed as since_seq
        in the next call to get new entries only.
        """
        session = self.get_session(session_id)
        if not session:
            return [], 0
        
        start_seq = since_seq if since_seq is not None else session.cursor
        results = []
        max_seq = start_seq
        
        with self._buffer_lock:
            for entry in self._buffer:
                if entry.seq <= start_seq:
                    continue
                
                if session.filters.matches(entry):
                    results.append({
                        "seq": entry.seq,
                        "time": entry.time,
                        "pid": entry.pid,
                        "process_name": entry.process_name,
                        "text": entry.text
                    })
                    
                    if len(results) >= limit:
                        max_seq = entry.seq
                        break
                
                max_seq = entry.seq
        
        # Update session cursor
        if results:
            session.cursor = results[-1]["seq"]
        elif max_seq > session.cursor:
            session.cursor = max_seq
        
        return results, session.cursor
    
    def clear_session(self, session_id: str) -> bool:
        """Reset session cursor to current position (skip all pending)."""
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.cursor = self._current_seq
        return True
    
    def get_session_status(self, session_id: str) -> Optional[dict]:
        """Get status information for a session."""
        session = self.get_session(session_id)
        if not session:
            return None
        
        # Count pending entries
        pending = 0
        with self._buffer_lock:
            for entry in self._buffer:
                if entry.seq > session.cursor:
                    if session.filters.matches(entry):
                        pending += 1
        
        return {
            "session_id": session.id,
            "name": session.name,
            "filters": {
                "include": [p.pattern for p in session.filters.include_patterns],
                "exclude": [p.pattern for p in session.filters.exclude_patterns],
                "process_names": [p.pattern for p in session.filters.process_names],
                "process_pids": session.filters.process_pids
            },
            "cursor": session.cursor,
            "pending_count": pending,
            "capture_running": self.is_running(),
            "total_buffered": len(self._buffer)
        }
    
    def list_processes(self, name_pattern: Optional[str] = None) -> list[dict]:
        """List running processes, optionally filtered by name."""
        pattern = re.compile(name_pattern, re.IGNORECASE) if name_pattern else None
        results = []
        
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                if pattern and not pattern.search(info["name"]):
                    continue
                results.append({
                    "pid": info["pid"],
                    "name": info["name"]
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return sorted(results, key=lambda x: x["name"].lower())


# Global instance
_manager: Optional[CaptureManager] = None


def get_manager() -> CaptureManager:
    """Get the global CaptureManager instance."""
    global _manager
    if _manager is None:
        _manager = CaptureManager()
    return _manager
