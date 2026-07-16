#Requires AutoHotkey v2.0
#SingleInstance Force
; Auto-translucent windows while dragging (or resizing) via native title-bar move.
; No modifier key: hooks the OS move/size loop, so grabbing the title bar and
; dragging fades the window; releasing restores full opacity.
;
; Canonical copy lives in ag-scripts (windows-setup-scripts/configs/drag-translucency/).
; Deployed to %LOCALAPPDATA%\drag-translucency\ and autostarted at login via a
; Startup-folder shortcut created by modules/drag-translucency.ps1.

DragOpacity := 176  ; 0-255 opacity while dragging (176 ~= 69%); tweak to taste

Persistent()  ; a DllCall hook alone is not persistent; without this the script
              ; runs to the end of the auto-execute section and exits, tearing
              ; down the WinEvent hook immediately.

EVENT_MOVESIZESTART := 0x000A
EVENT_MOVESIZEEND   := 0x000B
FLAGS := 0x0000 | 0x0002  ; WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS

cb := CallbackCreate(WinEventProc, , 7)
DllCall("SetWinEventHook", "UInt", EVENT_MOVESIZESTART, "UInt", EVENT_MOVESIZEEND
    , "Ptr", 0, "Ptr", cb, "UInt", 0, "UInt", 0, "UInt", FLAGS, "Ptr")

WinEventProc(hHook, event, hwnd, idObject, idChild, idThread, dwEventTime) {
    global DragOpacity, EVENT_MOVESIZESTART
    if (idObject != 0 || !hwnd)   ; OBJID_WINDOW only; ignore child/non-window events
        return
    try {
        if (event = EVENT_MOVESIZESTART)
            WinSetTransparent(DragOpacity, hwnd)
        else
            WinSetTransparent("Off", hwnd)  ; fully opaque on release
    }
}
