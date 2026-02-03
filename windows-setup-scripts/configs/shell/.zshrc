export TERM=xterm-256color

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

# History
HISTFILE=~/.histfile
HISTSIZE=1000
SAVEHIST=1000
unsetopt beep
bindkey -e

# Completion
zstyle :compinstall filename "$HOME/.zshrc"
autoload -Uz compinit
compinit

# Add Windows paths
export PATH="$HOME/AppData/Local/Microsoft/WinGet/Links:$PATH"
export PATH="$HOME/AppData/Local/Microsoft/WindowsApps:$PATH"
export PATH="/c/Program Files/Neovim/bin:$PATH"
export PATH="/c/Go/bin:$PATH"
export PATH="/c/miniforge3:/c/miniforge3/Scripts:$PATH"

# Aliases
alias vi=nvim
alias vim=nvim
alias dir="/bin/ls --color -al"
alias ls="/bin/ls --color -al"

# Use Windows OpenSSH (works with Windows ssh-agent service)
alias ssh='/c/Windows/System32/OpenSSH/ssh.exe'
alias ssh-add='/c/Windows/System32/OpenSSH/ssh-add.exe'

# Oh My Posh prompt
if command -v oh-my-posh.exe &> /dev/null; then
    eval "$(oh-my-posh.exe init zsh --config ~/.config/oh-my-posh/powerlevel10k_rainbow.omp.json)"
fi

# Atuin shell history (if available)
if command -v atuin &> /dev/null; then
    eval "$(atuin init zsh)"
fi

# Conda initialize
if [ -f '/c/miniforge3/Scripts/conda.exe' ]; then
    eval "$('/c/miniforge3/Scripts/conda.exe' 'shell.zsh' 'hook')"
fi

