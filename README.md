# databricks-agent-token-budgets

A Databricks App that tracks AI Gateway token usage per user and enforces daily, weekly, and monthly dollar budgets. Includes a React dashboard for admins and a Claude Code hook that blocks prompts when a user exceeds their budget.

## How It Works

1. A background scheduler queries `system.ai_gateway.usage` every 5 minutes to calculate per-user dollar costs across 1-day, 7-day, and 30-day windows using model-specific DBU pricing.
2. Usage snapshots are cached in a Lakebase (PostgreSQL) database alongside budget configurations.
3. When a budget is exceeded, a warning is created with an automatic expiry at the end of the budget period.
4. Claude Code hooks call `GET /api/check-budget` before every prompt. If the user is over budget, the hook exits with code 2 and Claude Code blocks the prompt.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Databricks App (FastAPI)                       │
│                                                 │
│  /api/check-budget   ← Claude Code hook calls   │
│  /api/overview       ← React dashboard          │
│  /api/users          ← Admin management          │
│  /api/budgets        ← Budget CRUD               │
│                                                 │
│  Background jobs:                               │
│   • Evaluation cycle (query usage, warn)        │
│   • User sync (auto-discover AI Gateway users)  │
├─────────────────────────────────────────────────┤
│  Lakebase (PostgreSQL)                          │
│   • budget_configs      • usage_snapshots       │
│   • default_budgets     • warnings              │
│   • audit_log           • app_config            │
├─────────────────────────────────────────────────┤
│  Databricks SQL Warehouse                       │
│   → system.ai_gateway.usage                     │
│   → system.serving.*                            │
└─────────────────────────────────────────────────┘
```

## Prerequisites

- A Databricks workspace with AI Gateway enabled
- Databricks CLI installed and configured (`databricks auth login`)
- A SQL warehouse (Serverless Starter is fine)
- System tables access (`system.ai_gateway.usage`)

## Deploy the Databricks App

This project uses [Databricks Asset Bundles](https://docs.databricks.com/dev-tools/bundles/index.html).

### 1. Clone and install dependencies

```bash
git clone https://github.com/IceRhymers/databricks-agent-token-budgets.git
cd databricks-agent-token-budgets
make install
```

### 2. Configure the bundle

Edit `databricks.yml` if you need to change the SQL warehouse lookup or admin user:

```yaml
variables:
  sql_warehouse_id:
    lookup:
      warehouse: "Serverless Starter Warehouse"  # your warehouse name
  admin_user:
    default: ${workspace.current_user.userName}
```

### 3. Build and deploy

```bash
# Validate first
make validate

# Full deploy (builds frontend, deploys bundle, starts app, grants system table access)
make deploy
```

This runs: `bundle deploy` → `app start` → `grant system table access` → `app deploy`.

### 4. Set default budgets

Open the app URL in your browser (printed after deploy) and configure default budgets via the dashboard. Users are auto-discovered from AI Gateway usage data and assigned the default budget.

## Install the Claude Code Hook

There are two ways to use the budget enforcement hook with Claude Code.

### Option A: Install as a Claude Code plugin

If you use the [Claude Code marketplace](https://github.com/IceRhymers/claude-marketplace-builder), install this repo as a plugin:

```bash
claude plugin add https://github.com/IceRhymers/databricks-agent-token-budgets
```

Then run the `install-budget-hook` skill in Claude Code — it will set up the hook and configure your environment.

### Option B: Manual setup

1. Set environment variables (in your shell profile):

```bash
export BUDGET_API_URL=https://<your-app-url>.databricksapps.com
export DATABRICKS_CLI_PROFILE=DEFAULT  # optional, defaults to DEFAULT
```

2. Copy `examples/claude-code/check-budget.sh` somewhere permanent:

```bash
cp examples/claude-code/check-budget.sh ~/.claude/hooks/check-budget.sh
chmod +x ~/.claude/hooks/check-budget.sh
```

3. Add hooks to `~/.claude/settings.json`:

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

## How the Hook Works

The hook runs in two modes:

- **SessionStart** (no flags): Calls the budget API, outputs current budget status as `additionalContext` so Claude sees your spending at the start of each session.
- **UserPromptSubmit** (`--enforce`): Calls the budget API before every prompt. If `allowed: false`, exits with code 2, which blocks the prompt in Claude Code.

The hook authenticates via `databricks auth token` (OAuth) and sends the token as `X-Forwarded-Access-Token`. It fails open on any error — if the API is unreachable or the CLI isn't installed, prompts are allowed.

## Configuration

### Environment Variables (App)

| Variable | Required | Default | Description |
|---|---|---|---|
| `PGHOST` | Yes | — | Lakebase host (set automatically by app resource binding) |
| `PGDATABASE` | Yes | `databricks_postgres` | Lakebase database name |
| `LAKEBASE_INSTANCE` | Yes | — | Lakebase instance name |
| `SQL_WAREHOUSE_ID` | Yes | — | SQL warehouse for system table queries |
| `EVALUATION_INTERVAL_MINUTES` | No | `5` | How often to evaluate budgets |
| `USER_SYNC_INTERVAL_MINUTES` | No | `5` | How often to sync users from AI Gateway |
| `ADMIN_GROUPS` | No | — | Comma-separated group names with admin access |

### Environment Variables (Hook)

| Variable | Required | Default | Description |
|---|---|---|---|
| `BUDGET_API_URL` | No | `https://usage-limits-1444828305810485.aws.databricksapps.com` | Your deployed app URL |
| `DATABRICKS_CLI_PROFILE` | No | `DEFAULT` | Databricks CLI profile for auth |

## API

### `GET /api/check-budget`

Returns budget status for the authenticated user.

**Headers:** `X-Forwarded-Access-Token: <databricks-oauth-token>`

**Response (within budget):**
```json
{
  "allowed": true,
  "usage": 12.50,
  "limit": 100.00,
  "period": "monthly"
}
```

**Response (over budget):**
```json
{
  "allowed": false,
  "reason": "monthly_limit",
  "usage": 105.00,
  "limit": 100.00,
  "period": "monthly"
}
```

## Development

```bash
# Install dependencies
make install

# Run backend locally
make serve

# Run frontend dev server
make fe-dev

# Run tests
make test

# Run tests with coverage
make test-cov
```

## Project Structure

```
├── app/
│   ├── main.py              # FastAPI entrypoint + scheduler
│   ├── api.py               # /api/check-budget endpoint
│   ├── core/
│   │   ├── auth.py          # User identity resolution
│   │   ├── budget.py        # Budget evaluation logic
│   │   ├── config.py        # App configuration
│   │   ├── db.py            # Database engine + schema init
│   │   ├── evaluator.py     # Background evaluation cycle
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── pricing.py       # Model pricing + cost SQL
│   │   ├── usage.py         # System table queries
│   │   └── warnings.py      # Warning management
│   ├── routers/             # API route handlers
│   ├── schemas/             # Pydantic request/response schemas
│   ├── frontend/            # React + Vite dashboard
│   └── tests/               # Unit + integration tests
├── examples/claude-code/    # Reference hook implementation
├── resources/               # DAB resource definitions
├── scripts/                 # Deploy + grant scripts
├── .claude/skills/          # Claude Code plugin skill
├── plugin.json              # Claude Code plugin manifest
└── databricks.yml           # Databricks Asset Bundle config
```

## License

MIT
