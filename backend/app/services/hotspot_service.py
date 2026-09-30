from collections import defaultdict
from datetime import datetime, timedelta
import json
from math import fsum
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from google.cloud import bigquery
from pydantic import TypeAdapter, AwareDatetime

from app.core.config import HotspotSettings
from app.schemas.bigquery import DATA_SOURCE
from app.schemas.hotspots import Hotspot, HotspotLocation, HotspotRequest
from app.services.bigquery_service import BigQueryService


def aggregate_hotspots(
    requests: list[dict[str, Any]], locations: list[dict[str, Any]], *, threshold: int, as_of: datetime,
) -> list[Hotspot]:
    settings = HotspotSettings(request_threshold=threshold)
    as_of = TypeAdapter(AwareDatetime).validate_python(as_of)
    location_index: dict[tuple[str, str], HotspotLocation] = {}
    ambiguous: set[tuple[str, str]] = set()
    for record in locations:
        place = HotspotLocation.model_validate(record)
        key = (place.district, place.location_name)
        if key in location_index and location_index[key] != place:
            ambiguous.add(key)
        location_index[key] = place

    groups: dict[tuple[str, str, str], list[HotspotRequest]] = defaultdict(list)
    seen: dict[str, HotspotRequest] = {}
    for record in requests:
        request = HotspotRequest.model_validate(record)
        if request.request_id in seen:
            if seen[request.request_id] != request:
                raise ValueError("Conflicting duplicate request IDs")
            continue
        seen[request.request_id] = request
        if request.district is None or request.location_name is None or request.created_at > as_of:
            continue
        place_key = (request.district, request.location_name)
        if place_key not in location_index or place_key in ambiguous:
            continue
        groups[(*place_key, request.category)].append(request)

    current_start = as_of - timedelta(days=30)
    previous_start = as_of - timedelta(days=60)
    result = []
    for key, records in sorted(groups.items()):
        if len(records) <= settings.request_threshold:
            continue
        place = location_index[key[:2]]
        current = sum(record.created_at >= current_start for record in records)
        previous = sum(previous_start <= record.created_at < current_start for record in records)
        growth = (current - previous) / previous if previous else (None if current else 0.0)
        result.append(Hotspot(
            hotspot_id=str(uuid5(NAMESPACE_URL, "civicpulse:hotspot:" + json.dumps(key, ensure_ascii=True))),
            location_name=place.location_name, district=place.district, category=key[2],
            request_count=len(records), affected_population=place.population,
            average_urgency=fsum(record.urgency for record in records) / len(records),
            demand_growth=growth, latitude=place.latitude, longitude=place.longitude, created_at=as_of,
        ))
    return result


class HotspotService:
    def __init__(self, store: BigQueryService, settings: HotspotSettings) -> None:
        self.store = store
        self.settings = settings

    def detect(self, *, as_of: datetime) -> list[Hotspot]:
        request_columns = ", ".join(HotspotRequest.model_fields)
        location_columns = ", ".join(HotspotLocation.model_fields)
        source = [bigquery.ScalarQueryParameter("source", "STRING", DATA_SOURCE)]
        requests = self.store.execute_query(
            f"SELECT {request_columns} FROM `{self.store.table_id('citizen_requests')}` "
            "WHERE data_source = @source AND created_at <= @as_of",
            [*source, bigquery.ScalarQueryParameter("as_of", "TIMESTAMP", as_of)],
        )
        locations = self.store.execute_query(
            f"SELECT {location_columns} FROM `{self.store.table_id('demographics')}` WHERE data_source = @source", source,
        )
        hotspots = aggregate_hotspots(requests, locations, threshold=self.settings.request_threshold, as_of=as_of)
        self._replace_snapshot(hotspots)
        return hotspots

    def _replace_snapshot(self, hotspots: list[Hotspot]) -> None:
        self.store.replace_snapshot("hotspots", [hotspot.model_dump(mode="json") for hotspot in hotspots])

    def list_hotspots(self, *, limit: int = 1000) -> list[Hotspot]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        columns = ", ".join(Hotspot.model_fields)
        rows = self.store.execute_query(
            f"SELECT {columns} FROM `{self.store.table_id('hotspots')}` ORDER BY request_count DESC, hotspot_id LIMIT @limit",
            [bigquery.ScalarQueryParameter("limit", "INT64", limit)],
        )
        return [Hotspot.model_validate(row) for row in rows]

    def get_hotspot(self, hotspot_id: str) -> Hotspot | None:
        columns = ", ".join(Hotspot.model_fields)
        rows = self.store.execute_query(
            f"SELECT {columns} FROM `{self.store.table_id('hotspots')}` WHERE hotspot_id = @hotspot_id LIMIT 1",
            [bigquery.ScalarQueryParameter("hotspot_id", "STRING", hotspot_id)],
        )
        return Hotspot.model_validate(rows[0]) if rows else None