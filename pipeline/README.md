# Claude Usage Analytics Pipeline

DLT pipeline that ingests AI Gateway inference table data and produces per-user, per-day Claude analytics with AI-generated interaction summaries.

## Architecture

```
Bronze: bronze_inference_payload      — raw streaming read from inference table
Silver: silver_parsed_requests        — parsed JSON, 200s only, structured columns
Gold:   gold_user_daily_metrics       — per-user per-day aggregates
Gold:   gold_interaction_summaries    — per-request AI summaries + task classification
```

## Prerequisites

1. AI Gateway inference table logging must be enabled on your model serving endpoint
2. Unity Catalog must be enabled in your workspace
3. Databricks CLI installed and authenticated

## Deploy

```bash
databricks bundle deploy \
  --var inference_table=catalog.schema.endpoint_payload \
  --var sql_warehouse_id=your_warehouse_id
```

Replace `catalog.schema.endpoint_payload` with your actual inference table name. The table name follows the pattern `<catalog>.<schema>.<endpoint-name>_payload`.

## Run

After deploying, trigger the pipeline manually or wait for the hourly schedule:

```bash
databricks bundle run claude_usage_pipeline
```

Or trigger from the Databricks UI: Workflows → Delta Live Tables → claude-usage-analytics → Start.

## Gold Tables

### `gold_user_daily_metrics`

Per-user per-day aggregates:

| Column | Description |
|--------|-------------|
| `requester` | Databricks user ID |
| `usage_date` | Date (UTC) |
| `request_count` | Number of Claude API calls |
| `total_input_tokens` | Total input tokens |
| `total_output_tokens` | Total output tokens |
| `total_tokens` | Combined token count |
| `avg_latency_ms` | Average request latency |
| `first_request` | Earliest request timestamp |
| `last_request` | Latest request timestamp |
| `models_used` | Array of distinct models used |

### `gold_interaction_summaries`

Per-request AI-generated summaries:

| Column | Description |
|--------|-------------|
| `databricks_request_id` | Unique request ID (join key) |
| `requester` | Databricks user ID |
| `request_time` | Request timestamp |
| `usage_date` | Date (UTC) |
| `model` | Claude model used |
| `input_tokens` | Input token count |
| `output_tokens` | Output token count |
| `interaction_summary` | 1-2 sentence summary of the interaction |
| `task_type` | Classification: debugging / new-feature / refactor / question / explanation / other |

## Example Queries

```sql
-- What was a user working on this week?
SELECT request_time, interaction_summary, task_type, input_tokens + output_tokens AS tokens
FROM gold_interaction_summaries
WHERE requester = 'user@company.com'
  AND usage_date >= current_date() - INTERVAL 7 DAYS
ORDER BY request_time DESC;

-- Top users by token consumption today
SELECT requester, request_count, total_tokens, avg_latency_ms
FROM gold_user_daily_metrics
WHERE usage_date = current_date()
ORDER BY total_tokens DESC;

-- Task type breakdown by user
SELECT requester, task_type, COUNT(*) AS count
FROM gold_interaction_summaries
WHERE usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY requester, task_type
ORDER BY requester, count DESC;
```

## Notes

- Inference table delivery is best-effort with up to 1 hour delay — pipeline results lag by the same amount
- Requests with payloads exceeding 1 MiB (GA) or 10 MiB (Beta) may not be logged by AI Gateway
- `ai_query()` calls in `gold_interaction_summaries` incur LLM costs per row — factor this into your pipeline schedule
- The pipeline uses `databricks-meta-llama-3-3-70b-instruct` for summaries by default — change in `dlt_pipeline.py` if needed
