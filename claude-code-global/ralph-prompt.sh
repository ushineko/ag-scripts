#!/bin/bash
#
# ralph-prompt.sh - General-purpose prompt iteration loop
#
# Runs Claude Code with the same prompt N times, useful for:
# - Iterative refinement tasks
# - Multi-step implementations without specs
# - Autonomous work sessions with fixed duration
#
# Usage: ./ralph-prompt.sh "your prompt" --max-iterations=5 [options]
#
# Options:
#   --max-iterations=N  Number of iterations (required)
#   --yolo              Enable YOLO mode (skip permission prompts)
#   --no-cclean         Output raw JSON instead of formatted via cclean
#   --cwd <dir>         Run in specified directory (default: current)
#   --help, -h          Show this help message
#
# Version: 1.0.0

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
PROMPT=""
MAX_ITERATIONS=""
SKIP_PERMISSIONS=false
USE_CCLEAN=true
PROJECT_DIR=""

show_help() {
    echo "Usage: $0 <prompt> --max-iterations=<n> [options]"
    echo "       $0 <prompt> <max_iterations> [options]"
    echo ""
    echo "General-purpose prompt iteration loop for Claude Code."
    echo ""
    echo "Options:"
    echo "  --max-iterations=N  Number of iterations to run (required)"
    echo "  --yolo              Enable YOLO mode (--dangerously-skip-permissions)"
    echo "  --no-cclean         Output raw stream-json instead of formatted via cclean"
    echo "  --cwd <dir>         Run Claude in specified directory"
    echo "  --help, -h          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 'Continue working on the task' --max-iterations=5"
    echo "  $0 'Fix all lint errors' 3 --yolo"
    echo "  $0 'Implement the feature' --max-iterations=10 --cwd ~/projects/myapp"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --max-iterations=*)
            MAX_ITERATIONS="${1#*=}"
            shift
            ;;
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --yolo|--skip-permissions)
            SKIP_PERMISSIONS=true
            shift
            ;;
        --no-cclean)
            USE_CCLEAN=false
            shift
            ;;
        --cwd)
            PROJECT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            if [[ -z "$PROMPT" ]]; then
                PROMPT="$1"
            elif [[ -z "$MAX_ITERATIONS" ]]; then
                MAX_ITERATIONS="$1"
            fi
            shift
            ;;
    esac
done

# Validate required arguments
if [[ -z "$PROMPT" ]] || [[ -z "$MAX_ITERATIONS" ]]; then
    echo -e "${RED}Error: Missing required arguments${NC}"
    echo ""
    show_help
    exit 1
fi

# Validate max_iterations is a positive integer
if ! [[ "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}Error: max_iterations must be a positive integer${NC}"
    exit 1
fi

if [[ "$MAX_ITERATIONS" -lt 1 ]]; then
    echo -e "${RED}Error: max_iterations must be at least 1${NC}"
    exit 1
fi

# Check for cclean if needed
if [[ "$USE_CCLEAN" == true ]]; then
    if ! command -v cclean &> /dev/null; then
        echo -e "${RED}Error: cclean not found${NC}"
        echo ""
        echo "cclean is required for formatted output. Install options:"
        echo "  curl -fsSL https://raw.githubusercontent.com/ariel-frischer/claude-clean/main/install.sh | sh"
        echo "  cargo install claude-clean"
        echo ""
        echo "Or run with --no-cclean for raw JSON output:"
        echo "  $0 --no-cclean \"$PROMPT\" --max-iterations=$MAX_ITERATIONS"
        exit 1
    fi
fi

# Build claude arguments
CLAUDE_ARGS="-p"
if [[ "$SKIP_PERMISSIONS" == true ]]; then
    CLAUDE_ARGS="$CLAUDE_ARGS --dangerously-skip-permissions"
fi
CLAUDE_ARGS="$CLAUDE_ARGS --verbose --output-format stream-json"
if [[ -n "$PROJECT_DIR" ]]; then
    CLAUDE_ARGS="$CLAUDE_ARGS --cwd $PROJECT_DIR"
fi

# Display banner
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Ralph Prompt Iteration Loop          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Prompt: ${GREEN}${PROMPT:0:60}${PROMPT:60:+...}${NC}"
echo -e "Max iterations: ${YELLOW}$MAX_ITERATIONS${NC}"
if [[ "$SKIP_PERMISSIONS" == true ]]; then
    echo -e "${YELLOW}WARNING: YOLO mode enabled - all permission prompts bypassed${NC}"
fi
if [[ -n "$PROJECT_DIR" ]]; then
    echo -e "Working directory: ${GREEN}$PROJECT_DIR${NC}"
fi
echo -e "${BLUE}────────────────────────────────────────────${NC}"
echo ""

# Main loop
for ((i=1; i<=MAX_ITERATIONS; i++)); do
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Iteration $i / $MAX_ITERATIONS${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Run claude with streaming output
    # shellcheck disable=SC2086
    if [[ "$USE_CCLEAN" == true ]]; then
        claude $CLAUDE_ARGS "$PROMPT" | cclean
    else
        claude $CLAUDE_ARGS "$PROMPT"
    fi

    if [[ $i -lt $MAX_ITERATIONS ]]; then
        echo ""
        echo -e "${GREEN}--- Completed iteration $i, continuing... ---${NC}"
        echo ""
        sleep 2
    fi
done

echo ""
echo -e "${BLUE}────────────────────────────────────────────${NC}"
echo -e "${GREEN}Ralph prompt loop completed after $MAX_ITERATIONS iterations${NC}"
