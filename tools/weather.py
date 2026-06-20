#!/usr/bin/env python3
"""Weather - current conditions + today's range for your location.

No API key. Location is auto-detected from your IP (or set "location" in
config.json weather as [latitude, longitude]). Data from open-meteo.com.
"""
import os
import sys
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0"}
WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
    96: "Thunderstorm + hail", 99: "Thunderstorm + hail",
}


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def locate(cfg):
    loc = cfg["weather"].get("location")
    if loc and isinstance(loc, list) and len(loc) == 2:
        return loc[0], loc[1], "your set location"
    try:
        d = _get("http://ip-api.com/json/?fields=status,city,regionName,lat,lon")
        if d.get("status") == "success":
            city = ", ".join(x for x in [d.get("city"), d.get("regionName")] if x)
            return d["lat"], d["lon"], city or "your area"
    except Exception:
        pass
    return None, None, None


def get_data():
    cfg = load_config()
    units = cfg["weather"].get("units", "fahrenheit")
    lat, lon, place = locate(cfg)
    if lat is None:
        return {"error": "could not determine location"}
    deg = "F" if units == "fahrenheit" else "C"
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
           f"weather_code,wind_speed_10m"
           f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           f"&temperature_unit={units}&wind_speed_unit=mph&timezone=auto")
    try:
        d = _get(url)
    except Exception as e:
        return {"error": str(e), "place": place}
    cur = d.get("current", {})
    day = d.get("daily", {})
    return {
        "place": place, "deg": deg,
        "temp": round(cur.get("temperature_2m", 0)),
        "feels": round(cur.get("apparent_temperature", 0)),
        "humidity": cur.get("relative_humidity_2m"),
        "wind": round(cur.get("wind_speed_10m", 0)),
        "desc": WMO.get(cur.get("weather_code"), "—"),
        "hi": round(day.get("temperature_2m_max", [0])[0]),
        "lo": round(day.get("temperature_2m_min", [0])[0]),
        "rain": (day.get("precipitation_probability_max") or [None])[0],
    }


def run():
    header("Weather", "[WX]")
    w = get_data()
    if w.get("error"):
        print(f"  {C.RED}Unavailable: {w['error']}{C.R}")
        return
    print(f"  {C.B}{w['place']}{C.R}")
    print(f"  {C.B}{C.CYN}{w['temp']}°{w['deg']}{C.R}  {w['desc']}   "
          f"{C.GRY}feels {w['feels']}°{C.R}")
    rain = f", {w['rain']}% rain" if w.get("rain") is not None else ""
    print(f"  {C.GRY}High {w['hi']}° / Low {w['lo']}°{rain}  ·  "
          f"humidity {w['humidity']}%  ·  wind {w['wind']} mph{C.R}")


if __name__ == "__main__":
    run()
