## Why

The existing `databricks-agent-token-budgets` app tracks spend and enforces budget limits but has no visibility into *how* users are using Claude — what they're asking, what Claude is doing, and how usage patterns differ across developers. Admins can see token counts but not the nature of the work.

AI Gateway inference tables capture the full request/response JSON for every Claude API call that passes through a configured endpoint. This raw data is sufficient to reconstruct per-user, per-day activity and generate natural language summaries of each interaction — but only with a pipeline to parse, enrich, and surface it.

## What Changes

- Add a DLT (Spark Declarative Pipeline) that reads from a configurable inference table and produces per-user, per-day Claude usage analytics
- Add a Databricks Asset Bundle manifest to deploy the pipeline as a managed Databricks resource alongside the existing app
- Add `ai_query()`-powered batch inference to generate a plain-language summary for each Claude interaction
- No changes to the existing budget enforcement app or its API

## Capabilities

### New Capabilities

- `etl-pipeline`: A three-layer DLT pipeline (Bronze → Silver → Gold) that ingests AI Gateway inference table data, parses conversation content, and produces per-user daily usage summaries with AI-generated interaction summaries
- `pipeline-bundle`: Databricks Asset Bundle resources that deploy and manage the DLT pipeline via `databricks bundle deploy`

### Unchanged Capabilities

- `budget-enforcement`: The existing `/api/check-budget` endpoint and budget checking logic are unchanged
- `inference-table-config`: The pipeline references an inference table by a configurable fully-qualified table name — no assumption about catalog/schema/endpoint naming
