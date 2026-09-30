import importlib.util
from collections import Counter
from pathlib import Path
from statistics import mean

import pytest
from app.schemas.bigquery import TABLE_SCHEMAS

SCRIPT = Path(__file__).resolve().parents[2] / "data/scripts/generate_data.py"
SPEC = importlib.util.spec_from_file_location("generate_data", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def test_dataset_sizes_labels_and_reproducibility() -> None:
    tables = generator.generate_data()
    assert tables == generator.generate_data()
    assert len(tables["citizen_requests"]) == 500
    assert len(tables["demographics"]) == 50
    assert len(tables["infrastructure"]) == 250
    assert len(tables["government_investments"]) == 250
    assert len({row["district"] for row in tables["demographics"]}) == 10
    for rows in tables.values():
        assert all(row["data_source"] == "SYNTHETIC / DEMO DATA" for row in rows)
    requests = tables["citizen_requests"]
    assert len({row["request_id"] for row in requests}) == 500
    assert {row["language"] for row in requests} == {"English", "Hindi", "Kannada"}
    assert {row["category"] for row in requests} == set(generator.CATEGORIES)


def test_requests_use_location_coordinates_and_valid_values() -> None:
    tables = generator.generate_data()
    locations = {row["location_name"]: row for row in tables["demographics"]}
    for row in tables["citizen_requests"]:
        location = locations[row["location_name"]]
        assert row["district"] == location["district"]
        assert (row["latitude"], row["longitude"]) == (
            location["latitude"], location["longitude"]
        )
        assert 0 <= row["urgency"] <= 1
        assert row["original_text"]
        assert row["created_at"].endswith("+00:00")
    for row in tables["infrastructure"]:
        assert row["available_capacity"] <= row["required_capacity"]
        assert row["capacity_unit"]
        assert 0 <= row["coverage_percent"] <= 100


def test_population_and_underservice_influence_demand() -> None:
    tables = generator.generate_data()
    counts = Counter(row["location_name"] for row in tables["citizen_requests"])
    locations = sorted(tables["demographics"], key=lambda row: row["population"])
    assert mean(counts[row["location_name"]] for row in locations[-15:]) > mean(
        counts[row["location_name"]] for row in locations[:15]
    )
    assert generator.demand_weight(10000, 0.2) > generator.demand_weight(10000, 0.8)
    assert generator.demand_weight(20000, 0.5) > generator.demand_weight(10000, 0.5)
    investments = {
        (row["location_name"], row["category"]): row
        for row in tables["government_investments"]
    }
    infrastructure = sorted(tables["infrastructure"], key=lambda row: row["coverage_percent"])
    def funding_ratio(row: dict) -> float:
        funding = investments[row["location_name"], row["category"]]
        return funding["investment_inr"] / funding["estimated_need_inr"]
    assert mean(map(funding_ratio, infrastructure[:50])) < mean(
        map(funding_ratio, infrastructure[-50:])
    )


def test_csv_serialization_is_unicode_and_schema_ordered() -> None:
    tables = generator.generate_data()
    for table_name, rows in tables.items():
        content = generator.serialize_csv(rows)
        assert content.splitlines()[0].split(",") == list(rows[0])
        assert list(rows[0]) == [field.name for field in TABLE_SCHEMAS[table_name]]
        assert "SYNTHETIC / DEMO DATA" in content
    assert any(ord(character) > 127 for character in generator.serialize_csv(tables["citizen_requests"]))


def test_rejects_invalid_request_count() -> None:
    with pytest.raises(ValueError):
        generator.generate_data(request_count=0)


def test_karnataka_profile_uses_sourced_geography_and_synthetic_measures() -> None:
    tables = generator.generate_karnataka_data()
    assert tables == generator.generate_karnataka_data()
    expected = {
        'Melukote': ('Mandya', 12.659444, 76.648333),
        'Halebidu': ('Hassan', 13.2157, 75.9914),
        'Hampi': ('Vijayanagara', 15.334444, 76.462222),
        'Banavasi': ('Uttara Kannada', 14.5341, 75.0177),
    }
    assert len(tables['demographics']) == 4
    assert len(tables['infrastructure']) == 20
    assert len(tables['government_investments']) == 20
    assert len(tables['citizen_requests']) == 846
    for table_name, rows in tables.items():
        for row in rows:
            assert row['data_source'] == generator.DATA_SOURCE
            assert row['district'] == expected[row['location_name']][0]
            assert 'Demo Village' not in str(row)
            assert list(row) == [field.name for field in TABLE_SCHEMAS[table_name]]
            if 'latitude' in row:
                assert (row['latitude'], row['longitude']) == expected[row['location_name']][1:]
    requests = tables['citizen_requests']
    assert len({row['request_id'] for row in requests}) == len(requests)
    assert all(row['location_name'] in row['original_text'] for row in requests)
    counts = Counter((row['location_name'], row['category']) for row in requests)
    assert sum(count > 20 for count in counts.values()) >= 8
    assert {row['language'] for row in requests} == set(generator.TEMPLATES)


def test_statewide_profile_covers_directory_and_each_district_without_placeholder_names():
    places = [
        {'location_name': 'Whitefield', 'district': 'Bengaluru Urban', 'latitude': 12.97, 'longitude': 77.715, 'source': 'verified'},
        {'location_name': 'Varthur', 'district': 'Bengaluru Urban', 'latitude': 12.940699, 'longitude': 77.746596, 'source': 'verified'},
        {'location_name': 'Melukote', 'district': 'Mandya', 'latitude': 12.659444, 'longitude': 76.648333, 'source': 'verified'},
    ]
    tables = generator.generate_statewide_data(places)
    assert tables == generator.generate_statewide_data(places)
    assert len(tables['demographics']) == 3
    assert len(tables['infrastructure']) == len(tables['government_investments']) == 15
    counts = Counter((row['location_name'], row['category']) for row in tables['citizen_requests'])
    assert all(counts[place['location_name'], category] > 20 for place in places for category in generator.CATEGORIES)
    assert len({row['request_id'] for row in tables['citizen_requests']}) == len(tables['citizen_requests'])
    for table, rows in tables.items():
        assert all(list(row) == [field.name for field in TABLE_SCHEMAS[table]] for row in rows)
        assert all(row['data_source'] == generator.DATA_SOURCE for row in rows)
        assert all(not row['location_name'].startswith('Demo Village') for row in rows)


@pytest.mark.parametrize('places', [[], [{'location_name': 'Demo Village 1', 'district': 'Mandya', 'latitude': 12.6, 'longitude': 76.6}]])
def test_statewide_profile_rejects_empty_or_placeholder_directory(places):
    with pytest.raises(ValueError):
        generator.generate_statewide_data(places)


def test_demo_demand_is_reproducible_and_creates_eight_eligible_groups() -> None:
    rows = generator.generate_demo_requests()
    assert rows == generator.generate_demo_requests()
    assert len(rows) == 346
    assert len({row['request_id'] for row in rows}) == len(rows)
    assert all(row['request_id'].startswith('SYN-DEMO-V1-') for row in rows)
    counts = Counter((row['location_name'], row['category']) for row in rows)
    assert len(counts) == 8 and min(counts.values()) > 20
    assert {row['category'] for row in rows} == set(generator.CATEGORIES)
    assert {row['language'] for row in rows} == set(generator.TEMPLATES)
    tables = generator.generate_data()
    locations = {row['location_name']: row for row in tables['demographics']}
    infrastructure = {(row['location_name'], row['category']) for row in tables['infrastructure']}
    for row in rows:
        assert row['data_source'] == generator.DATA_SOURCE
        assert row['confidence'] is None
        assert (row['location_name'], row['category']) in infrastructure
        assert row['district'] == locations[row['location_name']]['district']
        assert row['latitude'] == locations[row['location_name']]['latitude']
        assert row['longitude'] == locations[row['location_name']]['longitude']
        assert list(row) == [field.name for field in TABLE_SCHEMAS['citizen_requests']]
    assert not {row['request_id'] for row in rows} & {row['request_id'] for row in tables['citizen_requests']}


@pytest.mark.parametrize('demo_demand, karnataka, expected_files', [(False, False, 4), (True, False, 1), (False, True, 4)])
def test_generator_cli_isolates_output(monkeypatch: pytest.MonkeyPatch, demo_demand: bool, karnataka: bool, expected_files: int) -> None:
    from argparse import Namespace
    from unittest.mock import MagicMock

    output = MagicMock()
    monkeypatch.setattr(generator.argparse.ArgumentParser, "parse_args", lambda self: Namespace(
        seed=42, output_dir=output, demo_demand=demo_demand, karnataka=karnataka,
    ))
    generator.main()
    assert output.__truediv__.call_count == expected_files
    for call in output.__truediv__.return_value.write_text.call_args_list:
        assert call.kwargs["encoding"] == "utf-8"
        assert "SYNTHETIC / DEMO DATA" in call.args[0]