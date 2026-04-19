# --- vscode-launcher tmux hook (BEGIN) ---
# Switches the current shell's tmux client to the session mapped for the
# current workspace. MUST run BEFORE any tmux auto-attach in zshrc, because:
#   (a) VSCODE_INJECTION / VSCODE_PID are stripped when tmux attaches (they're
#       not in tmux's default update-environment list), and
#   (b) tmux rewrites TERM_PROGRAM to "tmux", defeating our VSCode detection.
# install.sh places this block BEFORE the first `tmux new-session|attach` line
# in ~/.zshrc (or at end of file if no such line is detected).
if [[ ( -n "${VSCODE_INJECTION:-}" || -n "${VSCODE_PID:-}" || "${TERM_PROGRAM:-}" == "vscode" ) ]] \
   && command -v vscl-tmux-lookup >/dev/null 2>&1; then
    _vscl_session=$(vscl-tmux-lookup "$PWD" 2>/dev/null)
    if [[ -n "$_vscl_session" ]]; then
        if [[ -z "${TMUX:-}" ]]; then
            if tmux attach -t "$_vscl_session" 2>/dev/null; then
                unset _vscl_session
                return
            fi
        else
            tmux switch-client -t "$_vscl_session" 2>/dev/null
        fi
    fi
    unset _vscl_session
fi
# --- vscode-launcher tmux hook (END) ---
