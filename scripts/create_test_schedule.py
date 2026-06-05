#!/usr/bin/env python3
"""
Create test schedules that trigger right now for manual testing.

This script creates schedules that:
1. Start now and run for 5 minutes
2. Start in 5 minutes and run for 5 minutes
3. Start in 10 minutes and run for 5 minutes

This allows you to manually verify that schedule switching works in real-time.

Usage:
    python scripts/create_test_schedule.py [--api-url http://localhost:4420/api]
"""

import argparse
import sys
from datetime import datetime, timedelta

import requests


def get_current_time_info():
    """Get current time info for schedule creation."""
    now = datetime.now()
    current_day = now.strftime("%A").lower()
    return now, current_day


def format_time(dt: datetime) -> str:
    """Format datetime to HH:MM string, rounded to nearest 15 minutes."""
    # Round to nearest 15 minutes
    minutes = (dt.minute // 15) * 15
    rounded = dt.replace(minute=minutes, second=0, microsecond=0)
    return rounded.strftime("%H:%M")


def create_schedule(api_url: str, page_id: str, start_time: str, end_time: str, day: str, name_suffix: str):
    """Create a schedule entry via API."""
    schedule_data = {
        "page_id": page_id,
        "start_time": start_time,
        "end_time": end_time,
        "day_pattern": "custom",
        "custom_days": [day],
        "enabled": True,
    }

    response = requests.post(f"{api_url}/schedules", json=schedule_data)
    response.raise_for_status()

    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Create test schedules for manual verification")
    parser.add_argument("--api-url", default="http://localhost:4420/api", help="API URL")
    args = parser.parse_args()

    print("🔧 Creating test schedules for schedule switching verification...\n")

    # Get current time
    now, current_day = get_current_time_info()
    print(f"Current time: {now.strftime('%H:%M')} on {current_day}")
    print(f"API URL: {args.api_url}\n")

    # Fetch available pages
    try:
        pages_response = requests.get(f"{args.api_url}/pages")
        pages_response.raise_for_status()
        pages = pages_response.json()["pages"]

        if len(pages) < 3:
            print(f"❌ Error: Need at least 3 pages. Found {len(pages)}. Create more pages first.")
            sys.exit(1)

        print(f"✅ Found {len(pages)} pages:")
        for i, page in enumerate(pages[:3]):
            print(f"   {i + 1}. {page['name']} (ID: {page['id']})")
        print()

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching pages: {e}")
        print("   Make sure the API server is running.")
        sys.exit(1)

    # Create 3 test schedules
    schedules = []

    # Schedule 1: Now -> 5 minutes
    start1 = now
    end1 = now + timedelta(minutes=5)
    start1_str = format_time(start1)
    end1_str = format_time(end1)

    print(f"Creating Schedule 1: {pages[0]['name']}")
    print(f"  Time: {start1_str} - {end1_str} (starting NOW)")

    try:
        schedule1 = create_schedule(args.api_url, pages[0]["id"], start1_str, end1_str, current_day, "Now")
        schedules.append(schedule1)
        print(f"  ✅ Created schedule {schedule1['id']}\n")
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error: {e}\n")

    # Schedule 2: 5 minutes -> 10 minutes
    start2 = now + timedelta(minutes=5)
    end2 = now + timedelta(minutes=10)
    start2_str = format_time(start2)
    end2_str = format_time(end2)

    print(f"Creating Schedule 2: {pages[1]['name']}")
    print(f"  Time: {start2_str} - {end2_str} (in 5 minutes)")

    try:
        schedule2 = create_schedule(args.api_url, pages[1]["id"], start2_str, end2_str, current_day, "In 5 min")
        schedules.append(schedule2)
        print(f"  ✅ Created schedule {schedule2['id']}\n")
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error: {e}\n")

    # Schedule 3: 10 minutes -> 15 minutes
    start3 = now + timedelta(minutes=10)
    end3 = now + timedelta(minutes=15)
    start3_str = format_time(start3)
    end3_str = format_time(end3)

    print(f"Creating Schedule 3: {pages[2]['name']}")
    print(f"  Time: {start3_str} - {end3_str} (in 10 minutes)")

    try:
        schedule3 = create_schedule(args.api_url, pages[2]["id"], start3_str, end3_str, current_day, "In 10 min")
        schedules.append(schedule3)
        print(f"  ✅ Created schedule {schedule3['id']}\n")
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error: {e}\n")

    # Enable schedule mode
    print("Enabling schedule mode...")
    try:
        response = requests.post(f"{args.api_url}/schedules/enabled", json={"enabled": True})
        response.raise_for_status()
        print("✅ Schedule mode enabled\n")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error enabling schedule mode: {e}\n")

    # Summary
    print("=" * 60)
    print("📅 TEST SCHEDULES CREATED")
    print("=" * 60)
    print(f"\nCurrent time: {now.strftime('%H:%M:%S')}")
    print(f"\nSchedule Timeline (today, {current_day}):")
    print(f"  {start1_str} - {end1_str}  →  {pages[0]['name']} (NOW)")
    print(f"  {start2_str} - {end2_str}  →  {pages[1]['name']} (in ~5 min)")
    print(f"  {start3_str} - {end3_str}  →  {pages[2]['name']} (in ~10 min)")
    print("\n🔄 The UI will refresh every 60 seconds")
    print("🎯 Watch the home page to see pages switch automatically")
    print("\n⚠️  Note: Switches may be delayed up to 60 seconds due to polling")
    print("\n🗑️  To clean up: Delete these schedules from the Schedule page")
    print("=" * 60)


if __name__ == "__main__":
    main()
