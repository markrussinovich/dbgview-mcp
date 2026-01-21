# Makefile for dbgcapture.exe

CC = cl
CFLAGS = /nologo /O2 /W3 /D_CRT_SECURE_NO_WARNINGS
LDFLAGS = /nologo
LIBS = advapi32.lib

TARGET = dbgcapture.exe

all: $(TARGET)

$(TARGET): dbgcapture.c
	$(CC) $(CFLAGS) dbgcapture.c /Fe:$(TARGET) /link $(LDFLAGS) $(LIBS)

clean:
	del /q *.obj *.exe 2>nul

.PHONY: all clean
