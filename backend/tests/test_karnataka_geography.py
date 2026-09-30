import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'data/scripts/import_karnataka.py'
SPEC = importlib.util.spec_from_file_location('import_karnataka', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
geography = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(geography)


def feature(name='Village', district='Bangalore', taluk='Bangalore South', code='001'):
    return {'properties': {'NAME': name, 'DISTRICT': district, 'TALUK': taluk, 'LOC_CODE': code},
            'geometry': {'type': 'Polygon', 'coordinates': [[[77, 12], [77.1, 12], [77.1, 12.1], [77, 12.1], [77, 12]]]}}


def test_source_points_and_duplicate_names_are_not_fabricated():
    records = geography.convert_features([feature(), feature(district='Mysore', code='002')])
    assert len(records) == 2
    assert len({row['location_name'] for row in records}) == 2
    assert {row['district'] for row in records} == {'Bengaluru Urban', 'Mysuru'}
    assert all(12 <= row['latitude'] <= 12.1 and 77 <= row['longitude'] <= 77.1 for row in records)
    assert all(row['source_code'] in {'001', '002'} for row in records)


@pytest.mark.parametrize('district,taluk,expected', [
    ('Bangalore Rural', 'Ramanagaram', 'Bengaluru South'),
    ('Bangalore Rural', 'Devanhalli', 'Bengaluru Rural'),
    ('Kolar', 'Chintamani', 'Chikkaballapur'), ('Kolar', 'Malur', 'Kolar'),
    ('Gulbarga', 'Shahpur', 'Yadgir'), ('Gulbarga', 'Aland', 'Kalaburagi'),
    ('Bellary', 'Hospet', 'Vijayanagara'), ('Bellary', 'Sandur', 'Ballari'),
    ('Davangere', 'Harapanahalli', 'Vijayanagara'),
])
def test_historical_district_crosswalk(district, taluk, expected):
    assert geography.current_district(district, taluk) == expected


@pytest.mark.parametrize('record', [feature(name='Demo Village 01'), feature(district='Unknown'), feature(name='')])
def test_invalid_geography_is_rejected(record):
    with pytest.raises(ValueError):
        geography.convert_features([record])


def test_bengaluru_localities_have_real_names_and_separate_district():
    places = {row['location_name']: row for row in geography.URBAN_LOCATIONS}
    assert {'Whitefield', 'Varthur'} <= places.keys()
    assert all(row['district'] == 'Bengaluru Urban' for row in places.values())
    assert places['Whitefield']['latitude'] == 12.97
    assert places['Varthur']['longitude'] == 77.746596


def test_non_settlements_are_excluded_and_split_town_polygons_are_preserved():
    records = geography.convert_features([
        feature(name='Water Body', code='5555'),
        feature(name='No Data', code='9999'),
        feature(name='Reserved Forest', code='4444'),
        feature(name='Bangalore Mc', code='01300101', taluk='Bangalore North'),
        feature(name='Bangalore Mc', code='01300101', taluk='Bangalore South'),
        feature(name='Bangalore Mc', code='01300101', taluk='Bangalore South'),
    ])
    assert len(records) == 2
    assert len({row['location_name'] for row in records}) == 2
    assert {row['source_code'] for row in records} == {'01300101'}


def test_conflicting_identity_in_same_source_region_is_rejected():
    with pytest.raises(ValueError, match='Conflicting'):
        geography.convert_features([feature(name='First'), feature(name='Second')])


def test_real_demothi_name_is_not_a_demo_placeholder():
    assert geography.convert_features([feature(name='Demothi')])[0]['location_name'] == 'Demothi'