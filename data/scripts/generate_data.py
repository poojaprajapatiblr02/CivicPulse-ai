"""Generate reproducible SYNTHETIC / DEMO DATA; no real citizen records."""

import argparse
import csv
import io
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA_SOURCE = "SYNTHETIC / DEMO DATA"
KARNATAKA_LOCATIONS = [
    {"location_name": "Melukote", "district": "Mandya", "latitude": 12.659444, "longitude": 76.648333},
    {"location_name": "Halebidu", "district": "Hassan", "latitude": 13.2157, "longitude": 75.9914},
    {"location_name": "Hampi", "district": "Vijayanagara", "latitude": 15.334444, "longitude": 76.462222},
    {"location_name": "Banavasi", "district": "Uttara Kannada", "latitude": 14.5341, "longitude": 75.0177},
]
CATEGORIES = {
    "Healthcare": ("Primary Health Centre", "people served", 5000, 2500),
    "Education": ("School", "student seats", 400, 10000),
    "Roads": ("Road Repair", "road kilometres", 5, 1500000),
    "Water": ("Water Supply", "household connections", 500, 15000),
    "Electricity": ("Power Supply", "household connections", 500, 12000),
}
TEMPLATES = {
    "English": {
        "Healthcare": "We need a nearby primary health centre in {location}.",
        "Education": "Our children need more classrooms in {location}.",
        "Roads": "Please repair the damaged roads in {location}.",
        "Water": "We need a reliable drinking water supply in {location}.",
        "Electricity": "Please address frequent power cuts in {location}.",
    },
    "Hindi": {
        "Healthcare": "{location} में हमें नजदीक प्राथमिक स्वास्थ्य केंद्र चाहिए।",
        "Education": "{location} में हमारे बच्चों के लिए अधिक कक्षाओं की जरूरत है।",
        "Roads": "कृपया {location} में खराब सड़कों की मरम्मत करें।",
        "Water": "{location} में हमें नियमित पेयजल आपूर्ति चाहिए।",
        "Electricity": "कृपया {location} में बार-बार बिजली कटौती की समस्या दूर करें।",
    },
    "Kannada": {
        "Healthcare": "{location} ನಲ್ಲಿ ನಮಗೆ ಹತ್ತಿರದ ಪ್ರಾಥಮಿಕ ಆರೋಗ್ಯ ಕೇಂದ್ರ ಬೇಕು.",
        "Education": "{location} ನಲ್ಲಿ ನಮ್ಮ ಮಕ್ಕಳಿಗೆ ಹೆಚ್ಚಿನ ತರಗತಿ ಕೊಠಡಿಗಳು ಬೇಕು.",
        "Roads": "ದಯವಿಟ್ಟು {location} ನಲ್ಲಿ ಹಾಳಾದ ರಸ್ತೆಗಳನ್ನು ಸರಿಪಡಿಸಿ.",
        "Water": "{location} ನಲ್ಲಿ ನಮಗೆ ನಿಯಮಿತ ಕುಡಿಯುವ ನೀರಿನ ಪೂರೈಕೆ ಬೇಕು.",
        "Electricity": "ದಯವಿಟ್ಟು {location} ನಲ್ಲಿ ಪದೇ ಪದೇ ವಿದ್ಯುತ್ ಕಡಿತವನ್ನು ಪರಿಹರಿಸಿ.",
    },
}


def demand_weight(population: int, coverage: float) -> float:
    return population * (0.2 + 1 - coverage)


def generate_data(
    seed: int = 42, request_count: int = 500, *, locations: list[dict[str, Any]] | None = None
) -> dict[str, list[dict[str, Any]]]:
    if request_count < 1:
        raise ValueError("request_count must be positive")
    rng = random.Random(seed)
    tables: dict[str, list[dict[str, Any]]] = {
        name: [] for name in (
            "citizen_requests", "demographics", "infrastructure", "government_investments"
        )
    }
    candidates = []
    weights = []
    for location_index in range(len(locations) if locations is not None else 50):
        district_index = location_index // 5
        population = rng.randint(2000, 30000)
        households = math.ceil(population / 4.5)
        vulnerability = round(rng.uniform(0.15, 0.9), 3)
        location = dict(locations[location_index]) if locations is not None else {
            "location_name": f"Demo Village {location_index + 1:02d}",
            "district": f"Demo District {district_index + 1:02d}",
            "latitude": round(12.2 + district_index * 0.27 + (location_index % 5) * 0.025, 5),
            "longitude": round(75.1 + (district_index % 4) * 0.52 + (location_index % 5) * 0.04, 5),
        }
        tables["demographics"].append({
            **location, "population": population, "households": households,
            "vulnerability_index": vulnerability, "data_source": DATA_SOURCE,
        })
        service_baseline = rng.uniform(0.15, 0.9)
        for category, (sub_category, unit, capacity_per_asset, cost_per_unit) in CATEGORIES.items():
            coverage = min(0.97, max(0.08, service_baseline + rng.uniform(-0.15, 0.15)))
            required = {
                "Healthcare": population, "Education": math.ceil(population * 0.2),
                "Roads": round(population / 800, 2),
                "Water": households, "Electricity": households,
            }[category]
            available = round(required * coverage, 2)
            key = {"location_name": location["location_name"], "district": location["district"], "category": category}
            tables["infrastructure"].append({
                "infrastructure_id": f"SYN-INF-{len(candidates) + 1:04d}", **key,
                "asset_type": sub_category, "asset_count": math.ceil(available / capacity_per_asset),
                "available_capacity": available, "required_capacity": required,
                "capacity_unit": unit, "coverage_percent": round(coverage * 100, 2),
                "average_distance_km": round(1 + (1 - coverage) * 15, 2) if category in ("Healthcare", "Education") else None,
                "service_hours_per_day": round(4 + coverage * 20, 2) if category in ("Water", "Electricity") else None,
                "road_condition_score": round(coverage * 100, 2) if category == "Roads" else None,
                "data_source": DATA_SOURCE,
            })
            estimated_need = round(required * cost_per_unit, 2)
            funding_ratio = min(0.95, max(0.05, coverage * rng.uniform(0.65, 0.95)))
            tables["government_investments"].append({
                "investment_id": f"SYN-INV-{len(candidates) + 1:04d}", **key,
                "financial_year": "2026-27", "investment_inr": round(estimated_need * funding_ratio, 2),
                "estimated_need_inr": estimated_need, "currency": "INR", "data_source": DATA_SOURCE,
            })
            candidates.append((location, category, sub_category, coverage, vulnerability))
            weights.append(demand_weight(population, coverage))

    total_weight = sum(weights)
    expected_counts = [weight / total_weight * request_count for weight in weights]
    counts = [math.floor(expected) for expected in expected_counts]
    remainder_order = sorted(range(len(counts)), key=lambda index: expected_counts[index] - counts[index], reverse=True)
    for index in remainder_order[:request_count - sum(counts)]:
        counts[index] += 1
    languages = list(TEMPLATES)
    for candidate, count in zip(candidates, counts, strict=True):
        location, category, sub_category, coverage, vulnerability = candidate
        for _ in range(count):
            request_number = len(tables["citizen_requests"]) + 1
            language = languages[(request_number - 1) % len(languages)]
            created_at = datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(
                days=rng.randrange(60), minutes=rng.randrange(1440)
            )
            tables["citizen_requests"].append({
                "request_id": f"SYN-REQ-{request_number:04d}",
                "original_text": TEMPLATES[language][category].format(location=location["location_name"]),
                "language": language, "category": category, "sub_category": sub_category,
                "problem": TEMPLATES["English"][category].format(location=location["location_name"]),
                **location,
                "urgency": round(min(1, max(0, 0.15 + (1 - coverage) * 0.6 + vulnerability * 0.2)), 3),
                "created_at": created_at.isoformat(), "data_source": DATA_SOURCE,
                "confidence": None,
            })
    return tables


def generate_demo_requests(
    tables: dict[str, list[dict[str, Any]]] | None = None,
    scenarios: list[tuple[int, str, int]] | None = None,
) -> list[dict[str, Any]]:
    tables = generate_data() if tables is None else tables
    locations = {row['location_name']: row for row in tables['demographics']}
    assets = {(row['location_name'], row['category']): row for row in tables['infrastructure']}
    scenarios = scenarios if scenarios is not None else [
        (17, 'Healthcare', 60), (17, 'Water', 45), (4, 'Education', 40),
        (9, 'Roads', 36), (26, 'Electricity', 32), (38, 'Water', 55),
        (43, 'Healthcare', 48), (50, 'Education', 30),
    ]
    rows = []
    languages = list(TEMPLATES)
    for scenario, (village, category, count) in enumerate(scenarios, start=1):
        name = tables['demographics'][village - 1]['location_name']
        location = locations[name]
        infrastructure = assets[name, category]
        coverage = infrastructure['available_capacity'] / infrastructure['required_capacity']
        for index in range(count):
            language = languages[index % len(languages)]
            age = 35 + index % 20 if index % 4 == 0 else 1 + index % 25
            created_at = datetime(2026, 9, 20, 12, tzinfo=timezone.utc) - timedelta(days=age, minutes=index)
            rows.append({
                'request_id': f'SYN-DEMO-V1-{scenario:02d}-{index + 1:03d}',
                'original_text': TEMPLATES[language][category].format(location=name),
                'language': language, 'category': category, 'sub_category': CATEGORIES[category][0],
                'problem': TEMPLATES['English'][category].format(location=name),
                **{key: location[key] for key in ('location_name', 'district', 'latitude', 'longitude')},
                'urgency': round(min(1, max(0, 0.15 + (1 - coverage) * 0.6 + location['vulnerability_index'] * 0.2)), 3),
                'created_at': created_at.isoformat(), 'data_source': DATA_SOURCE, 'confidence': None,
            })
    return rows


def generate_karnataka_data() -> dict[str, list[dict[str, Any]]]:
    tables = generate_data(locations=KARNATAKA_LOCATIONS)
    tables['citizen_requests'].extend(generate_demo_requests(tables, [
        (1, 'Healthcare', 60), (1, 'Water', 45), (2, 'Education', 40),
        (2, 'Roads', 36), (3, 'Electricity', 32), (3, 'Water', 55),
        (4, 'Healthcare', 48), (4, 'Education', 30),
    ]))
    return tables


def generate_statewide_data(directory: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    locations = [{key: row[key] for key in ('location_name', 'district', 'latitude', 'longitude')} for row in directory]
    if not locations or any(row['location_name'].casefold().startswith(('demo village', 'demo district')) for row in locations):
        raise ValueError('A sourced non-placeholder directory is required')
    if len({row['location_name'].casefold() for row in locations}) != len(locations):
        raise ValueError('Directory requires unambiguous location labels')
    tables = generate_data(locations=locations, request_count=5000)
    district_indices = {}
    selected = set()
    for index, row in enumerate(locations, start=1):
        district_indices.setdefault(row['district'], index)
        if row['location_name'] in {'Whitefield', 'Varthur', 'Melukote', 'Halebidu', 'Hampi', 'Banavasi'}:
            selected.add(index)
    selected.update(district_indices.values())
    scenarios = [(index, category, 32 + (index + category_index) % 25)
                 for index in sorted(selected) for category_index, category in enumerate(CATEGORIES)]
    tables['citizen_requests'].extend(generate_demo_requests(tables, scenarios))
    for row in tables['citizen_requests']:
        row['request_id'] = row['request_id'].replace('SYN-REQ-', 'SYN-KA-REQ-').replace('SYN-DEMO-V1-', 'SYN-KA-DEMAND-')
    return tables


def serialize_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument("--demo-demand", action="store_true", help="Write only the canonical seed-42 demo demand supplement")
    profile.add_argument("--karnataka", action="store_true", help="Write the seed-42 Karnataka geography demo profile")
    profile.add_argument('--statewide-geography', type=Path, help='Generate planning data for a sourced statewide directory CSV')
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "synthetic")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tables = generate_karnataka_data() if args.karnataka else (
        {"demo_requests": generate_demo_requests()} if args.demo_demand else generate_data(seed=args.seed)
    )
    if getattr(args, 'statewide_geography', None):
        with args.statewide_geography.open(encoding='utf-8', newline='') as source:
            directory = list(csv.DictReader(source))
        for row in directory:
            row['latitude'], row['longitude'] = float(row['latitude']), float(row['longitude'])
        tables = generate_statewide_data(directory)
    for table_name, rows in tables.items():
        (args.output_dir / f"{table_name}.csv").write_text(serialize_csv(rows), encoding="utf-8", newline="")
        print(f"{table_name}: {len(rows)} rows ({DATA_SOURCE})")


if __name__ == "__main__":
    main()