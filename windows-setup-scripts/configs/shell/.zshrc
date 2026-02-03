export TERM=xterm-256color

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

# Lines configured by zsh-newuser-install
HISTFILE=~/.histfile
HISTSIZE=1000
SAVEHIST=1000
unsetopt beep
bindkey -e
# End of lines configured by zsh-newuser-install
# The following lines were added by compinstall
zstyle :compinstall filename "$HOME/.zshrc"

# Neovim
export PATH="/c/Program Files/Neovim/bin:$PATH"
alias vi=nvim
alias vim=nvim
alias dir="/bin/ls --color -al"
alias ls="/bin/ls --color -al"

autoload -Uz compinit
compinit
# End of lines added by compinstall
# Oh My Posh prompt with transient prompt
export PATH="$HOME/AppData/Local/Microsoft/WindowsApps:$PATH"
eval "$(oh-my-posh.exe init zsh --config ~/.config/oh-my-posh/powerlevel10k_rainbow.omp.json)"
eval "$(atuin init zsh)"
# Use Windows OpenSSH (works with Windows ssh-agent service)
alias ssh='/c/Windows/System32/OpenSSH/ssh.exe'
alias ssh-add='/c/Windows/System32/OpenSSH/ssh-add.exe'

export PATH=/c/miniforge3:/c/miniforge3/Scripts:$PATH

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
if [ -f '/c/miniforge3/Scripts/conda.exe' ]; then
    eval "$('/c/miniforge3/Scripts/conda.exe' 'shell.zsh' 'hook')"
fi
# <<< conda initialize <<<

