## Implementation Tasks

- [ ] Add `inference_table` variable to root `databricks.yml`
- [ ] Add DLT pipeline resource block to root `databricks.yml`
- [ ] Create `pipeline/dlt_pipeline.py` — Bronze streaming table
- [ ] Create `pipeline/dlt_pipeline.py` — Silver streaming table with JSON parsing
- [ ] Create `pipeline/dlt_pipeline.py` — Gold `gold_user_daily_metrics` materialized view
- [ ] Create `pipeline/dlt_pipeline.py` — Gold `gold_interaction_summaries` materialized view with `ai_query()`
- [ ] Add DLT expectations for data quality (non-null requester, valid status codes)
- [ ] Create `pipeline/README.md` with setup and deployment instructions
- [ ] Test pipeline against a real inference table in dev target
