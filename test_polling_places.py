import os
import sys
import json
from pathlib import Path

parent_dir = str(Path(__file__).parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from common.booth_results_processor import (
    download_polling_places_data,
    process_polling_places_file,
    DATA_DIR,
    create_sample_2025_polling_places_data,
    process_and_load_polling_places,
    get_polling_places_for_division,
)

print("Testing download_polling_places_data()...")
polling_places_path = DATA_DIR / "polling_places" / "polling-places-2025.csv"

if polling_places_path.exists():
    print(f"Deleting existing file: {polling_places_path}")
    polling_places_path.unlink()

download_result = download_polling_places_data()
print(f"Download result: {download_result}")

if polling_places_path.exists():
    print(f"File exists at: {polling_places_path}")
    with open(polling_places_path, "r", encoding="utf-8-sig") as f:
        first_line = f.readline().strip()
        print(f"First line of file: {first_line}")

        if first_line.startswith("<!DOCTYPE html>") or "<html" in first_line:
            print("ERROR: File contains HTML instead of CSV data")
        else:
            print("SUCCESS: File appears to be valid CSV")

            print("\nTesting process_polling_places_file()...")
            polling_places = process_polling_places_file(polling_places_path)
            print(f"Processed {len(polling_places)} polling places")

            if polling_places:
                print("\nSample polling place:")
                print(json.dumps(polling_places[0], indent=2))

                north_sydney_booths = [
                    p
                    for p in polling_places
                    if "North Sydney" in p["polling_place_name"]
                    or "Cammeray" in p["polling_place_name"]
                    or "Wollstonecraft" in p["polling_place_name"]
                ]

                print(f"\nFound {len(north_sydney_booths)} North Sydney area booths:")
                for booth in north_sydney_booths:
                    print(
                        f"  {booth['polling_place_id']} | {booth['polling_place_name']} | {booth['division_name']}"
                    )
else:
    print(f"ERROR: File does not exist at {polling_places_path}")
    print("\nTesting fallback sample data generation...")
    sample_data = create_sample_2025_polling_places_data()
    print(f"Generated {len(sample_data)} sample polling places")

    if sample_data:
        print("\nSample polling place:")
        print(json.dumps(sample_data[0], indent=2))

        north_sydney_booths = [
            p
            for p in sample_data
            if "North Sydney" in p["polling_place_name"]
            or "Cammeray" in p["polling_place_name"]
            or "Wollstonecraft" in p["polling_place_name"]
        ]

        print(
            f"\nFound {len(north_sydney_booths)} North Sydney area booths in sample data:"
        )
        for booth in north_sydney_booths:
            print(
                f"  {booth['polling_place_id']} | {booth['polling_place_name']} | {booth['division_name']}"
            )
