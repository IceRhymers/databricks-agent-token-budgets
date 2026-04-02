#!/usr/bin/env bash
# Register Claude Code session → Databricks user mapping.
# Runs as a SessionStart hook. Calls the usage-limits app's
# /api/sessions/register endpoint so OTEL metrics can be
# attributed to specific workspace users.
# Fails open on any error — never blocks a session.

trap 'exit 0' ERR
set -euo pipefail

BUDGET_API="${BUDGET_API_URL:-}"
PROFILE="${DATABRICKS_CLI_PROFILE:-DEFAULT}"

# --- Early exit if not configured ---
if [[ -z "$BUDGET_API" ]]; then
  exit 0  # App URL not set — nothing to do
fi

# --- Get OAuth token via Databricks CLI ---
if ! command -v databricks &>/dev/null; then
  exit 0  # CLI not installed — fail open
fi

TOKEN_JSON=$(databricks auth token --profile "$PROFILE" 2>/dev/null) || true
if [[ -z "$TOKEN_JSON" ]]; then
  exit 0  # Token retrieval failed — fail open
fi

if command -v jq &>/dev/null; then
  TOKEN=$(echo "$TOKEN_JSON" | jq -r '.access_token // empty' 2>/dev/null) || true
else
  TOKEN=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" <<< "$TOKEN_JSON" 2>/dev/null) || true
fi

if [[ -z "$TOKEN" ]]; then
  exit 0  # Token parse failed — fail open
fi

# --- Resolve session ID (three-tier fallback) ---
SESSION_ID=""

# Tier 1: stdin JSON from hook framework
if [[ -t 0 ]]; then
  : # stdin is a terminal, skip
else
  STDIN_DATA=$(cat 2>/dev/null) || true
  if [[ -n "$STDIN_DATA" ]]; then
    if command -v jq &>/dev/null; then
      SESSION_ID=$(echo "$STDIN_DATA" | jq -r '.session_id // empty' 2>/dev/null) || true
    else
      SESSION_ID=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" <<< "$STDIN_DATA" 2>/dev/null) || true
    fi
  fi
fi

# Tier 2: environment variable
if [[ -z "$SESSION_ID" ]]; then
  SESSION_ID="${CLAUDE_SESSION_ID:-}"
fi

# Tier 3: generate a UUID
if [[ -z "$SESSION_ID" ]]; then
  if command -v uuidgen &>/dev/null; then
    SESSION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]') || true
  else
    SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())" 2>/dev/null) || true
  fi
fi

if [[ -z "$SESSION_ID" ]]; then
  exit 0  # Could not determine session ID — fail open
fi

# --- Register session with the app ---
curl -s -f -m 5 \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Forwarded-Access-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION_ID\"}" \
  "$BUDGET_API/api/sessions/register" >/dev/null 2>&1 || true

cat <<EOF
{"additionalContext": "Session registered for per-user OTEL tracking."}
EOF
exit 0
