# Integration: GitLab via glab CLI

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> Configures GitLab integration using the glab CLI tool.

---

## Approach

One tested approach uses `glab` (GitLab CLI), authenticated via a Personal Access Token. Other valid approaches include GitLab MCP servers, the GitLab web UI, direct API calls, or equivalent tools for other platforms (GitHub `gh`, Bitbucket CLI, etc.).

## Common Operations

```bash
# Merge requests
glab mr create --source-branch <branch> --target-branch <target> --title "title" --description "body"
glab mr view <number>
glab mr merge <number> --auto-merge --remove-source-branch

# Issues and pipelines
glab issue view <number>
glab ci status
```

## Practical Notes

- Must be run from within a repo that has the correct remote, or use `--repo` flag
- `--merge-when-pipeline-succeeds` is deprecated — use `--auto-merge` instead
- If an MR already exists for a source branch, `glab mr create` will fail with 409 — use `glab mr update` instead
- If authentication fails, the token may have expired — regenerate it in your GitLab user settings

**Other options**: GitHub (`gh` CLI or GitHub MCP), Bitbucket, Azure DevOps, or web UI workflows. The patterns (create branch, open MR/PR, review, merge) are the same regardless of platform.
