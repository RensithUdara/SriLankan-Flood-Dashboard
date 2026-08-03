import httpx
import json
import os
from cachetools import TTLCache
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

BASE_URL = "https://raw.githubusercontent.com/nuuuwan/lk_dmc_vis/main"
GAUGE_FEATURE_LAYER_URL = os.getenv(
    "GAUGE_FEATURE_LAYER_URL",
    "https://services3.arcgis.com/J7ZFXmR8rSmQ3FGf/arcgis/rest/services/"
    "gauges_2_view/FeatureServer/0",
).rstrip("/")
LOCAL_GAUGE_JSON_PATH = Path(__file__).resolve().parents[3] / "data" / "gauges_2_view.json"

# Cache data for 15 minutes (900 seconds) - matches pipeline update frequency
cache = TTLCache(maxsize=100, ttl=900)


def cached(key_func):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            if key in cache:
                return cache[key]
            result = await func(*args, **kwargs)
            cache[key] = result
            return result
        return wrapper
    return decorator


async def fetch_json(path: str) -> dict | list | None:
    url = f"{BASE_URL}/{path}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None


def coerce_timestamp(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e12:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            return datetime.fromisoformat(stripped.replace("Z", "+00:00")).isoformat()
        except ValueError:
            try:
                return coerce_timestamp(float(stripped))
            except ValueError:
                return stripped
    return ""


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalise_arcgis_records(records: list[dict]) -> list[dict]:
    sorted_records = sorted(
        records,
        key=lambda r: coerce_timestamp(r.get("CreationDate") or r.get("EditDate")),
        reverse=True,
    )
    by_gauge: dict[str, list[dict]] = {}
    for record in sorted_records:
        gauge = str(record.get("gauge") or "").strip()
        if not gauge:
            continue
        by_gauge.setdefault(gauge, []).append(record)

    latest_levels = []
    for gauge, gauge_records in by_gauge.items():
        latest = gauge_records[0]
        previous = next(
            (
                to_float(record.get("water_level"))
                for record in gauge_records[1:]
                if to_float(record.get("water_level")) is not None
            ),
            None,
        )
        timestamp = coerce_timestamp(latest.get("CreationDate") or latest.get("EditDate"))
        latest_levels.append(
            {
                "gauging_station_name": gauge,
                "current_water_level": to_float(latest.get("water_level")),
                "previous_water_level": previous,
                "rising_or_falling": None,
                "rainfall_mm": to_float(latest.get("rain_fall")),
                "remarks": None,
                "time_str": timestamp,
            }
        )

    return latest_levels


def normalise_arcgis_history(records: list[dict], station_name: str) -> list[dict]:
    sorted_records = sorted(
        records,
        key=lambda r: coerce_timestamp(r.get("CreationDate") or r.get("EditDate")),
        reverse=True,
    )
    readings = []
    for index, record in enumerate(sorted_records):
        previous = None
        if index + 1 < len(sorted_records):
            previous = to_float(sorted_records[index + 1].get("water_level"))
        timestamp = coerce_timestamp(record.get("CreationDate") or record.get("EditDate"))
        readings.append(
            {
                "gauging_station_name": station_name,
                "current_water_level": to_float(record.get("water_level")),
                "previous_water_level": previous,
                "rising_or_falling": None,
                "rainfall_mm": to_float(record.get("rain_fall")),
                "remarks": None,
                "time_str": timestamp,
            }
        )
    return readings


@cached(lambda: "live_gauge_records")
async def fetch_live_gauge_records() -> list[dict]:
    params = {
        "f": "json",
        "where": os.getenv("GAUGE_WHERE", "1=1"),
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": 1000,
        "orderByFields": "CreationDate DESC",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GAUGE_FEATURE_LAYER_URL}/query",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return [feature.get("attributes", {}) for feature in data.get("features", [])]


@cached(lambda station_name, limit=50: f"gauge_history_{station_name.lower()}_{limit}")
async def fetch_live_gauge_history(station_name: str, limit: int = 50) -> list[dict]:
    escaped_station = station_name.replace("'", "''")
    params = {
        "f": "json",
        "where": f"gauge='{escaped_station}'",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": max(1, min(limit, 500)),
        "orderByFields": "CreationDate DESC",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GAUGE_FEATURE_LAYER_URL}/query",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return [feature.get("attributes", {}) for feature in data.get("features", [])]


def read_local_gauge_records() -> list[dict]:
    if not LOCAL_GAUGE_JSON_PATH.exists():
        return []
    try:
        data = json.loads(LOCAL_GAUGE_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("records", [])


def read_local_gauge_history(station_name: str, limit: int = 50) -> list[dict]:
    station_key = station_name.lower()
    records = [
        record
        for record in read_local_gauge_records()
        if str(record.get("gauge") or "").lower() == station_key
    ]
    records.sort(
        key=lambda r: coerce_timestamp(r.get("CreationDate") or r.get("EditDate")),
        reverse=True,
    )
    return records[:limit]


@cached(lambda: "gauging_stations")
async def get_gauging_stations() -> list[dict]:
    data = await fetch_json("data/static/gauging_stations.json")
    return data if data else []


@cached(lambda: "rivers")
async def get_rivers() -> list[dict]:
    data = await fetch_json("data/static/rivers.json")
    return data if data else []


@cached(lambda: "river_basins")
async def get_river_basins() -> list[dict]:
    data = await fetch_json("data/static/river_basins.json")
    return data if data else []


@cached(lambda: "locations")
async def get_locations() -> list[dict]:
    data = await fetch_json("data/static/locations.json")
    return data if data else []


@cached(lambda: "docs_index")
async def get_docs_index() -> list[dict]:
    url = f"{BASE_URL}/data/docs_last100.tsv"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            lines = response.text.strip().split("\n")
            docs = []
            # Skip header row, doc_id is in column 1
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) >= 2:
                    docs.append({"id": parts[1], "url": parts[5] if len(parts) > 5 else ""})
            return docs
        except httpx.HTTPError:
            return []


async def get_water_level_data(doc_id: str) -> dict | None:
    cache_key = f"water_level_{doc_id}"
    if cache_key in cache:
        return cache[cache_key]

    data = await fetch_json(f"data/jsons/{doc_id}.json")
    if data:
        cache[cache_key] = data
    return data


async def get_latest_water_levels() -> list[dict]:
    try:
        records = await fetch_live_gauge_records()
    except httpx.HTTPError:
        records = read_local_gauge_records()

    if records:
        return normalise_arcgis_records(records)

    docs = await get_docs_index()
    if not docs:
        return []

    # Fallback to the DMC document index if ArcGIS and local snapshot are unavailable.
    latest_doc = next((doc for doc in docs if "water-level" in doc["id"]), None)
    if not latest_doc:
        return []

    data = await get_water_level_data(latest_doc["id"])
    if not data or "d_list" not in data:
        return []

    return data["d_list"]


async def get_station_water_level_history(station_name: str, limit: int = 50) -> list[dict]:
    try:
        records = await fetch_live_gauge_history(station_name, limit)
    except httpx.HTTPError:
        records = read_local_gauge_history(station_name, limit)

    if records:
        return normalise_arcgis_history(records, station_name)

    docs = await get_docs_index()
    readings = []
    for doc in docs[:limit]:
        data = await get_water_level_data(doc["id"])
        if not data or "d_list" not in data:
            continue

        for level in data["d_list"]:
            if level.get("gauging_station_name", "").lower() == station_name.lower():
                readings.append(level)
                break

    return readings


async def get_station_by_name(name: str) -> dict | None:
    stations = await get_gauging_stations()
    for station in stations:
        if station.get("name", "").lower() == name.lower():
            return station
    return None


async def get_river_by_name(name: str) -> dict | None:
    rivers = await get_rivers()
    for river in rivers:
        if river.get("name", "").lower() == name.lower():
            return river
    return None


async def get_basin_by_name(name: str) -> dict | None:
    basins = await get_river_basins()
    for basin in basins:
        if basin.get("name", "").lower() == name.lower():
            return basin
    return None


def calculate_alert_status(water_level: float | None, station: dict) -> str:
    if water_level is None:
        return "NO_DATA"

    major = station.get("major_flood_level", float("inf"))
    minor = station.get("minor_flood_level", float("inf"))
    alert = station.get("alert_level", float("inf"))

    if water_level >= major:
        return "MAJOR"
    elif water_level >= minor:
        return "MINOR"
    elif water_level >= alert:
        return "ALERT"
    else:
        return "NORMAL"


def calculate_flood_score(water_level: float | None, station: dict) -> float | None:
    if water_level is None:
        return None

    alert = station.get("alert_level", 0)
    major = station.get("major_flood_level", 0)

    if major <= alert:
        return None

    # Normalized score: 0 = at alert level, 1 = at major flood level
    return (water_level - alert) / (major - alert)
