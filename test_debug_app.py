"""
Debug Output Test Application

A configurable test application that produces Windows debug output (OutputDebugString)
for testing the dbgcapture MCP server capabilities.

Usage:
    python test_debug_app.py [options]

Examples:
    # Basic: Send 10 messages with [TEST] tag
    python test_debug_app.py
    
    # Custom tag and count
    python test_debug_app.py --tag ERROR --count 50 --interval 0.1
    
    # Multiple tags for filter testing
    python test_debug_app.py --multi-tag
    
    # Continuous mode for real-time monitoring
    python test_debug_app.py --continuous --interval 1.0
    
    # Burst mode for stress testing
    python test_debug_app.py --burst 1000
"""

import argparse
import ctypes
import random
import string
import sys
import time
from datetime import datetime


def output_debug_string(message: str):
    """Send a debug string via Windows OutputDebugString API."""
    ctypes.windll.kernel32.OutputDebugStringA(message.encode('ascii', errors='replace') + b'\0')


def generate_random_data(length: int = 10) -> str:
    """Generate random alphanumeric data."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def run_basic_mode(args):
    """Send a fixed number of messages with a single tag."""
    print(f"Sending {args.count} messages with tag [{args.tag}]...")
    print(f"Interval: {args.interval}s")
    print()
    
    for i in range(1, args.count + 1):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        message = f"[{args.tag}] [{timestamp}] Message {i}/{args.count}: {args.message}"
        
        output_debug_string(message)
        print(f"  Sent: {message}")
        
        if i < args.count:
            time.sleep(args.interval)
    
    print(f"\nDone! Sent {args.count} messages.")


def run_multi_tag_mode(args):
    """Send messages with multiple tags for filter testing."""
    tags = ["INFO", "DEBUG", "WARN", "ERROR", "TRACE", "VERBOSE"]
    levels = {
        "ERROR": "Critical failure detected!",
        "WARN": "Warning: potential issue",
        "INFO": "Informational message",
        "DEBUG": "Debug details here",
        "TRACE": "Trace: entering function",
        "VERBOSE": "Verbose: detailed trace data"
    }
    
    print(f"Sending {args.count} messages with multiple tags: {tags}")
    print("Use MCP filters to test include/exclude patterns!")
    print()
    
    for i in range(1, args.count + 1):
        tag = random.choice(tags)
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        message = f"[{tag}] [{timestamp}] #{i}: {levels[tag]} - {generate_random_data(8)}"
        
        output_debug_string(message)
        print(f"  [{tag}] {message}")
        
        if i < args.count:
            time.sleep(args.interval)
    
    print(f"\nDone! Sent {args.count} messages across {len(tags)} tags.")
    print("\nFilter suggestions:")
    print("  - Include only errors: set_filters(include=[r'\\[ERROR\\]'])")
    print("  - Exclude verbose: set_filters(exclude=[r'\\[VERBOSE\\]', r'\\[TRACE\\]'])")


def run_continuous_mode(args):
    """Run continuously until interrupted."""
    print(f"Continuous mode - sending [{args.tag}] messages every {args.interval}s")
    print("Press Ctrl+C to stop...")
    print()
    
    count = 0
    try:
        while True:
            count += 1
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            message = f"[{args.tag}] [{timestamp}] Continuous #{count}: {args.message}"
            
            output_debug_string(message)
            print(f"  Sent #{count}: {message}")
            
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n\nStopped after {count} messages.")


def run_burst_mode(args):
    """Send a burst of messages as fast as possible."""
    burst_count = args.burst
    print(f"Burst mode - sending {burst_count} messages as fast as possible...")
    
    start = time.perf_counter()
    
    for i in range(1, burst_count + 1):
        message = f"[BURST] #{i}: {generate_random_data(20)}"
        output_debug_string(message)
    
    elapsed = time.perf_counter() - start
    rate = burst_count / elapsed if elapsed > 0 else 0
    
    print(f"Done! Sent {burst_count} messages in {elapsed:.3f}s ({rate:.0f} msg/s)")
    print("\nThis tests the ring buffer and high-throughput capture.")


def run_pattern_mode(args):
    """Send messages with specific patterns for regex testing."""
    patterns = [
        ("[APP:Main] Starting application v1.0.0", "App lifecycle"),
        ("[APP:Main] Configuration loaded from config.json", "App lifecycle"),
        ("[DB:Query] SELECT * FROM users WHERE id = 123", "Database"),
        ("[DB:Query] INSERT INTO logs (msg) VALUES ('test')", "Database"),
        ("[HTTP:Request] GET /api/users/123 HTTP/1.1", "HTTP"),
        ("[HTTP:Response] 200 OK (45ms)", "HTTP"),
        ("[PERF] Frame time: 16.7ms (60 FPS)", "Performance"),
        ("[PERF] Memory usage: 256MB / 1024MB", "Performance"),
        ("[SECURITY] Authentication successful for user 'admin'", "Security"),
        ("[SECURITY] Failed login attempt from 192.168.1.100", "Security"),
        ("[CACHE] Cache hit for key 'user:123'", "Cache"),
        ("[CACHE] Cache miss - loading from database", "Cache"),
        ("[ERROR] NullReferenceException in ProcessData()", "Error"),
        ("[ERROR] Connection timeout after 30s", "Error"),
        ("[WARN] Deprecated API usage detected", "Warning"),
        ("[WARN] Low disk space: 500MB remaining", "Warning"),
    ]
    
    print("Pattern mode - sending diverse message patterns for regex filter testing")
    print(f"Sending {len(patterns)} unique patterns, {args.count} iterations each")
    print()
    
    total = 0
    for iteration in range(args.count):
        for pattern, category in patterns:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            message = f"{pattern} @{timestamp}"
            output_debug_string(message)
            total += 1
            
            if args.verbose:
                print(f"  [{category}] {message}")
        
        if iteration < args.count - 1:
            time.sleep(args.interval)
    
    print(f"\nDone! Sent {total} messages.")
    print("\nFilter suggestions:")
    print("  - Database queries: set_filters(include=[r'\\[DB:'])")
    print("  - HTTP traffic: set_filters(include=[r'\\[HTTP:'])")
    print("  - Errors and warnings: set_filters(include=[r'\\[ERROR\\]', r'\\[WARN\\]'])")
    print("  - Exclude performance: set_filters(exclude=[r'\\[PERF\\]'])")


def run_interactive_mode(args):
    """Interactive mode - type messages to send."""
    print("Interactive mode - type messages to send as debug output")
    print(f"Messages will be prefixed with [{args.tag}]")
    print("Type 'quit' or press Ctrl+C to exit")
    print()
    
    try:
        while True:
            user_input = input(f"[{args.tag}] > ").strip()
            if user_input.lower() == 'quit':
                break
            if user_input:
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                message = f"[{args.tag}] [{timestamp}] {user_input}"
                output_debug_string(message)
                print(f"  Sent: {message}")
    except (KeyboardInterrupt, EOFError):
        pass
    
    print("\nExiting interactive mode.")


def main():
    parser = argparse.ArgumentParser(
        description="Debug Output Test Application for MCP Server Testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  default       Send a fixed number of messages with one tag
  --multi-tag   Send messages with random tags (INFO, DEBUG, WARN, ERROR, etc.)
  --continuous  Keep sending until Ctrl+C
  --burst N     Send N messages as fast as possible
  --pattern     Send diverse patterns for regex filter testing
  --interactive Type messages to send manually

Examples:
  %(prog)s --tag MYAPP --count 20 --interval 0.5
  %(prog)s --multi-tag --count 100
  %(prog)s --continuous --interval 2.0
  %(prog)s --burst 5000
  %(prog)s --pattern --count 3
  %(prog)s --interactive
        """
    )
    
    parser.add_argument("--tag", "-t", default="TEST",
                        help="Message tag/prefix (default: TEST)")
    parser.add_argument("--count", "-c", type=int, default=10,
                        help="Number of messages to send (default: 10)")
    parser.add_argument("--interval", "-i", type=float, default=0.5,
                        help="Interval between messages in seconds (default: 0.5)")
    parser.add_argument("--message", "-m", default="Test debug output message",
                        help="Custom message content")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--multi-tag", action="store_true",
                            help="Use multiple random tags for filter testing")
    mode_group.add_argument("--continuous", action="store_true",
                            help="Run continuously until interrupted")
    mode_group.add_argument("--burst", type=int, metavar="N",
                            help="Burst mode: send N messages as fast as possible")
    mode_group.add_argument("--pattern", action="store_true",
                            help="Send diverse patterns for regex testing")
    mode_group.add_argument("--interactive", action="store_true",
                            help="Interactive mode: type messages to send")
    
    args = parser.parse_args()
    
    if sys.platform != "win32":
        print("Error: This application only works on Windows.")
        sys.exit(1)
    
    print("=" * 60)
    print("Debug Output Test Application")
    print("=" * 60)
    print(f"PID: {ctypes.windll.kernel32.GetCurrentProcessId()}")
    print()
    
    if args.burst:
        run_burst_mode(args)
    elif args.multi_tag:
        run_multi_tag_mode(args)
    elif args.continuous:
        run_continuous_mode(args)
    elif args.pattern:
        run_pattern_mode(args)
    elif args.interactive:
        run_interactive_mode(args)
    else:
        run_basic_mode(args)


if __name__ == "__main__":
    main()
