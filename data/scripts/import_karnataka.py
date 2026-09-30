"""Convert attributed historical Karnataka polygons into a planning geography directory."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from shapely.geometry import GeometryCollection, shape

SOURCE_URL = 'https://github.com/datameet/indian_village_boundaries/blob/master/ka/ka.geojson'
DISTRICTS = {
    'Uttar Kannad': 'Uttara Kannada', 'Udupi': 'Udupi', 'Tumkur': 'Tumakuru',
    'Shimoga': 'Shivamogga', 'Raichur': 'Raichur', 'Mysore': 'Mysuru',
    'Mandya': 'Mandya', 'Koppal': 'Koppal', 'Kolar': 'Kolar', 'Kodagu': 'Kodagu',
    'Haveri': 'Haveri', 'Hassan': 'Hassan', 'Gulbarga': 'Kalaburagi',
    'Gadag': 'Gadag', 'Dharwad': 'Dharwad', 'Davangere': 'Davanagere',
    'Dakshina Kannada': 'Dakshina Kannada', 'Chamarajnagar': 'Chamarajanagar',
    'Chikmagalur': 'Chikkamagaluru', 'Chitradurga': 'Chitradurga',
    'Bangalore': 'Bengaluru Urban', 'Bangalore Rural': 'Bengaluru Rural',
    'Bellary': 'Ballari', 'Bagalkot': 'Bagalkote', 'Bijapur': 'Vijayapura',
    'Belgaum': 'Belagavi', 'Bidar': 'Bidar',
}
SPLITS = {
    'Bengaluru South': ('Bangalore Rural', {'Magadi', 'Ramanagaram', 'Kankapura', 'Channapatna'}),
    'Chikkaballapur': ('Kolar', {'Bagepalli', 'Gauribidanur', 'Gudibanda', 'Chintamani', 'Chikballapur', 'Sidlaghatta'}),
    'Yadgir': ('Gulbarga', {'Yadgir', 'Shahpur', 'Shorapur'}),
    'Vijayanagara': ('Bellary', {'Hospet', 'Hagaribommanahalli', 'Hadagalli', 'Kudligi'}),
}
URBAN_LOCATIONS = [
    {'location_name': 'Whitefield', 'district': 'Bengaluru Urban', 'latitude': 12.97, 'longitude': 77.715,
     'source_code': 'urban-whitefield', 'source_name': 'Whitefield', 'taluk': 'Bengaluru East',
     'source': 'https://en.wikipedia.org/wiki/Whitefield,_Bengaluru'},
    {'location_name': 'Varthur', 'district': 'Bengaluru Urban', 'latitude': 12.940699, 'longitude': 77.746596,
     'source_code': 'urban-varthur', 'source_name': 'Varthur', 'taluk': 'Bengaluru East',
     'source': 'https://en.wikipedia.org/wiki/Varthur'},
]


def current_district(district: str, taluk: str) -> str:
    if district == 'Davangere' and taluk == 'Harapanahalli':
        return 'Vijayanagara'
    for current, (previous, taluks) in SPLITS.items():
        if district == previous and taluk in taluks:
            return current
    if district not in DISTRICTS:
        raise ValueError(f'Unmapped source district: {district}')
    return DISTRICTS[district]


def convert_features(features: list[dict]) -> list[dict]:
    records = []
    regions = {}
    for feature in features:
        properties = feature['properties']
        name = str(properties['NAME'] or '').strip()
        code = str(properties['LOC_CODE'] or '').strip()
        taluk = str(properties['TALUK'] or '').strip()
        if code in {'5555', '9999', '4444'}:
            continue
        if not name or not code or not taluk or name.casefold().startswith(('demo village', 'demo district')):
            raise ValueError('Missing or placeholder source geography')
        polygon = shape(feature['geometry'])
        if polygon.is_empty or polygon.geom_type not in {'Polygon', 'MultiPolygon'}:
            raise ValueError('Village polygon required')
        key = (properties['DISTRICT'], taluk, code)
        if key in regions:
            if regions[key]['name'] != name:
                raise ValueError('Conflicting source location identity')
            regions[key]['polygons'].append(polygon)
        else:
            regions[key] = {'name': name, 'polygons': [polygon]}
    for (district, taluk, code), region in regions.items():
        name = region['name']
        point = GeometryCollection(region['polygons']).representative_point()
        if not 11 <= point.y <= 19 or not 74 <= point.x <= 79:
            raise ValueError('Coordinates outside Karnataka source envelope')
        records.append({
            'location_name': name, 'district': current_district(district, taluk),
            'latitude': round(point.y, 6), 'longitude': round(point.x, 6),
            'source_code': code, 'source_name': name, 'taluk': taluk, 'source': SOURCE_URL,
        })
    counts = Counter(row['location_name'].casefold() for row in records)
    for row in records:
        if counts[row['location_name'].casefold()] > 1:
            row['location_name'] += f" ({row['taluk']}; {row['source_code']})"
        if len(row['location_name']) > 200:
            raise ValueError('Location label exceeds API contract')
    return sorted(records, key=lambda row: (row['district'], row['location_name']))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    rows = convert_features(json.loads(raw)['features'])
    urban_names = {row['location_name'].casefold() for row in URBAN_LOCATIONS}
    rows = [row for row in rows if not (row['district'] == 'Bengaluru Urban' and row['source_name'].casefold() in urban_names)]
    rows.extend(URBAN_LOCATIONS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as destination:
        writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} sourced locations; {len({row["district"] for row in rows})} districts')
    print(f'Source SHA256: {hashlib.sha256(raw).hexdigest()}')


if __name__ == '__main__':
    main()