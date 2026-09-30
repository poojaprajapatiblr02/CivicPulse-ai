"""Export schemas, provision tables, or load the four synthetic seed datasets."""

import argparse
import json
from pathlib import Path

from google.cloud import bigquery

from app.core.config import get_bigquery_settings
from app.schemas.bigquery import DATA_SOURCE, TABLE_SCHEMAS
from app.services.bigquery_service import BigQueryService

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SEED_TABLES = tuple(name for name in TABLE_SCHEMAS if name not in {"hotspots", "infrastructure_gaps", "recommendations"})


def export_schemas(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, fields in TABLE_SCHEMAS.items():
        (destination / f"{name}.json").write_text(
            json.dumps([field.to_api_repr() for field in fields], indent=2) + "\n", encoding="utf-8"
        )


def schema_signature(fields: list[bigquery.SchemaField]) -> list[tuple[str, str, str]]:
    aliases = {"INT64": "INTEGER", "FLOAT64": "FLOAT"}
    return [(field.name, aliases.get(field.field_type, field.field_type), field.mode) for field in fields]


def ensure_tables(service: BigQueryService) -> None:
    settings = service.settings
    dataset = bigquery.Dataset(f"{settings.project_id}.{settings.dataset}")
    dataset.location = settings.location
    dataset.description = f"CivicPulse AI POC: {DATA_SOURCE}. Not government data."
    dataset.labels = {"data_source": "synthetic"}
    existing = service.client.create_dataset(dataset, exists_ok=True, timeout=30)
    if existing.location.lower() != settings.location.lower():
        raise ValueError("Existing dataset location differs from BIGQUERY_LOCATION")
    if existing.labels.get("data_source") != "synthetic":
        raise ValueError("Refusing to use a dataset not labeled synthetic")
    for name, fields in TABLE_SCHEMAS.items():
        table = bigquery.Table(service.table_id(name), schema=fields)
        table.description = f"{DATA_SOURCE}: fictional {name}; not government statistics."
        table.labels = {"data_source": "synthetic"}
        existing_table = service.client.create_table(table, exists_ok=True, timeout=30)
        if schema_signature(existing_table.schema) != schema_signature(fields):
            legacy_fields = [
                bigquery.SchemaField(field.name, field.field_type, mode="REQUIRED")
                for field in fields if field.name != "confidence"
            ]
            if name != "citizen_requests" or schema_signature(existing_table.schema) != schema_signature(legacy_fields):
                raise ValueError("Existing table schema does not match a supported schema")
            existing_table.schema = fields
            migrated = service.client.update_table(existing_table, ["schema"], timeout=30)
            if schema_signature(migrated.schema) != schema_signature(fields):
                raise ValueError("Request schema migration was not confirmed")


def load_csv(service: BigQueryService, table_name: str, path: Path) -> int:
    table_id = service.table_id(table_name)
    config = bigquery.LoadJobConfig(
        schema=TABLE_SCHEMAS[table_name], source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1, encoding="UTF-8", max_bad_records=0,
        write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,
        create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
    )
    with path.open("rb") as source:
        job = service.client.load_table_from_file(
            source, table_id, job_config=config, location=service.settings.location, timeout=30,
        )
    job.result(timeout=120)
    return int(job.output_rows or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-schemas", action="store_true", help="Write schema JSON locally; no cloud access")
    parser.add_argument("--load", action="store_true", help="Load synthetic CSV files into empty tables only")
    parser.add_argument("--karnataka-demo", action="store_true", help="Use the Karnataka profile; requires a dataset ending in _karnataka")
    parser.add_argument("--table", choices=list(SEED_TABLES), help="Load only this seed table, e.g. after a partial setup")
    args = parser.parse_args()
    try:
        if args.export_schemas:
            export_schemas(PROJECT_ROOT / "data/schemas")
            print(f"Exported {len(TABLE_SCHEMAS)} explicit BigQuery schema files.")
            return 0
        settings = get_bigquery_settings()
        if args.karnataka_demo and not settings.dataset.endswith('_karnataka'):
            raise ValueError('Karnataka profile requires an isolated _karnataka dataset')
        service = BigQueryService(settings)
        ensure_tables(service)
        if args.load:
            source = PROJECT_ROOT / 'data/synthetic'
            if args.karnataka_demo:
                source = source / 'karnataka'
            names = [args.table] if args.table else list(SEED_TABLES)
            for name in names:
                count = load_csv(service, name, source / f"{name}.csv")
                print(f"Loaded {name}: {count} rows ({DATA_SOURCE})")
        else:
            print(f"Synthetic dataset and {len(TABLE_SCHEMAS)} explicit-schema tables are ready.")
        return 0
    except Exception as error:
        print(f"BigQuery setup failed ({type(error).__name__}). Check ADC, IAM, location, schemas, and empty-table requirements.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())