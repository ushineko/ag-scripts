# Integration: Jira via MCP (mcp-atlassian)

> **Policy module**: Activated via `## Selected Policies` in project `.claude/CLAUDE.md`.
> Configures Jira integration using the mcp-atlassian MCP server.

---

## Recommended Approach

Use the `mcp-atlassian` MCP server ([sooperset/mcp-atlassian](https://github.com/sooperset/mcp-atlassian)) for Jira integration. This is the recommended approach over direct API calls, `curl` commands, or grepping local files for ticket information.

**Why MCP over curl/API/grep:**
- MCP tools are first-class citizens in Claude Code — the agent discovers and uses them automatically
- No credential leakage in terminal output (credentials stay in `env` config, never in commands)
- 32 Jira tools available: issue CRUD, JQL search, sprints, boards, comments, transitions, worklogs, etc.
- Structured JSON responses instead of parsing HTML/curl output

## Setup (`~/.claude/mcp.json`)

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "uvx",
      "args": [
        "--python=3.12",
        "mcp-atlassian"
      ],
      "env": {
        "JIRA_URL": "https://<your-domain>.atlassian.net",
        "JIRA_USERNAME": "<your-email>",
        "JIRA_API_TOKEN": "<your-api-token>"
      }
    }
  }
}
```

**Setup notes:**
- Requires `uvx` (from `uv` package manager). Install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- `--python=3.12` is needed because `mcp-atlassian` may not yet support Python 3.14+. `uvx` will download 3.12 automatically if not installed
- Generate a Jira API token at: https://id.atlassian.com/manage-profile/security/api-tokens
- The `env` field passes credentials to the MCP server subprocess — they never appear in CLI args or terminal output
- Claude Code loads MCP servers at startup. After changing `mcp.json`, **restart Claude Code** for changes to take effect

## Alternative: Official Atlassian Rovo MCP Server

Atlassian provides an official remote MCP server at `https://mcp.atlassian.com/v1/mcp` using OAuth 2.1. This is more complex to set up (requires browser-based OAuth consent flow) but is officially maintained. See [Atlassian's MCP documentation](https://www.atlassian.com/platform/remote-mcp-server) for details.

## When to Fetch Issue Details

**Proactively fetch when:**
- A ticket ID (e.g., `PROJ-1234`) appears in user messages, branch names, commit messages, or spec files
- The user asks to "check", "verify", or "look at" a ticket
- Working in Ralph Loop mode and a spec references an issue

**Do not fetch when:**
- The ticket is mentioned in passing and context is already clear
- You already fetched the relevant information earlier in the session
- The user provides the issue details inline

**What to look at:**
- Issue description and acceptance criteria
- Current status (in progress, blocked, done)
- Comments for additional context or decisions
- Linked issues that may affect implementation

## MCP Tool Preference

**Always prefer MCP tools over alternatives:**
- **Use** `jira_get_issue`, `jira_search`, etc. (MCP tools) for all Jira operations
- **Never** use `curl` to hit the Jira API directly when the MCP server is configured
- **Never** grep local files to find ticket information when the MCP can fetch it
- **Never** ask the user to paste ticket details when MCP can retrieve them
- If the MCP server is unavailable (tools not listed), inform the user and suggest restarting Claude Code

**Other options**: Any issue tracker (GitHub Issues, Linear, Shortcut, Azure DevOps) with whatever integration method works for your setup — MCP server, CLI tool, API, or manual reference.
