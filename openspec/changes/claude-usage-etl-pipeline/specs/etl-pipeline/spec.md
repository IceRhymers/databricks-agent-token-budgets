## Bronze Layer

### Requirement: Bronze table streams from configurable inference table

`bronze_inference_payload` SHALL be a DLT Streaming Table that reads from the inference table specified by the `inference_table` bundle variable using `spark.readStream`.

The table name SHALL be passed via a configurable parameter — no hardcoded catalog, schema, or endpoint name.

#### Scenario: new rows appear in inference table
- **WHEN** new rows are written to the configured inference table
- **THEN** `bronze_inference_payload` appends those rows on the next pipeline trigger
- **AND** no rows are dropped or duplicated

#### Scenario: inference table is empty
- **WHEN** the inference table has no rows
- **THEN** `bronze_inference_payload` is created as an empty table with matching schema
- **AND** no pipeline error is raised

---

## Silver Layer

### Requirement: Silver table parses JSON columns into structured fields

`silver_parsed_requests` SHALL be a DLT Streaming Table that reads from `bronze_inference_payload` and extracts structured columns from the `request` and `response` JSON strings.

#### Scenario: valid 200 request with messages and response
- **WHEN** a Bronze row has `status_code = 200`, a non-null `request` JSON containing a `messages` array, and a non-null `response` JSON
- **THEN** Silver produces one row with:
  - `model` extracted from `request:model`
  - `last_user_message` set to the content of the last message where role = "user"
  - `assistant_response` set to the first text block from `response:content`
  - `input_tokens` and `output_tokens` extracted from `response:usage`
  - `usage_date` set to `DATE(request_time)`

#### Scenario: non-200 response is excluded
- **WHEN** a Bronze row has `status_code != 200`
- **THEN** no Silver row is produced for that request

#### Scenario: null request or response payload
- **WHEN** a Bronze row has a null `request` or null `response` (e.g., oversized payload logging error)
- **THEN** no Silver row is produced for that request

#### Scenario: messages array has no user message
- **WHEN** the `messages` array contains no entry with `role = "user"`
- **THEN** `last_user_message` is null
- **AND** the row is still written to Silver (not filtered out)

#### Scenario: response has no text content block
- **WHEN** the response `content` array has no text block (e.g., tool_use only)
- **THEN** `assistant_response` is null
- **AND** the row is still written to Silver

---

## Gold — Daily Metrics

### Requirement: Gold daily metrics aggregates per user per day

`gold_user_daily_metrics` SHALL be a DLT Materialized View that aggregates Silver rows by `requester` and `usage_date`.

#### Scenario: user makes multiple requests on the same day
- **WHEN** a requester has 5 Silver rows on the same `usage_date`
- **THEN** `gold_user_daily_metrics` has one row for that requester + date
- **AND** `request_count = 5`
- **AND** `total_input_tokens` = sum of all 5 `input_tokens` values
- **AND** `total_output_tokens` = sum of all 5 `output_tokens` values
- **AND** `first_request` = earliest `request_time` of the 5
- **AND** `last_request` = latest `request_time` of the 5

#### Scenario: user uses multiple models on the same day
- **WHEN** a requester's requests on one day span two different models
- **THEN** `models_used` contains both model names as a set

#### Scenario: no requests on a given day
- **WHEN** a requester has no Silver rows for a date
- **THEN** no row exists in `gold_user_daily_metrics` for that requester + date

---

## Gold — Interaction Summaries

### Requirement: Gold summaries generate one AI summary per Silver request

`gold_interaction_summaries` SHALL be a DLT Materialized View that calls `ai_query()` on each Silver row to produce:
1. `interaction_summary` — a 1-3 sentence plain-language description of what the user asked and what Claude did
2. `task_type` — a classification of the interaction type (one of: `debugging`, `new-feature`, `refactor`, `question`, `explanation`, `other`)

#### Scenario: user asks Claude to fix a bug
- **WHEN** `last_user_message` describes a bug fix request and `assistant_response` contains corrected code
- **THEN** `interaction_summary` describes the bug being fixed in plain language
- **AND** `task_type = "debugging"`

#### Scenario: null last_user_message
- **WHEN** `last_user_message` is null
- **THEN** `interaction_summary` is null
- **AND** `task_type` is null
- **AND** no `ai_query()` call is made for that row

#### Scenario: null assistant_response
- **WHEN** `assistant_response` is null but `last_user_message` is not null
- **THEN** `ai_query()` is called with the user message alone
- **AND** `interaction_summary` is populated based on the request content

---

## Bundle Configuration

### Requirement: Pipeline is deployable via Databricks Asset Bundle

The pipeline SHALL be defined as a resource in `databricks.yml` and deployable with `databricks bundle deploy`.

#### Scenario: deploying the bundle
- **WHEN** `databricks bundle deploy` is run with `--var inference_table=catalog.schema.endpoint_payload`
- **THEN** the DLT pipeline is created or updated in the target workspace
- **AND** the budget app is created or updated in the target workspace
- **AND** both resources are managed under the same bundle

#### Scenario: inference_table variable not provided
- **WHEN** `databricks bundle deploy` is run without setting `inference_table`
- **THEN** the bundle deploy fails with a clear error indicating the variable is required
- **AND** no partial resources are created

### Requirement: Pipeline runs on a trigger schedule

The pipeline SHALL be configured with a triggered execution mode (not continuous) with a configurable schedule defaulting to hourly.

#### Scenario: pipeline trigger fires
- **WHEN** the scheduled trigger fires
- **THEN** the pipeline processes all new Bronze rows since the last run
- **AND** Gold Materialized Views are refreshed
- **AND** `ai_query()` is called only for rows not yet summarized
