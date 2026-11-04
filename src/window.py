import ctypes
import os
import sys
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    )
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
else:
    _user32 = _kernel32 = None


def foreground_info():
    """Return (exe name, window title) of the foreground window, lower-cased."""
    if _user32 is None:
        return "", ""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    title_buf = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, title_buf, 512)
    exe = ""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                exe = os.path.basename(buf.value)
        finally:
            _kernel32.CloseHandle(handle)
    return exe.lower(), title_buf.value.strip().lower()


def game_in_foreground():
    try:
        exe, title = foreground_info()
    except Exception:
        return True
    if exe:
        return exe.startswith("fortnite")
    return title.startswith("fortnite")
