"""
Claude Usage ETL Pipeline
=========================
DLT (Spark Declarative Pipeline) that ingests AI Gateway inference table data
and produces per-user, per-day Claude analytics with AI-generated summaries.

Layers:
  Bronze  — raw inference table payload (streaming)
  Silver  — parsed + filtered requests (streaming)
  Gold    — per-user daily metrics + per-interaction AI summaries (materialized views)

Configuration:
  Set the INFERENCE_TABLE Spark conf in the pipeline config:
    spark.claude_analytics.inference_table = catalog.schema.endpoint_payload

  Or pass via the `inference_table` bundle variable (see databricks.yml).
"""

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import StringType


def _get_inference_table() -> str:
    return spark.conf.get("spark.claude_analytics.inference_table")


# ── Bronze ────────────────────────────────────────────────────────────────────


@dlt.table(
    name="bronze_inference_payload",
    comment="Raw AI Gateway inference table payload — append-only, no transformations.",
    table_properties={"quality": "bronze"},
)
def bronze_inference_payload():
    return spark.readStream.format("delta").table(_get_inference_table())


# ── Silver ────────────────────────────────────────────────────────────────────


@dlt.table(
    name="silver_parsed_requests",
    comment="Parsed Claude requests: JSON columns extracted to structured fields. 200s only.",
    table_properties={"quality": "silver"},
)
@dlt.expect("valid_requester", "requester IS NOT NULL")
@dlt.expect("valid_request_time", "request_time IS NOT NULL")
def silver_parsed_requests():
    return (
        dlt.read_stream("bronze_inference_payload")
        .filter("status_code = 200")
        .filter("request IS NOT NULL AND response IS NOT NULL")
        .selectExpr(
            "databricks_request_id",
            "requester",
            "request_time",
            "DATE(request_time) AS usage_date",
            "execution_duration_ms AS latency_ms",
            # Extract model from request JSON
            "request:model :: STRING AS model",
            # Extract full messages array (kept as JSON string for ai_query later)
            "request:messages :: STRING AS messages_json",
            # Last user message — find last element where role = 'user'
            """
            (
              SELECT m.content
              FROM (
                SELECT explode(from_json(request:messages :: STRING, 'ARRAY<STRUCT<role: STRING, content: STRING>>')) AS m
              )
              WHERE m.role = 'user'
              ORDER BY m.role DESC
              LIMIT 1
            ) AS last_user_message
            """,
            # First text block from response content array
            "response:content[0].text :: STRING AS assistant_response",
            # Token counts from response usage
            "CAST(response:usage.input_tokens AS BIGINT) AS input_tokens",
            "CAST(response:usage.output_tokens AS BIGINT) AS output_tokens",
        )
    )


# ── Gold — Daily Metrics ──────────────────────────────────────────────────────


@dlt.table(
    name="gold_user_daily_metrics",
    comment="Per-user per-day Claude usage aggregates: request counts, tokens, latency, models.",
    table_properties={"quality": "gold"},
)
def gold_user_daily_metrics():
    return (
        dlt.read("silver_parsed_requests")
        .groupBy("requester", "usage_date")
        .agg(
            F.count("*").alias("request_count"),
            F.sum("input_tokens").alias("total_input_tokens"),
            F.sum("output_tokens").alias("total_output_tokens"),
            (F.sum("input_tokens") + F.sum("output_tokens")).alias("total_tokens"),
            F.avg("latency_ms").alias("avg_latency_ms"),
            F.min("latency_ms").alias("min_latency_ms"),
            F.max("latency_ms").alias("max_latency_ms"),
            F.min("request_time").alias("first_request"),
            F.max("request_time").alias("last_request"),
            F.collect_set("model").alias("models_used"),
        )
    )


# ── Gold — Interaction Summaries ──────────────────────────────────────────────


@dlt.table(
    name="gold_interaction_summaries",
    comment="Per-request AI-generated summaries and task classification via ai_query().",
    table_properties={"quality": "gold"},
)
def gold_interaction_summaries():
    base = (
        dlt.read("silver_parsed_requests")
        .filter("last_user_message IS NOT NULL")
        .select(
            "databricks_request_id",
            "requester",
            "request_time",
            "usage_date",
            "model",
            "input_tokens",
            "output_tokens",
            "last_user_message",
            "assistant_response",
        )
    )

    # Build prompt input — include assistant response when available
    with_prompt = base.withColumn(
        "summary_input",
        F.when(
            F.col("assistant_response").isNotNull(),
            F.concat_ws(
                "\n\n",
                F.lit("User message:"),
                F.col("last_user_message"),
                F.lit("Claude's response:"),
                F.col("assistant_response"),
            ),
        ).otherwise(
            F.concat_ws(
                "\n\n",
                F.lit("User message:"),
                F.col("last_user_message"),
            )
        ),
    )

    # Generate summary
    with_summary = with_prompt.withColumn(
        "interaction_summary",
        F.expr(
            """
            ai_query(
              'databricks-meta-llama-3-3-70b-instruct',
              CONCAT(
                'Summarize this Claude Code interaction in 1-2 sentences. ',
                'What was the developer asking for and what did Claude do? ',
                'Be specific and concise.\n\n',
                summary_input
              )
            )
            """
        ),
    )

    # Classify task type
    with_classification = with_summary.withColumn(
        "task_type",
        F.expr(
            """
            ai_query(
              'databricks-meta-llama-3-3-70b-instruct',
              CONCAT(
                'Classify this developer interaction into exactly one category. ',
                'Respond with only the category name, nothing else. ',
                'Categories: debugging, new-feature, refactor, question, explanation, other\n\n',
                summary_input
              )
            )
            """
        ),
    )

    return with_classification.select(
        "databricks_request_id",
        "requester",
        "request_time",
        "usage_date",
        "model",
        "input_tokens",
        "output_tokens",
        "interaction_summary",
        "task_type",
    )
