#!/usr/bin/env bash
# Shared utilities for deploy and grant scripts.
#
# Contract: the sourcing script must set BUNDLE_ROOT and TARGET before
# sourcing this file.  All functions use those two variables.

# ── Warehouse resolution ────────────────────────────────────────────────

resolve_warehouse_id() {
  local wh_id
  wh_id="$(databricks bundle summary -o json -t "$TARGET" | jq -r '
    .resources.sql_warehouses | to_entries | first | .value.id
  ')"
  if [[ -z "$wh_id" || "$wh_id" == "null" ]]; then
    echo "Error: Could not resolve SQL warehouse from bundle summary." >&2
    return 1
  fi
  echo "$wh_id"
}

# ── DAB variable resolution ────────────────────────────────────────────

resolve_dab_variable() {
  local name="$1"
  databricks bundle summary -o json -t "$TARGET" | jq -r --arg n "$name" \
    '.variables[$n].value // .variables[$n].default // empty'
}

# ── SQL execution ───────────────────────────────────────────────────────

run_sql() {
  local sql="$1"
  local warehouse_id="${2:-$WAREHOUSE_ID}"
  echo "    SQL: ${sql:0:120}..."
  databricks api post /api/2.0/sql/statements \
    --json "{
      \"warehouse_id\": \"$warehouse_id\",
      \"statement\": $(echo "$sql" | jq -Rs .),
      \"wait_timeout\": \"30s\"
    }" | jq -r '.status.state'
}
