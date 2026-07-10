"""What is a pane's shell running? (OS process-table check.)

herdr's `pane process-info` on Windows reports only the pane's *shell*, not the
program launched inside it (a child of that shell), so it cannot distinguish a
bare shell from one running yazi/lazygit/etc. Label-driven restore needs that
distinction to avoid relaunching a program that is already running.

Rather than trust herdr's foreground view, this inspects the OS process table and
returns the shell's child image names. It is stateless — no snapshot or saved
terminal ids — so label restore stays purely declarative and is correct under
every invocation path.

Callers match against a *specific* program name rather than "has any child": a
plain prompt renderer (oh-my-posh / starship / git) briefly appears as a child of
an idle shell, so "any child == busy" would wrongly skip a legitimate restore.
Matching the target program name ignores those transients.

`shell_child_names` returns a normalized name set (lowercased, exe-suffix
stripped) when it can determine the answer, or None when the platform isn't
supported, so the caller can fall back to herdr's foreground view (reliable
everywhere except the Windows build this works around).
"""

from __future__ import annotations

import sys

from whitelist import normalize_name


def _norm(name: str) -> str:
    return normalize_name(name).lower()


def shell_child_names(shell_pid: int | None) -> set[str] | None:
    """Normalized image names of `shell_pid`'s child processes, or None if it
    can't be determined on this platform (caller should fall back)."""
    if not shell_pid or shell_pid <= 0:
        return None
    if sys.platform.startswith("win"):
        return _win_child_names(int(shell_pid))
    if sys.platform.startswith("linux"):
        return _linux_child_names(int(shell_pid))
    return None  # macOS / other: no cheap stdlib way; fall back to herdr's view


def _linux_child_names(shell_pid: int) -> set[str] | None:
    # The kernel exposes a pid's children directly; cheaper and more robust than
    # scanning every /proc/<pid>/stat for a matching ppid.
    try:
        with open(f"/proc/{shell_pid}/task/{shell_pid}/children") as fh:
            child_pids = fh.read().split()
    except OSError:
        return None
    names: set[str] = set()
    for pid in child_pids:
        try:
            with open(f"/proc/{pid}/comm") as fh:
                names.add(_norm(fh.read().strip()))
        except OSError:
            continue
    return names


def _win_child_names(shell_pid: int) -> set[str] | None:
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    try:
        k32 = ctypes.windll.kernel32
    except (AttributeError, OSError):
        return None
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return None
    names: set[str] = set()
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not k32.Process32First(snap, ctypes.byref(entry)):
            return None
        while True:
            if entry.th32ParentProcessID == shell_pid:
                names.add(_norm(entry.szExeFile.decode("mbcs", "replace")))
            if not k32.Process32Next(snap, ctypes.byref(entry)):
                break
    finally:
        k32.CloseHandle(snap)
    return names
