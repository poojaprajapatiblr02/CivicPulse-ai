"""Explicit BigQuery schemas in CSV column order for synthetic Phase 2 data."""

from google.cloud.bigquery import SchemaField

DATA_SOURCE = "SYNTHETIC / DEMO DATA"
CATEGORIES = ("Healthcare", "Education", "Roads", "Water", "Electricity")
LOCATION_FIELDS = [("location_name", "STRING"), ("district", "STRING")]
COORDINATE_FIELDS = [("latitude", "FLOAT64"), ("longitude", "FLOAT64")]
CATEGORY_FIELDS = [*LOCATION_FIELDS, ("category", "STRING")]
SOURCE_FIELDS = [("data_source", "STRING")]

TABLE_FIELDS = {
    "citizen_requests": [
        ("request_id", "STRING"), ("original_text", "STRING"), ("language", "STRING"),
        ("category", "STRING"), ("sub_category", "STRING"), ("problem", "STRING"),
        *LOCATION_FIELDS, *COORDINATE_FIELDS, ("urgency", "FLOAT64"),
        ("created_at", "TIMESTAMP"), *SOURCE_FIELDS, ("confidence", "FLOAT64"),
    ],
    "demographics": [
        *LOCATION_FIELDS, *COORDINATE_FIELDS, ("population", "INT64"),
        ("households", "INT64"), ("vulnerability_index", "FLOAT64"), *SOURCE_FIELDS,
    ],
    "infrastructure": [
        ("infrastructure_id", "STRING"), *CATEGORY_FIELDS, ("asset_type", "STRING"),
        ("asset_count", "INT64"), ("available_capacity", "FLOAT64"),
        ("required_capacity", "FLOAT64"), ("capacity_unit", "STRING"),
        ("coverage_percent", "FLOAT64"), ("average_distance_km", "FLOAT64"),
        ("service_hours_per_day", "FLOAT64"), ("road_condition_score", "FLOAT64"), *SOURCE_FIELDS,
    ],
    "government_investments": [
        ("investment_id", "STRING"), *CATEGORY_FIELDS, ("financial_year", "STRING"),
        ("investment_inr", "NUMERIC"), ("estimated_need_inr", "NUMERIC"),
        ("currency", "STRING"), *SOURCE_FIELDS,
    ],
    "hotspots": [
        ("hotspot_id", "STRING"), *CATEGORY_FIELDS, ("request_count", "INT64"),
        ("affected_population", "INT64"), ("average_urgency", "FLOAT64"),
        ("demand_growth", "FLOAT64"), *COORDINATE_FIELDS, ("created_at", "TIMESTAMP"),
    ],
}
NULLABLE_FIELDS = {"average_distance_km", "service_hours_per_day", "road_condition_score"}
TABLE_FIELDS["infrastructure_gaps"] = [
    *TABLE_FIELDS["hotspots"],
    ("demand_score", "FLOAT64"), ("infrastructure_gap_score", "FLOAT64"),
    ("population_impact_score", "FLOAT64"), ("vulnerability_score", "FLOAT64"),
    ("urgency_score", "FLOAT64"), ("investment_gap_score", "FLOAT64"), ("priority_score", "FLOAT64"),
    ("available_capacity", "FLOAT64"), ("required_capacity", "FLOAT64"), ("capacity_gap", "FLOAT64"),
    ("capacity_unit", "STRING"), ("vulnerability_index", "FLOAT64"),
    ("investment_inr", "NUMERIC"), ("estimated_need_inr", "NUMERIC"), ("investment_gap_inr", "NUMERIC"),
    ("financial_year", "STRING"), ("data_issues", "STRING"),
    ("max_request_count", "INT64"), ("max_population", "INT64"),
    ("scoring_status", "STRING"), ("scoring_version", "STRING"),
]
NULLABLE_GAP_FIELDS = {
    "demand_growth", "infrastructure_gap_score", "vulnerability_score", "investment_gap_score", "priority_score",
    "available_capacity", "required_capacity", "capacity_gap", "capacity_unit", "vulnerability_index",
    "investment_inr", "estimated_need_inr", "investment_gap_inr", "financial_year", "data_issues",
}
NULLABLE_REQUEST_FIELDS = {"location_name", "district", "latitude", "longitude", "confidence"}
TABLE_FIELDS["recommendations"] = [
    ("recommendation_id", "STRING"), ("hotspot_id", "STRING"),
    ("recommended_intervention", "STRING"), ("reasoning", "STRING"), ("evidence", "STRING"),
    ("expected_impact", "STRING"), ("confidence", "FLOAT64"), ("limitations", "STRING"),
    ("created_at", "TIMESTAMP"), ("evidence_snapshot", "STRING"),
]
REPEATED_RECOMMENDATION_FIELDS = {"reasoning", "evidence", "limitations"}
TABLE_SCHEMAS = {
    table_name: [
        SchemaField(name, field_type, mode="REPEATED" if table_name == "recommendations" and name in REPEATED_RECOMMENDATION_FIELDS else "NULLABLE" if (
            name in NULLABLE_FIELDS or table_name == "citizen_requests" and name in NULLABLE_REQUEST_FIELDS
            or table_name == "hotspots" and name == "demand_growth"
            or table_name == "infrastructure_gaps" and name in NULLABLE_GAP_FIELDS
        ) else "REQUIRED")
        for name, field_type in fields
    ]
    for table_name, fields in TABLE_FIELDS.items()
}