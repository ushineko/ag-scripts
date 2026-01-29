#!/bin/bash

echo "Uninstalling @anthropic-ai/claude-code globally..."
npm uninstall -g @anthropic-ai/claude-code

if [ $? -eq 0 ]; then
    echo "Successfully uninstalled claude-code."
else
    echo "Failed to uninstall claude-code."
    exit 1
fi
