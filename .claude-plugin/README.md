# Claude Code Plugin

This plugin provides two hooks for Claude Code:

- **SessionStart** → `register-session.sh` maps the session to the authenticated Databricks user for per-user OTEL analysis
- **UserPromptSubmit** → `check-budget.sh --enforce` blocks prompts when a user exceeds their AI Gateway budget

Both scripts live in `plugin-scripts/` and use the same `BUDGET_API_URL` env var.

## Setup

1. Deploy the usage-limits Databricks App (see root README)
2. Set `BUDGET_API_URL` in `~/.claude/settings.json`:
   ```json
   {
     "env": {
       "BUDGET_API_URL": "https://usage-limits-<id>.aws.databricksapps.com"
     }
   }
   ```

## Manual setup (without plugin system)

If you're not using the plugin system, add hooks directly to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "bash /path/to/plugin-scripts/register-session.sh", "timeout": 10000}]}],
    "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "bash /path/to/plugin-scripts/check-budget.sh --enforce", "timeout": 10000}]}]
  }
}
```

## Installable plugins

If you use [claude-marketplace-builder](https://github.com/IceRhymers/claude-marketplace-builder),
the `budget-checker` and `databricks-otel` plugins install and configure these hooks automatically.
