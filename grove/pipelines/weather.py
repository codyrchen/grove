"""Oxford, MS weather from Open-Meteo (free, no API key)."""

import requests

from ..config import OXFORD_LAT, OXFORD_LON

URL = "https://api.open-meteo.com/v1/forecast"
PARAMS = {
    "latitude": OXFORD_LAT,
    "longitude": OXFORD_LON,
    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
    "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
             "precipitation_probability_max,sunrise,sunset",
    "hourly": "temperature_2m,weather_code,is_day,precipitation_probability",
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "timezone": "America/Chicago",
    "forecast_days": 5,
}

# WMO weather codes -> (description, Bootstrap icon name)
CODES = {
    0: ("Clear", "sun"), 1: ("Mostly clear", "sun"), 2: ("Partly cloudy", "cloud-sun"),
    3: ("Cloudy", "cloud"), 45: ("Fog", "cloud-fog"), 48: ("Fog", "cloud-fog"),
    51: ("Light drizzle", "cloud-drizzle"), 53: ("Drizzle", "cloud-drizzle"),
    55: ("Heavy drizzle", "cloud-drizzle"), 56: ("Freezing drizzle", "cloud-sleet"),
    57: ("Freezing drizzle", "cloud-sleet"), 61: ("Light rain", "cloud-rain"),
    63: ("Rain", "cloud-rain"), 65: ("Heavy rain", "cloud-rain-heavy"),
    66: ("Freezing rain", "cloud-sleet"), 67: ("Freezing rain", "cloud-sleet"),
    71: ("Light snow", "cloud-snow"), 73: ("Snow", "cloud-snow"), 75: ("Heavy snow", "cloud-snow"),
    77: ("Snow grains", "cloud-snow"), 80: ("Showers", "cloud-rain"),
    81: ("Showers", "cloud-rain"), 82: ("Heavy showers", "cloud-rain-heavy"),
    85: ("Snow showers", "cloud-snow"), 86: ("Snow showers", "cloud-snow"),
    95: ("Thunderstorms", "cloud-lightning-rain"), 96: ("Thunderstorms, hail", "cloud-hail"),
    99: ("Thunderstorms, hail", "cloud-hail"),
}


SNOW_CODES = {71, 73, 75, 77, 85, 86}


def describe(code, is_day: bool = True) -> tuple[str, str]:
    text, icon = CODES.get(code, ("—", "cloud"))
    if not is_day and icon in ("sun", "cloud-sun"):
        icon = "moon-stars" if icon == "sun" else "cloud-moon"
    return text, icon


def clock(iso: str) -> str:
    """'2026-10-07T18:31' -> '6:31 PM'"""
    hour, minute = int(iso[11:13]), iso[14:16]
    return f"{hour % 12 or 12}:{minute} {'AM' if hour < 12 else 'PM'}"


def hour_label(iso: str) -> str:
    """'2026-10-07T13:00' -> '1 pm'"""
    hour = int(iso[11:13])
    return f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}"


def upcoming_hours(raw: dict, count: int = 5, step: int = 3) -> list[dict]:
    """The next few hours after now, every `step` hours (like 4 pm, 7 pm, 10 pm...)."""
    hourly = raw.get("hourly")
    if not hourly:
        return []
    now = raw["current"]["time"][:13]  # "2026-10-07T08"; times share the local timezone
    start = next((i for i, t in enumerate(hourly["time"]) if t[:13] > now), None)
    if start is None:
        return []
    out = []
    for i in range(start, len(hourly["time"]), step):
        text, icon = describe(hourly["weather_code"][i], bool(hourly["is_day"][i]))
        out.append({"label": hour_label(hourly["time"][i]),
                    "temp": round(hourly["temperature_2m"][i]), "text": text, "icon": icon})
        if len(out) == count:
            break
    return out


def all_hours(raw: dict) -> list[dict]:
    """Every forecast hour (Oxford time), compact, for things like the kickoff forecast."""
    h = raw.get("hourly")
    if not h:
        return []
    rain = h.get("precipitation_probability") or [None] * len(h["time"])
    return [{"t": t, "temp": round(h["temperature_2m"][i]), "code": h["weather_code"][i],
             "day": h["is_day"][i], "rain": rain[i]} for i, t in enumerate(h["time"])]


def parse(raw: dict) -> dict:
    cur, daily = raw["current"], raw["daily"]
    text, icon = describe(cur["weather_code"], bool(cur.get("is_day", 1)))
    days = []
    for i, date in enumerate(daily["time"]):
        d_text, d_icon = describe(daily["weather_code"][i])
        days.append({
            "date": date,
            "high": round(daily["temperature_2m_max"][i]),
            "low": round(daily["temperature_2m_min"][i]),
            "rain_chance": daily["precipitation_probability_max"][i],
            "text": d_text,
            "icon": d_icon,
            "code": daily["weather_code"][i],
        })
    return {
        "temp": round(cur["temperature_2m"]),
        "feels_like": round(cur["apparent_temperature"]),
        "wind_mph": round(cur["wind_speed_10m"]),
        "text": text,
        "icon": icon,
        "code": cur["weather_code"],
        "sunset": clock(daily["sunset"][0]) if daily.get("sunset") else None,
        "hours": upcoming_hours(raw),
        "forecast": all_hours(raw),
        "days": days,
    }


def fetch() -> dict:
    r = requests.get(URL, params=PARAMS, timeout=30)
    r.raise_for_status()
    return parse(r.json())
