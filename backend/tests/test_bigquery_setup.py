import io
import json
from argparse import Namespace
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from app.core.config import BigQuerySettings
from app.schemas.bigquery import TABLE_SCHEMAS
from app.services.bigquery_service import BigQueryService
from app.services.bigquery_setup import ensure_tables, export_schemas, load_csv
from app.services import bigquery_setup


@pytest.fixture
def service() -> BigQueryService:
    client = MagicMock()
    client.create_dataset.return_value.location = "asia-south1"
    client.create_dataset.return_value.labels = {"data_source": "synthetic"}
    client.create_table.side_effect = lambda table, **kwargs: table
    return BigQueryService(BigQuerySettings(project_id="demo-project"), client=client)


def test_create_dataset_and_tables(service: BigQueryService) -> None:
    ensure_tables(service)
    call = service.client.create_dataset.call_args
    assert call.kwargs["exists_ok"] is True
    assert call.args[0].labels == {"data_source": "synthetic"}
    assert service.client.create_table.call_count == len(TABLE_SCHEMAS)


def test_reject_existing_location_mismatch(service: BigQueryService) -> None:
    service.client.create_dataset.return_value.location = "US"
    with pytest.raises(ValueError, match="location"):
        ensure_tables(service)
    service.client.create_table.assert_not_called()


def test_refuse_unlabeled_dataset(service: BigQueryService) -> None:
    service.client.create_dataset.return_value.labels = {}
    with pytest.raises(ValueError, match="synthetic"):
        ensure_tables(service)


def test_refuse_schema_mismatch(service: BigQueryService) -> None:
    service.client.create_table.side_effect = None
    service.client.create_table.return_value.schema = []
    with pytest.raises(ValueError, match="schema"):
        ensure_tables(service)


def test_migrate_requests_without_replacing_rows(service: BigQueryService) -> None:
    old_fields = []
    for field in TABLE_SCHEMAS["citizen_requests"]:
        if field.name == "confidence":
            continue
        definition = dict(field.to_api_repr())
        definition["mode"] = "REQUIRED"
        old_fields.append(bigquery.SchemaField.from_api_repr(definition))
    existing = bigquery.Table(service.table_id("citizen_requests"), schema=old_fields)
    service.client.create_table.side_effect = lambda table, **kwargs: existing if table.table_id == "citizen_requests" else table
    service.client.update_table.side_effect = lambda table, fields, **kwargs: table
    ensure_tables(service)
    service.client.update_table.assert_called_once_with(existing, ["schema"], timeout=30)
    assert existing.schema == TABLE_SCHEMAS["citizen_requests"]
    fields = {field.name: field for field in existing.schema}
    assert fields["confidence"].mode == "NULLABLE"
    assert all(fields[name].mode == "NULLABLE" for name in ("location_name", "district", "latitude", "longitude"))
    service.client.delete_table.assert_not_called()
    service.client.load_table_from_json.assert_not_called()
    service.client.load_table_from_file.assert_not_called()
    ensure_tables(service)
    assert service.client.update_table.call_count == 1


def test_migration_requires_confirmed_schema(service: BigQueryService) -> None:
    legacy = bigquery.Table(service.table_id("citizen_requests"), schema=[
        bigquery.SchemaField(field.name, field.field_type, mode="REQUIRED")
        for field in TABLE_SCHEMAS["citizen_requests"] if field.name != "confidence"
    ])
    service.client.create_table.return_value = legacy
    service.client.create_table.side_effect = None
    service.client.update_table.return_value.schema = []
    with pytest.raises(ValueError, match="not confirmed"):
        ensure_tables(service)


def test_load_is_empty_only_and_schema_checked(service: BigQueryService) -> None:
    path = MagicMock()
    path.open.return_value.__enter__.return_value = io.BytesIO(b"synthetic csv")
    service.client.load_table_from_file.return_value.output_rows = 500
    assert load_csv(service, "citizen_requests", path) == 500
    config = service.client.load_table_from_file.call_args.kwargs["job_config"]
    assert config.write_disposition == "WRITE_EMPTY"
    assert config.source_format == "CSV"
    assert config.schema == TABLE_SCHEMAS["citizen_requests"]
    assert config.skip_leading_rows == 1
    assert config.max_bad_records == 0
    assert config.create_disposition == "CREATE_NEVER"


def test_load_failure_is_not_ignored(service: BigQueryService) -> None:
    path = MagicMock()
    service.client.load_table_from_file.return_value.result.side_effect = RuntimeError("failed")
    with pytest.raises(RuntimeError):
        load_csv(service, "citizen_requests", path)


def test_export_schemas_matches_runtime_schema() -> None:
    destination = MagicMock()
    export_schemas(destination)
    assert destination.__truediv__.call_count == len(TABLE_SCHEMAS)
    for table_name, call in zip(TABLE_SCHEMAS, destination.__truediv__.return_value.write_text.call_args_list):
        fields = json.loads(call.args[0])
        assert fields == [field.to_api_repr() for field in TABLE_SCHEMAS[table_name]]


@pytest.mark.parametrize(
    ("export", "load", "table", "expected_loads"),
    [(True, False, None, 0), (False, False, None, 0),
     (False, True, None, 4), (False, True, "demographics", 1)],
)
def test_setup_cli(
    monkeypatch: pytest.MonkeyPatch, export: bool, load: bool, table: str | None,
    expected_loads: int,
) -> None:
    monkeypatch.setattr(bigquery_setup.argparse.ArgumentParser, "parse_args", lambda self: Namespace(
        export_schemas=export, load=load, table=table, karnataka_demo=False,
    ))
    export_mock = MagicMock()
    ensure_mock = MagicMock()
    load_mock = MagicMock(return_value=50)
    monkeypatch.setattr(bigquery_setup, "export_schemas", export_mock)
    monkeypatch.setattr(bigquery_setup, "ensure_tables", ensure_mock)
    monkeypatch.setattr(bigquery_setup, "load_csv", load_mock)
    monkeypatch.setattr(bigquery_setup, "get_bigquery_settings", MagicMock())
    factory = MagicMock()
    monkeypatch.setattr(bigquery_setup, "BigQueryService", factory)
    assert bigquery_setup.main() == 0
    assert load_mock.call_count == expected_loads
    assert all(call.args[1] not in {"hotspots", "infrastructure_gaps", "recommendations"} for call in load_mock.call_args_list)
    if export:
        factory.assert_not_called()
        export_mock.assert_called_once()
    else:
        ensure_mock.assert_called_once()


def test_setup_cli_safe_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(bigquery_setup.argparse.ArgumentParser, "parse_args", lambda self: Namespace(
        export_schemas=False, load=True, table=None, karnataka_demo=False,
    ))
    monkeypatch.setattr(bigquery_setup, "get_bigquery_settings", MagicMock(side_effect=ValueError("private credential")))
    assert bigquery_setup.main() == 1
    output = capsys.readouterr().out
    assert "ValueError" in output
    assert "private credential" not in output


@pytest.mark.parametrize('dataset, expected', [('civicpulse_karnataka', 0), ('civicpulse', 1)])
def test_karnataka_setup_requires_isolated_dataset(monkeypatch: pytest.MonkeyPatch, dataset: str, expected: int) -> None:
    monkeypatch.setattr(bigquery_setup.argparse.ArgumentParser, 'parse_args', lambda self: Namespace(
        export_schemas=False, load=True, table=None, karnataka_demo=True,
    ))
    monkeypatch.setattr(bigquery_setup, 'get_bigquery_settings', lambda: BigQuerySettings(project_id='demo-project', dataset=dataset))
    factory = MagicMock()
    ensure_mock = MagicMock()
    load_mock = MagicMock(return_value=4)
    monkeypatch.setattr(bigquery_setup, 'BigQueryService', factory)
    monkeypatch.setattr(bigquery_setup, 'ensure_tables', ensure_mock)
    monkeypatch.setattr(bigquery_setup, 'load_csv', load_mock)
    assert bigquery_setup.main() == expected
    if expected:
        factory.assert_not_called()
        ensure_mock.assert_not_called()
        load_mock.assert_not_called()
    else:
        assert load_mock.call_count == 4
        assert all(call.args[2].parent.name == 'karnataka' for call in load_mock.call_args_list)