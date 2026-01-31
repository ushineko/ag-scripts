# Spec 004: Ralph Loop Orchestration Script

**Status: COMPLETE**

## Description
Create a shell script that orchestrates Claude Code to work through specs in a loop, spawning fresh context per iteration.

## Requirements
- Accept project directory as argument (default: current directory)
- Find incomplete specs in `specs/` folder
- Process specs in numerical order (lowest first)
- Launch Claude Code with appropriate prompt for each spec
- Detect `<promise>DONE</promise>` completion signal
- Support max iterations limit
- Support dry-run mode

## Acceptance Criteria
- [x] Parses command-line arguments (project_dir, --max-iterations, --dry-run)
- [x] Finds specs directory and lists incomplete specs
- [x] Sorts specs by number prefix
- [x] Constructs proper prompt for Claude Code
- [x] Launches Claude Code with --print flag
- [x] Detects DONE signal in output
- [x] Loops until all specs complete or max iterations reached
- [x] Provides colored terminal output for status

## Implementation Notes
Created `ralph-loop.sh` with full CLI argument parsing, spec detection, and Claude Code orchestration.
