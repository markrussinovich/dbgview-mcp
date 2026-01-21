/*
 * dbgcapture.c - Headless Win32 debug output capture
 * 
 * Captures OutputDebugString output and writes JSON lines to stdout.
 * Based on DebugView by Mark Russinovich.
 * 
 * Usage: dbgcapture.exe [--global]
 *   --global: Capture from all sessions (requires admin)
 *   Default: Capture from current session only
 */

#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sddl.h>
#include <io.h>
#include <fcntl.h>

#define BUFFER_SIZE 4096
#define MAX_OUTPUT_LEN 4096

// Shared memory objects for Win32 debug capture
static HANDLE hDBWIN_BUFFER = NULL;
static HANDLE hDBWIN_DATA_READY = NULL;
static HANDLE hDBWIN_BUFFER_READY = NULL;
static HANDLE hDBWIN_MUTEX = NULL;
static char* pDebugBuffer = NULL;

static volatile BOOL g_Running = TRUE;
static ULONGLONG g_Sequence = 0;

// Console control handler
BOOL WINAPI ConsoleHandler(DWORD signal) {
    if (signal == CTRL_C_EVENT || signal == CTRL_BREAK_EVENT || signal == CTRL_CLOSE_EVENT) {
        g_Running = FALSE;
        // Signal the wait to wake up
        if (hDBWIN_DATA_READY != NULL) {
            SetEvent(hDBWIN_DATA_READY);
        }
        return TRUE;
    }
    return FALSE;
}

// Escape a string for JSON output
void JsonEscape(const char* input, char* output, size_t outputSize) {
    size_t j = 0;
    for (size_t i = 0; input[i] && j < outputSize - 2; i++) {
        char c = input[i];
        switch (c) {
            case '"':  if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = '"'; } break;
            case '\\': if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = '\\'; } break;
            case '\b': if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = 'b'; } break;
            case '\f': if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = 'f'; } break;
            case '\n': if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = 'n'; } break;
            case '\r': if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = 'r'; } break;
            case '\t': if (j < outputSize - 3) { output[j++] = '\\'; output[j++] = 't'; } break;
            default:
                if ((unsigned char)c >= 32) {
                    output[j++] = c;
                }
                break;
        }
    }
    output[j] = '\0';
}

// Initialize Win32 debug capture
BOOL InitializeCapture(BOOL global) {
    SECURITY_ATTRIBUTES sa;
    PSECURITY_DESCRIPTOR sddlSd = NULL;
    char objectName[MAX_PATH];
    const char* prefix = global ? "Global\\" : "";
    
    // Security descriptor that allows access from all processes
    const char* sddlSecurity = 
        "D:(A;;GRGWGX;;;WD)(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGWGX;;;AN)(A;;GRGWGX;;;RC)"
        "(A;;GRGWGX;;;S-1-15-2-1)S:(ML;;NW;;;LW)";

    ConvertStringSecurityDescriptorToSecurityDescriptorA(
        sddlSecurity, SDDL_REVISION_1, &sddlSd, NULL);

    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = sddlSd;

    // Create/open the mutex
    sprintf(objectName, "%sDBWinMutex", prefix);
    hDBWIN_MUTEX = OpenMutexA(SYNCHRONIZE, FALSE, objectName);
    if (!hDBWIN_MUTEX) {
        hDBWIN_MUTEX = CreateMutexA(&sa, FALSE, objectName);
    }

    // Create/open the shared memory buffer
    sprintf(objectName, "%sDBWIN_BUFFER", prefix);
    hDBWIN_BUFFER = CreateFileMappingA(INVALID_HANDLE_VALUE, &sa, PAGE_READWRITE, 0, BUFFER_SIZE, objectName);
    if (!hDBWIN_BUFFER) {
        fprintf(stderr, "{\"error\": \"Failed to create DBWIN_BUFFER: %lu\"}\n", GetLastError());
        if (sddlSd) LocalFree(sddlSd);
        return FALSE;
    }

    // Map the buffer
    pDebugBuffer = (char*)MapViewOfFile(hDBWIN_BUFFER, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, BUFFER_SIZE);
    if (!pDebugBuffer) {
        fprintf(stderr, "{\"error\": \"Failed to map DBWIN_BUFFER: %lu\"}\n", GetLastError());
        CloseHandle(hDBWIN_BUFFER);
        if (sddlSd) LocalFree(sddlSd);
        return FALSE;
    }

    // Create/open DATA_READY event
    sprintf(objectName, "%sDBWIN_DATA_READY", prefix);
    hDBWIN_DATA_READY = CreateEventA(&sa, FALSE, FALSE, objectName);
    if (!hDBWIN_DATA_READY) {
        fprintf(stderr, "{\"error\": \"Failed to create DBWIN_DATA_READY: %lu\"}\n", GetLastError());
        UnmapViewOfFile(pDebugBuffer);
        CloseHandle(hDBWIN_BUFFER);
        if (sddlSd) LocalFree(sddlSd);
        return FALSE;
    }

    // Create/open BUFFER_READY event
    sprintf(objectName, "%sDBWIN_BUFFER_READY", prefix);
    hDBWIN_BUFFER_READY = CreateEventA(&sa, FALSE, FALSE, objectName);
    if (!hDBWIN_BUFFER_READY) {
        fprintf(stderr, "{\"error\": \"Failed to create DBWIN_BUFFER_READY: %lu\"}\n", GetLastError());
        CloseHandle(hDBWIN_DATA_READY);
        UnmapViewOfFile(pDebugBuffer);
        CloseHandle(hDBWIN_BUFFER);
        if (sddlSd) LocalFree(sddlSd);
        return FALSE;
    }

    if (sddlSd) LocalFree(sddlSd);

    // Signal that buffer is ready for first write
    SetEvent(hDBWIN_BUFFER_READY);
    
    return TRUE;
}

// Cleanup resources
void UninitializeCapture(void) {
    if (pDebugBuffer) {
        UnmapViewOfFile(pDebugBuffer);
        pDebugBuffer = NULL;
    }
    if (hDBWIN_DATA_READY) {
        CloseHandle(hDBWIN_DATA_READY);
        hDBWIN_DATA_READY = NULL;
    }
    if (hDBWIN_BUFFER_READY) {
        CloseHandle(hDBWIN_BUFFER_READY);
        hDBWIN_BUFFER_READY = NULL;
    }
    if (hDBWIN_BUFFER) {
        CloseHandle(hDBWIN_BUFFER);
        hDBWIN_BUFFER = NULL;
    }
    if (hDBWIN_MUTEX) {
        CloseHandle(hDBWIN_MUTEX);
        hDBWIN_MUTEX = NULL;
    }
}

// Main capture loop
void CaptureLoop(void) {
    char escapedText[MAX_OUTPUT_LEN * 2];
    DWORD pid;
    char* text;
    SYSTEMTIME st;
    FILETIME ft;
    ULARGE_INTEGER uli;

    fprintf(stderr, "{\"status\": \"started\"}\n");
    fflush(stderr);

    while (g_Running) {
        // Wait for debug output
        DWORD waitResult = WaitForSingleObject(hDBWIN_DATA_READY, 1000);
        
        if (!g_Running) break;
        
        if (waitResult == WAIT_OBJECT_0) {
            // Extract PID (first 4 bytes) and text (rest)
            pid = *(DWORD*)pDebugBuffer;
            text = pDebugBuffer + sizeof(DWORD);
            
            // Get current time
            GetSystemTime(&st);
            SystemTimeToFileTime(&st, &ft);
            uli.LowPart = ft.dwLowDateTime;
            uli.HighPart = ft.dwHighDateTime;
            
            // Escape text for JSON
            JsonEscape(text, escapedText, sizeof(escapedText));
            
            // Output JSON line
            printf("{\"seq\":%llu,\"time\":%llu,\"pid\":%lu,\"text\":\"%s\"}\n",
                   g_Sequence++, uli.QuadPart, pid, escapedText);
            fflush(stdout);
            
            // Signal ready for next output
            SetEvent(hDBWIN_BUFFER_READY);
        }
        // WAIT_TIMEOUT: just continue loop
    }

    fprintf(stderr, "{\"status\": \"stopped\"}\n");
    fflush(stderr);
}

int main(int argc, char* argv[]) {
    BOOL global = FALSE;

    // Parse arguments
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--global") == 0 || strcmp(argv[i], "-g") == 0) {
            global = TRUE;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            printf("Usage: dbgcapture.exe [--global]\n");
            printf("  --global, -g  Capture from all sessions (requires admin)\n");
            printf("  --help, -h    Show this help\n");
            return 0;
        }
    }

    // Set up console handler for graceful shutdown
    SetConsoleCtrlHandler(ConsoleHandler, TRUE);

    // Set stdout to binary mode to avoid CR/LF translation issues
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);

    // Initialize capture
    if (!InitializeCapture(global)) {
        return 1;
    }

    // Run capture loop
    CaptureLoop();

    // Cleanup
    UninitializeCapture();

    return 0;
}
