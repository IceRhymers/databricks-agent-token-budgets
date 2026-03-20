---
name: install-budget-hook
description: Install the Databricks token budget enforcement hook into Claude Code. Sets up SessionStart and UserPromptSubmit hooks that check your AI Gateway spending against configured budgets.
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Install Budget Hook

This skill installs the Databricks AI Gateway budget enforcement hook into the user's Claude Code environment.

## What it does

1. Copies `check-budget.sh` to `~/.claude/hooks/check-budget.sh`
2. Configures hooks in `~/.claude/settings.json` for:
   - **SessionStart**: Shows budget status at the start of each session
   - **UserPromptSubmit**: Blocks prompts when the user is over budget
3. Prompts the user for their `BUDGET_API_URL` (their deployed Databricks App URL)

## Steps

### 1. Ask for configuration

Before doing anything, ask the user:

- **BUDGET_API_URL**: The URL of their deployed usage-limits Databricks App (e.g., `https://usage-limits-xxxxx.aws.databricksapps.com`). This is required.
- **DATABRICKS_CLI_PROFILE**: Their Databricks CLI profile name. Defaults to `DEFAULT` if not specified.

### 2. Find the plugin directory

The hook script lives in this plugin's directory. Find it:

```bash
PLUGIN_DIR="$(dirname "$(dirname "$(dirname "$(readlink -f "$0")")")")"
```

Or look for it relative to this skill file at `../../../examples/claude-code/check-budget.sh`.

### 3. Copy the hook script

```bash
mkdir -p ~/.claude/hooks
cp <plugin-dir>/examples/claude-code/check-budget.sh ~/.claude/hooks/check-budget.sh
chmod +x ~/.claude/hooks/check-budget.sh
```

### 4. Configure the hook script

Edit `~/.claude/hooks/check-budget.sh` and replace the default `BUDGET_API` line with the user's URL:

```bash
BUDGET_API="${BUDGET_API_URL:-<user-provided-url>}"
```

### 5. Add hooks to settings.json

Read `~/.claude/settings.json` (create it if it doesn't exist). Merge these hooks into the existing config — do NOT overwrite other settings:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/check-budget.sh",
            "timeout": 10000
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/check-budget.sh --enforce",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

### 6. Verify setup

Run a quick test to make sure the hook script is executable and the Databricks CLI is available:

```bash
bash ~/.claude/hooks/check-budget.sh && echo "Hook installed successfully"
```

Tell the user:
- The hook will show their budget status at the start of every Claude Code session
- Every prompt will be checked against their budget — if over budget, the prompt is blocked
- The hook fails open: if the API is unreachable or the CLI isn't installed, prompts are allowed
- They need the Databricks CLI configured with `databricks auth login` for authentication to work

### Prerequisites

The user needs:
- **Databricks CLI** installed and authenticated (`databricks auth login`)
- A deployed instance of the **databricks-agent-token-budgets** app with a budget configured for their user
- `jq` or `python3` available (for JSON parsing — the script handles both)
