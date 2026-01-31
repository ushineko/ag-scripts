#!/bin/bash
#
# ralph-loop.sh - Ralph Wiggum Autonomous Development Loop
#
# Orchestrates Claude Code to work through specs in a project's specs/ folder.
# Each iteration spawns a fresh Claude context to prevent degradation.
#
# Usage: ralph-loop.sh [project_dir] [--max-iterations N] [--dry-run]
#
# Version: 1.0.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Defaults
MAX_ITERATIONS=50
DRY_RUN=false
PROJECT_DIR="."

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            echo "Usage: ralph-loop.sh [project_dir] [--max-iterations N] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  project_dir        Project directory (default: current directory)"
            echo "  --max-iterations N Maximum iterations before stopping (default: 50)"
            echo "  --dry-run          Show what would be done without executing"
            echo "  --help, -h         Show this help message"
            exit 0
            ;;
        *)
            PROJECT_DIR="$1"
            shift
            ;;
    esac
done

# Resolve to absolute path
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
SPECS_DIR="$PROJECT_DIR/specs"

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Ralph Wiggum Development Loop          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Project: ${GREEN}$PROJECT_DIR${NC}"
echo -e "Max iterations: ${YELLOW}$MAX_ITERATIONS${NC}"
echo ""

# Check for specs directory
if [[ ! -d "$SPECS_DIR" ]]; then
    echo -e "${RED}Error: No specs/ directory found in $PROJECT_DIR${NC}"
    echo "Create specs in $SPECS_DIR to use the Ralph loop."
    exit 1
fi

# Function to find incomplete specs
find_incomplete_specs() {
    local incomplete=()
    for spec in "$SPECS_DIR"/*.md; do
        [[ -f "$spec" ]] || continue
        # Check if spec is NOT marked complete
        if ! grep -q "Status: COMPLETE" "$spec" 2>/dev/null; then
            incomplete+=("$spec")
        fi
    done
    printf '%s\n' "${incomplete[@]}"
}

# Function to get spec number for sorting
get_spec_number() {
    basename "$1" | grep -oE '^[0-9]+' || echo "999"
}

# Main loop
iteration=0
while [[ $iteration -lt $MAX_ITERATIONS ]]; do
    ((iteration++))

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Iteration $iteration / $MAX_ITERATIONS${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Find incomplete specs
    mapfile -t incomplete_specs < <(find_incomplete_specs | sort -t'-' -k1 -n)

    if [[ ${#incomplete_specs[@]} -eq 0 ]]; then
        echo -e "${GREEN}✓ All specs complete! Ralph loop finished.${NC}"
        exit 0
    fi

    echo -e "Found ${YELLOW}${#incomplete_specs[@]}${NC} incomplete spec(s):"
    for spec in "${incomplete_specs[@]}"; do
        echo -e "  - $(basename "$spec")"
    done
    echo ""

    # Take the first (lowest numbered) incomplete spec
    current_spec="${incomplete_specs[0]}"
    spec_name="$(basename "$current_spec")"

    echo -e "Working on: ${GREEN}$spec_name${NC}"
    echo ""

    if [[ "$DRY_RUN" == true ]]; then
        echo -e "${YELLOW}[DRY RUN] Would execute Claude Code with spec: $spec_name${NC}"
        echo ""
        continue
    fi

    # Build the prompt for Claude
    PROMPT="You are in Ralph Loop Mode. Implement the following spec completely.

SPEC FILE: $spec_name

$(cat "$current_spec")

INSTRUCTIONS:
1. Read the spec requirements carefully
2. Implement all requirements
3. Verify all acceptance criteria are met
4. Mark the spec as complete (change 'Status:' line to 'Status: COMPLETE')
5. Check all boxes in the acceptance criteria
6. Output <promise>DONE</promise> when finished

Do NOT output DONE until ALL acceptance criteria are checked and the spec is marked complete."

    # Create a temporary file for the prompt
    PROMPT_FILE=$(mktemp)
    echo "$PROMPT" > "$PROMPT_FILE"

    # Run Claude Code and capture output
    echo -e "${BLUE}Launching Claude Code...${NC}"
    echo ""

    OUTPUT_FILE=$(mktemp)

    # Run claude with the prompt, working in the project directory
    # Use --print to get non-interactive output, pipe prompt via stdin
    if claude --print "$PROMPT" --cwd "$PROJECT_DIR" 2>&1 | tee "$OUTPUT_FILE"; then
        # Check for DONE signal
        if grep -q "<promise>DONE</promise>" "$OUTPUT_FILE"; then
            echo ""
            echo -e "${GREEN}✓ Spec $spec_name completed successfully${NC}"
        else
            echo ""
            echo -e "${YELLOW}⚠ Claude finished but no DONE signal detected${NC}"
            echo "The spec may need manual review or another iteration."
        fi
    else
        echo ""
        echo -e "${RED}✗ Claude Code exited with error${NC}"
    fi

    # Cleanup temp files
    rm -f "$PROMPT_FILE" "$OUTPUT_FILE"

    echo ""

    # Small delay between iterations
    sleep 2
done

echo -e "${YELLOW}⚠ Reached maximum iterations ($MAX_ITERATIONS)${NC}"
echo "Some specs may still be incomplete. Run again or increase --max-iterations."
exit 1
