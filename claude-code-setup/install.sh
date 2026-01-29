#!/bin/bash

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for npm
if ! command_exists npm; then
    echo "Error: npm is not installed. Please install Node.js and npm first."
    exit 1
fi

echo "Installing @anthropic-ai/claude-code globally..."
npm install -g @anthropic-ai/claude-code

if [ $? -eq 0 ]; then
    echo "Successfully installed claude-code."
    echo "You can now run 'claude' to start."
else
    echo "Failed to install claude-code."
    exit 1
fi
