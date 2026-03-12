# Claude Code Integration Example

These files show how to wire Claude Code hooks to the budget enforcement API.

## How it works

- `check-budget.sh` calls `GET /api/check-budget` with a Databricks OAuth token
- On **SessionStart**: injects budget status as `additionalContext` (informational)
- On **UserPromptSubmit**: blocks the prompt with exit code 2 if over budget

## Setup

1. Deploy the Databricks App (see root README)
2. Copy `check-budget.sh` somewhere on your machine
3. Set `BUDGET_API_URL` to your deployed app URL:
   ```bash
   export BUDGET_API_URL=https://<workspace>.databricks.com/apps/<app-name>
   ```
4. Add hooks to your `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "SessionStart": [{"matcher": "", "hooks": [{"type": "command", "command": "bash /path/to/check-budget.sh", "timeout": 10000}]}],
       "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "bash /path/to/check-budget.sh --enforce", "timeout": 10000}]}]
     }
   }
   ```

## Installable plugin

If you use [claude-marketplace-builder](https://github.com/IceRhymers/claude-marketplace-builder),
the `budget-checker` plugin installs and configures this automatically.
