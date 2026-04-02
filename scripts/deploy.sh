#!/usr/bin/env bash
# Deploy script for usage-limits Databricks Asset Bundle.
#
# Usage: bash scripts/deploy.sh [COMMAND] [--target TARGET]
#
# Commands:
#   validate   Validate the bundle configuration
#   deploy     Deploy the bundle to the workspace
#   start      Start the app compute (skips if already ACTIVE)
#   stop       Stop the app compute
#   app-deploy Deploy the app source code
#   migrate    Grant Lakebase schema perms + run Alembic migrations
#   grant      Grant system table access to the app's SP
#   create-otel-table  Create the OTEL metrics Delta table (idempotent)
#   full       deploy → start → migrate → create-otel-table → grant → app-deploy (default)
#   help       Print this help message

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BUNDLE_ROOT"

TARGET="${TARGET:-dev}"

# ── Parse arguments ──────────────────────────────────────────────────────

COMMAND="${1:-full}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Prerequisites ────────────────────────────────────────────────────────

check_prereqs() {
  if ! command -v databricks &>/dev/null; then
    echo "Error: 'databricks' CLI not found. Install: https://docs.databricks.com/dev-tools/cli/install.html"
    exit 1
  fi
  if ! command -v jq &>/dev/null; then
    echo "Error: 'jq' not found. Install: https://jqlang.github.io/jq/download/"
    exit 1
  fi
  if ! command -v envsubst &>/dev/null; then
    echo "Error: 'envsubst' not found. Install: brew install gettext (macOS) or apt-get install gettext (Linux)"
    exit 1
  fi
}

source "$SCRIPT_DIR/common.sh"

# ── Bundle helpers ───────────────────────────────────────────────────────

get_app_name() {
  databricks bundle summary -o json -t "$TARGET" | jq -r '.resources.apps | to_entries | first | .value.name'
}

get_workspace_path() {
  databricks bundle summary -o json -t "$TARGET" | jq -r '.workspace.file_path'
}

# ── Subcommands ──────────────────────────────────────────────────────────

cmd_validate() {
  echo "==> Validating bundle (target: $TARGET)..."
  databricks bundle validate -t "$TARGET"
  echo "    Bundle is valid."
}

cmd_deploy() {
  echo "==> Deploying bundle (target: $TARGET)..."
  databricks bundle deploy -t "$TARGET"
  echo "    Bundle deployed."
}

cmd_start() {
  local app_name
  app_name="$(get_app_name)"
  echo "==> Starting app '$app_name'..."

  local state
  state="$(databricks apps get "$app_name" -o json 2>/dev/null | jq -r '.compute_status.state // empty')" || true

  if [[ "$state" == "ACTIVE" ]]; then
    echo "    App is already ACTIVE — skipping start."
    return
  fi

  databricks apps start "$app_name"
  echo "    Start initiated."
}

cmd_stop() {
  local app_name
  app_name="$(get_app_name)"
  echo "==> Stopping app '$app_name'..."
  databricks apps stop "$app_name"
  echo "    Stop initiated."
}

cmd_app_deploy() {
  local app_name workspace_path
  app_name="$(get_app_name)"
  workspace_path="$(get_workspace_path)/app"
  echo "==> Deploying app source for '$app_name'..."
  databricks apps deploy "$app_name" --source-code-path "$workspace_path"
  echo "    App deploy initiated."
}

cmd_migrate() {
  local app_name
  app_name="$(get_app_name)"
  echo "==> Running Lakebase migration for '$app_name'..."
  uv run --directory "$BUNDLE_ROOT/app" python "$SCRIPT_DIR/migrate.py" --app-name "$app_name" --instance "usage-limits"
}

cmd_create_otel_table() {
  echo "==> Creating OTEL metrics table..."
  local catalog schema warehouse_id table_sql
  catalog="$(resolve_dab_variable otel_catalog)"
  schema="$(resolve_dab_variable otel_schema)"
  warehouse_id="$(resolve_warehouse_id)"
  echo "    Catalog: $catalog  Schema: $schema  Warehouse: $warehouse_id"

  WAREHOUSE_ID="$warehouse_id" run_sql "CREATE SCHEMA IF NOT EXISTS \`$catalog\`.\`$schema\`"

  table_sql="$(OTEL_CATALOG="$catalog" OTEL_SCHEMA="$schema" envsubst < "$BUNDLE_ROOT/sql/create_otel_metrics.sql")"
  # Strip SQL comments before sending
  table_sql="$(echo "$table_sql" | sed '/^--/d')"
  WAREHOUSE_ID="$warehouse_id" run_sql "$table_sql"
  echo "    OTEL metrics table ready."
}

cmd_grant() {
  echo "==> Granting system table access (target: $TARGET)..."
  bash "$SCRIPT_DIR/grant_system_access.sh" --target "$TARGET"
}

cmd_full() {
  cmd_deploy
  cmd_start
  cmd_migrate
  cmd_create_otel_table
  cmd_grant
  cmd_app_deploy
}

cmd_help() {
  echo "Usage: bash scripts/deploy.sh [COMMAND] [--target TARGET]"
  echo ""
  echo "Commands:"
  echo "  validate    Validate the bundle configuration"
  echo "  deploy      Deploy the bundle to the workspace"
  echo "  start       Start the app compute (skips if ACTIVE)"
  echo "  stop        Stop the app compute"
  echo "  app-deploy  Deploy the app source code"
  echo "  migrate     Grant Lakebase schema perms + run Alembic migrations"
  echo "  grant       Grant system table access to the app's SP"
  echo "  create-otel-table  Create the OTEL metrics Delta table (idempotent)"
  echo "  full        deploy → start → migrate → create-otel-table → grant → app-deploy (default)"
  echo "  help        Print this help message"
  echo ""
  echo "Options:"
  echo "  --target TARGET   Deployment target (default: dev)"
}

# ── Dispatch ─────────────────────────────────────────────────────────────

check_prereqs

case "$COMMAND" in
  validate)   cmd_validate ;;
  deploy)     cmd_deploy ;;
  start)      cmd_start ;;
  stop)       cmd_stop ;;
  app-deploy) cmd_app_deploy ;;
  migrate)    cmd_migrate ;;
  grant)      cmd_grant ;;
  create-otel-table) cmd_create_otel_table ;;
  full)       cmd_full ;;
  help)       cmd_help ;;
  *)          echo "Unknown command: $COMMAND"; cmd_help; exit 1 ;;
esac
