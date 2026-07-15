import json
import sys
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

import fred

ASSETS = [
    "SP500",
]


def fetch_all() -> dict:
    results = {}
    for asset in ASSETS:
        try:
            observations = fred.series_observations(asset, sort_order="desc", limit=1)
            info = fred.series_info(asset)
            results[asset] = {
                "title": info["title"],
                "units": info["units_short"],
                "value": observations[0]["value"],
                "date": observations[0]["date"],
            }
        except Exception as e:
            results[asset] = {"error": str(e)}
    return results


if __name__ == "__main__":
    print(json.dumps(fetch_all()))
