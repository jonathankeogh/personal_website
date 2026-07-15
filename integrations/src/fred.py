import os
from dotenv import load_dotenv
import requests

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

BASE_URL = "https://api.stlouisfed.org/fred"
API_KEY = os.environ["FRED_API_KEY"]


def _get(endpoint: str, params: dict) -> dict:
    params = {"api_key": API_KEY, "file_type": "json", **params}
    r = requests.get(f"{BASE_URL}/{endpoint}", params=params)
    r.raise_for_status()
    return r.json()


def series_observations(series_id: str, **kwargs) -> list[dict]:
    data = _get("series/observations", {"series_id": series_id, **kwargs})
    return data["observations"]


def series_info(series_id: str) -> dict:
    data = _get("series", {"series_id": series_id})
    return data["seriess"][0]
