#!/usr/bin/env python3
"""
Seed the FiestaBoard app with realistic dummy data for screenshot purposes.

Usage: python3 scripts/seed_screenshot_data.py [--reset]
  --reset  Remove all seeded data and restore to defaults
"""

import sys
import json
import urllib.request
import urllib.error
import time

BASE_URL = "http://localhost:4420/api"

SEED_TAG = "__screenshot_seed__"  # marker in page names to identify seeded pages


def api(method: str, path: str, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  ERROR {method} {path}: {e.code} {e.read().decode()[:200]}")
        return None


def reset():
    print("Resetting seeded data...")

    # Delete seeded pages
    pages = api("GET", "/pages") or {}
    for page in pages.get("pages", []):
        if SEED_TAG in page.get("name", ""):
            api("DELETE", f"/pages/{page['id']}")
            print(f"  Deleted page: {page['name']}")
            time.sleep(0.1)  # avoid overwhelming the API

    # Delete all schedules
    schedules = api("GET", "/schedules") or {}
    for entry in schedules.get("schedules", []):
        api("DELETE", f"/schedules/{entry['id']}")
    print(f"  Deleted {schedules.get('total', 0)} schedule entries")

    # Disable all plugins
    plugins = api("GET", "/plugins") or {}
    for plugin in plugins.get("plugins", []):
        if plugin.get("enabled"):
            api("POST", f"/plugins/{plugin['id']}/disable")
            print(f"  Disabled plugin: {plugin['id']}")

    print("Reset complete.")


def seed():
    print("Seeding screenshot data...")

    # --- Enable plugins (no API key required) ---
    no_key_plugins = [
        "date_time",
        "star_trek_quotes",
        "visual_clock",
        "sun_art",
        "white_noise",
        "stardate",
        "dad_jokes",
        "spacecraft_launches",
        "sports_scores",
        "disney_parks_times",
    ]
    print("\nEnabling plugins...")
    for plugin_id in no_key_plugins:
        result = api("POST", f"/plugins/{plugin_id}/enable")
        if result:
            print(f"  Enabled: {plugin_id}")

    # --- Create sample pages ---
    print("\nCreating pages...")
    pages_data = [
        {
            "name": f"Morning Brief {SEED_TAG}",
            "type": "template",
            "device_type": "flagship",
            "template": [
                "    GOOD MORNING      ",
                "                      ",
                " {date_time.date}     ",
                " {date_time.time}     ",
                "                      ",
                " {star_trek_quotes.quote} ",
            ],
            "duration_seconds": 300,
        },
        {
            "name": f"Date & Time {SEED_TAG}",
            "type": "single",
            "device_type": "flagship",
            "display_type": "date_time",
            "duration_seconds": 60,
        },
        {
            "name": f"Star Trek Quotes {SEED_TAG}",
            "type": "single",
            "device_type": "flagship",
            "display_type": "star_trek_quotes",
            "duration_seconds": 120,
        },
        {
            "name": f"Stardate {SEED_TAG}",
            "type": "single",
            "device_type": "flagship",
            "display_type": "stardate",
            "duration_seconds": 60,
        },
        {
            "name": f"Evening Update {SEED_TAG}",
            "type": "template",
            "device_type": "flagship",
            "template": [
                "   EVENING UPDATE     ",
                "                      ",
                " Today is             ",
                " {date_time.date}     ",
                "                      ",
                " {dad_jokes.joke}     ",
            ],
            "duration_seconds": 300,
        },
    ]

    created_pages = []
    for page_data in pages_data:
        result = api("POST", "/pages", page_data)
        if result:
            page = result.get("page", result)
            created_pages.append(page)
            print(f"  Created page: {page['name']} ({page['id']})")

    if not created_pages:
        print("  No pages created, cannot seed schedule.")
        return

    # --- Create schedule entries ---
    print("\nCreating schedule entries...")
    # Use the first 3 created pages for schedule
    page_ids = [p["id"] for p in created_pages[:4]]

    schedule_entries = [
        # Weekday mornings - Morning Brief
        {
            "page_id": page_ids[0],
            "start_time": "07:00",
            "end_time": "09:00",
            "day_pattern": "weekdays",
            "enabled": True,
        },
        # Weekday daytime - Date & Time
        {
            "page_id": page_ids[1] if len(page_ids) > 1 else page_ids[0],
            "start_time": "09:00",
            "end_time": "17:00",
            "day_pattern": "weekdays",
            "enabled": True,
        },
        # Weekday evenings - Star Trek Quotes
        {
            "page_id": page_ids[2] if len(page_ids) > 2 else page_ids[0],
            "start_time": "17:00",
            "end_time": "22:00",
            "day_pattern": "weekdays",
            "enabled": True,
        },
        # Weekend mornings - Morning Brief
        {
            "page_id": page_ids[0],
            "start_time": "09:00",
            "end_time": "11:00",
            "day_pattern": "weekends",
            "enabled": True,
        },
        # Weekend afternoons - Evening Update
        {
            "page_id": page_ids[3] if len(page_ids) > 3 else page_ids[0],
            "start_time": "14:00",
            "end_time": "18:00",
            "day_pattern": "weekends",
            "enabled": True,
        },
        # Evening filler
        {
            "page_id": page_ids[2] if len(page_ids) > 2 else page_ids[0],
            "start_time": "22:00",
            "end_time": "23:45",
            "day_pattern": "all",
            "enabled": True,
        },
    ]

    for entry in schedule_entries:
        result = api("POST", "/schedules", entry)
        if result:
            print(f"  Created schedule: {entry['start_time']}-{entry['end_time']} {entry['day_pattern']}")

    # --- Enable schedule mode ---
    api("PUT", "/schedules/enabled", {"enabled": True})
    print("  Enabled schedule mode")

    print("\nSeeding complete!")
    print(f"  Pages created: {len(created_pages)}")
    print(f"  Schedule entries created: {len(schedule_entries)}")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
    else:
        seed()
