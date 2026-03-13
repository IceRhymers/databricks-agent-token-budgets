## Context

AI Gateway inference tables store the raw JSON body of every request and response that passes through a configured endpoint. For Claude Code requests routed through AI Gateway, each row contains:

- `requester` — the Databricks user ID whose token was used
- `request_time` — when the request arrived
- `request` — full JSON including the `messages` array (conversation history), `model`, `tools`
- `response` — full JSON including the assistant's reply, `usage.input_tokens`, `usage.output_tokens`
- `status_code`, `execution_duration_ms`

There is no native session identifier — requests are independent rows. For this pipeline, the unit of analysis is **one request per row** in Silver, and **one day per user** as the aggregation grain in Gold.

The pipeline is deployed as part of the existing Databricks Asset Bundle so it can be managed alongside the budget app with a single `databricks bundle deploy`.

## Goals / Non-Goals

**Goals:**
- Parse inference table payload JSON into structured columns
- Produce per-user, per-day aggregates (request count, tokens, cost estimate, latency)
- Generate an AI summary for each individual Claude interaction using `ai_query()`
- Make the inference table name configurable (no hardcoded catalog/schema/endpoint)
- Deploy via Databricks Asset Bundle
- Use DLT (Spark Declarative Pipeline) for the ETL

**Non-Goals:**
- Session reconstruction or session-level aggregates
- Real-time streaming (triggered or scheduled refresh is sufficient given inference table delivery latency of up to 1 hour)
- Changes to the budget enforcement API
- Capturing OTEL traces — inference table is the only data source
- Supporting non-Claude models in the same pipeline (though schema is generic)

## Decisions

### D1: Per-request summaries in Gold, not per-day

Each Claude interaction is summarized individually via `ai_query()`. A per-day summary would lose the granularity of what each individual exchange was about. The Gold table stores one row per request with an AI-generated summary; the dashboard can then group, filter, and paginate by user and date.

**Alternative considered:** One summary per day per user ("here's what you worked on today"). Rejected — loses individual interaction detail, and reconstructing a coherent day-level summary across many unrelated requests would produce low-quality output.

### D2: Configurable inference table via bundle variable

The inference table name is passed as a Databricks Asset Bundle variable (`inference_table`). This allows different workspace deployments to point at different endpoints without code changes.

```yaml
# databricks.yml
variables:
  inference_table:
    description: "Fully-qualified inference table name (catalog.schema.endpoint_payload)"
```

**Alternative considered:** Environment variable in `app.yaml`. Rejected — DAB variables are the idiomatic way to parameterize pipeline targets, and they integrate with `databricks bundle deploy --var`.

### D3: DLT Materialized Views for Gold, Streaming Tables for Bronze/Silver

- Bronze: Streaming Table (continuously appends new rows from inference table)
- Silver: Streaming Table (parses JSON, structured columns, 1:1 with Bronze)
- Gold aggregates: Materialized View (refreshed on pipeline trigger)
- Gold summaries: Materialized View (runs `ai_query()` on new Silver rows)

`ai_query()` cannot run inside a Streaming Table because it is not a streaming operation. Materialized Views support batch `ai_query()` calls. The pipeline runs on a trigger schedule (e.g., hourly or daily).

### D4: Use `ai_query()` not `ai_summarize()`

`ai_query()` allows a custom prompt and model selection. `ai_summarize()` is a convenience wrapper with less control. For interaction summaries we want a specific prompt format ("What was the developer asking Claude to do? What did Claude do?") and a configurable model.

### D5: Pipeline lives in `pipeline/` subdirectory, bundle config extended in root `databricks.yml`

The existing `databricks.yml` already defines the budget app. The ETL pipeline resources are added as an additional resource block in the same bundle. Pipeline source lives in `pipeline/` alongside the existing `app/` directory.

## Architecture

```
pipeline/
├── dlt_pipeline.py         # DLT pipeline definition (Bronze + Silver + Gold)
└── README.md               # Pipeline docs

databricks.yml              # Extended with pipeline resource block
```

### Bronze Layer — `bronze_inference_payload`

Streaming Table. Reads from the configured inference table with `spark.readStream`. Passes rows through unchanged — no transformation. Acts as the raw landing zone.

Key columns passed through: `databricks_request_id`, `requester`, `request_time`, `status_code`, `request`, `response`, `execution_duration_ms`

### Silver Layer — `silver_parsed_requests`

Streaming Table. Parses the `request` and `response` JSON columns into structured fields. Filters to `status_code = 200` and non-null payloads.

Derived columns:
- `model` — extracted from `request:model`
- `messages_json` — extracted from `request:messages` (raw JSON array, kept as string)
- `last_user_message` — last message in the messages array where role = "user"
- `assistant_response` — first text block from `response:content`
- `input_tokens` — from `response:usage.input_tokens`
- `output_tokens` — from `response:usage.output_tokens`
- `usage_date` — `DATE(request_time)` for partitioning

### Gold Layer — `gold_user_daily_metrics` (Materialized View)

Per-user, per-day aggregates. Joins with Silver on `requester` and `usage_date`.

Columns:
- `requester`, `usage_date`
- `request_count` — COUNT(*)
- `total_input_tokens`, `total_output_tokens`, `total_tokens`
- `avg_latency_ms`
- `first_request`, `last_request`
- `models_used` — COLLECT_SET(model)
- `estimated_cost_usd` — derived from token counts × configurable per-token rate

### Gold Layer — `gold_interaction_summaries` (Materialized View)

One row per request. Runs `ai_query()` on the `last_user_message` + `assistant_response` to generate a plain-language summary of what the interaction was about.

Columns:
- `databricks_request_id`, `requester`, `request_time`, `usage_date`, `model`
- `input_tokens`, `output_tokens`
- `interaction_summary` — output of `ai_query()`
- `task_type` — output of a separate `ai_query()` classification call (one of: debugging / new-feature / refactor / question / explanation / other)

## Affected Files

```
databricks.yml                        — add pipeline resource block and variables
pipeline/dlt_pipeline.py              — new: DLT pipeline definition
pipeline/README.md                    — new: pipeline docs and usage
openspec/changes/claude-usage-etl-pipeline/   — this spec
```
