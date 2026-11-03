"""Weather from Open-Meteo: find the home area, read the forecast, say what is notable.

The wording is built here from numbers, never copied from web text, so it is safe to speak plainly.
Only the area name goes out (to find its coordinates).
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .http import Fetch

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=5&language=en&format=json"
FORECAST = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&hourly=temperature_2m,precipitation,snowfall,weather_code,wind_gusts_10m&forecast_days=2&timezone=auto"
)
WINDOW_HOURS = 18
SNOW_CM, RAIN_MM_HOUR, GUST_KMH, COLD_C, HOT_C = 1.0, 4.0, 65.0, -12.0, 37.0
HEAVY_RAIN_CODES = {65, 67, 82}
THUNDER_CODES = {95, 96, 99}


@dataclass(frozen=True)
class Notable:
    kind: str  # snow, rain, thunder, wind, cold, heat
    summary: str
    starts: datetime
    ends: datetime


async def locate(area: str, fetch: Fetch) -> tuple[float, float, str] | None:
    """(latitude, longitude, timezone-less place name) for "Orem, Utah", or None."""
    parts = [p.strip() for p in area.split(",") if p.strip()]
    if not parts:
        return None
    body = await fetch(GEOCODE.format(name=urllib.parse.quote(parts[0])))
    try:
        results = json.loads(body or "{}").get("results") or []
    except ValueError:
        return None
    wanted = " ".join(parts[1:]).lower()
    for r in results:
        region = f"{r.get('admin1', '')} {r.get('country', '')} {r.get('country_code', '')}".lower()
        if not wanted or any(w in region for w in wanted.replace(",", " ").split()):
            return float(r["latitude"]), float(r["longitude"]), str(r.get("name") or parts[0])
    return None


async def forecast(lat: float, lon: float, fetch: Fetch) -> dict[str, Any] | None:
    body = await fetch(FORECAST.format(lat=lat, lon=lon))
    try:
        data = json.loads(body or "{}")
    except ValueError:
        return None
    hourly = data.get("hourly")
    if not isinstance(hourly, dict) or not hourly.get("time"):
        return None
    return {"hourly": hourly, "tz": data.get("timezone") or "UTC"}


def _f(c: float) -> int:
    return round(c * 9 / 5 + 32)


def _when(start: datetime, now: datetime) -> str:
    if start - now <= timedelta(hours=1):
        return "within the hour"
    h = start.hour
    day = "tonight" if h >= 20 or h < 5 else "this evening" if h >= 17 else "this afternoon" if h >= 12 else "this morning"
    return day if start.date() == now.date() else "tomorrow morning" if h < 12 else f"tomorrow {('afternoon' if h < 17 else 'evening')}"


def notable(data: dict[str, Any], now: datetime, *, imperial: bool = True) -> list[Notable]:
    """Conditions worth saying in the next 18 hours, one entry per kind."""
    h = data["hourly"]
    tz = ZoneInfo(data["tz"]) if data.get("tz") else timezone.utc
    local_now = now.astimezone(tz)
    rows = []
    for i, stamp in enumerate(h["time"]):
        t = datetime.fromisoformat(stamp).replace(tzinfo=tz)
        if local_now - timedelta(hours=1) <= t <= local_now + timedelta(hours=WINDOW_HOURS):
            def at(key: str, default: float = 0.0) -> float:
                vals = h.get(key) or []
                return float(vals[i]) if i < len(vals) and vals[i] is not None else default
            rows.append((t, at("temperature_2m"), at("precipitation"), at("snowfall"), int(at("weather_code")), at("wind_gusts_10m")))
    out: list[Notable] = []

    def first_last(pred):
        hit = [r[0] for r in rows if pred(r)]
        return (hit[0], hit[-1] + timedelta(hours=1)) if hit else None

    snow = sum(r[3] for r in rows)
    if snow >= SNOW_CM and (w := first_last(lambda r: r[3] > 0.05)):
        inches = snow / 2.54
        amount = f"around {inches:.0f} inch{'es' if round(inches) != 1 else ''}" if imperial and inches >= 1 else f"about {snow:.0f} centimeters" if not imperial else "a light dusting to an inch"
        out.append(Notable("snow", f"Snow is expected {_when(w[0], local_now)}, {amount} in total.", *w))
    if w := first_last(lambda r: r[2] >= RAIN_MM_HOUR or r[4] in HEAVY_RAIN_CODES):
        out.append(Notable("rain", f"Heavy rain is expected {_when(w[0], local_now)}.", *w))
    if w := first_last(lambda r: r[4] in THUNDER_CODES):
        out.append(Notable("thunder", f"Thunderstorms are expected {_when(w[0], local_now)}.", *w))
    if w := first_last(lambda r: r[5] >= GUST_KMH):
        peak = max(r[5] for r in rows)
        speed = f"{peak * 0.621:.0f} miles per hour" if imperial else f"{peak:.0f} kilometers per hour"
        out.append(Notable("wind", f"Strong wind is expected {_when(w[0], local_now)}, gusts up to {speed}.", *w))
    if rows and (low := min(r[1] for r in rows)) <= COLD_C and (w := first_last(lambda r: r[1] <= COLD_C)):
        deg = f"{_f(low)} degrees" if imperial else f"{low:.0f} degrees"
        out.append(Notable("cold", f"It will get very cold {_when(w[0], local_now)}, down to about {deg}.", *w))
    if rows and (high := max(r[1] for r in rows)) >= HOT_C and (w := first_last(lambda r: r[1] >= HOT_C)):
        deg = f"{_f(high)} degrees" if imperial else f"{high:.0f} degrees"
        out.append(Notable("heat", f"It will get very hot {_when(w[0], local_now)}, up to about {deg}.", *w))
    return out


def outlook(data: dict[str, Any], now: datetime, *, imperial: bool = True) -> str:
    """A plain one-line outlook for the day, for the morning brief."""
    h = data["hourly"]
    tz = ZoneInfo(data["tz"]) if data.get("tz") else timezone.utc
    today = now.astimezone(tz).date()
    temps = [float(t) for stamp, t in zip(h["time"], h["temperature_2m"]) if t is not None
             and datetime.fromisoformat(stamp).date() == today]
    if not temps:
        return "No forecast available."
    hi, lo = max(temps), min(temps)
    unit = (lambda c: f"{_f(c)}") if imperial else (lambda c: f"{c:.0f}")
    parts = [f"Today's high is around {unit(hi)} and the low around {unit(lo)} degrees."]
    alerts = notable(data, now, imperial=imperial)
    parts += [a.summary for a in alerts]
    return " ".join(parts)
