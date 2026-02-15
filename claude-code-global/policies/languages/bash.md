# Bash / Shell Script Standards

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> Apply these guidelines when writing shell scripts.

---

## Shell Portability
- Know your target shell: `/bin/sh`, `bash`, and `dash` are all different
- Use appropriate shebang: `#!/bin/bash` for bash-specific features, `#!/bin/sh` for POSIX compatibility
- If targeting bash, use bash-native features; don't write POSIX-only code in a bash script
- Document shell requirements in script header if non-obvious

## Prefer Bash-Native Patterns
When using bash, prefer built-in constructs over subshells and external commands:
- Use `[[ ]]` instead of `[ ]` for conditionals (better quoting, pattern matching, regex)
- Use `$(( ))` for arithmetic instead of `expr`
- Use parameter expansion for string manipulation: `${var%suffix}`, `${var#prefix}`, `${var/old/new}`
- Use `printf` over `echo` for portable/predictable output
- Use `read` with proper options: `read -r` to prevent backslash interpretation

## Error Handling
Scripts follow the same reliability rules as other languages:
- Use `set -e` (exit on error), `set -u` (error on undefined vars), `set -o pipefail` (catch pipe failures)
- Check return codes explicitly for critical operations
- Never let a script continue blindly after a failure - this leaves systems in inconsistent states
- Guard destructive operations (rm, mv, truncate) with existence checks and confirmations
- Use `|| exit 1` or `|| return 1` for commands that must succeed

## Traps and Signals
- Use `trap` for cleanup on EXIT, ERR, INT, TERM
- Clean up temporary files, restore state, release locks
- Example: `trap 'rm -f "$tmpfile"' EXIT`
- Consider what happens if script is interrupted mid-operation

## Debugging and Observability
- Use `set -x` selectively for debugging (or enable via env var)
- Log meaningful messages to stderr for diagnostics: `echo "Processing $file..." >&2`
- Include script name in error messages for clarity in logs
- Consider a verbose/debug flag for operational visibility

## Safety Practices
- Quote all variable expansions: `"$var"` not `$var`
- Use `--` to separate options from arguments in commands that support it
- Validate inputs before using them in commands
- Be explicit about paths - don't assume working directory
- Use `mktemp` for temporary files, not predictable names in `/tmp`

## Linting
- Run `shellcheck` on all scripts before committing
- Address warnings, not just errors - they often catch real bugs
- Document intentional shellcheck disables: `# shellcheck disable=SC2034`
