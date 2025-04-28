import os
import sys
from pathlib import Path

parent_dir = str(Path(__file__).parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils.booth_results_processor import download_polling_places_data, process_polling_places_file, DATA_DIR

polling_places_path = DATA_DIR / "polling_places" / "polling-places-2025.csv"
if polling_places_path.exists():
    print(f"Deleting existing file: {polling_places_path}")
    polling_places_path.unlink()

print("Testing download_polling_places_data()...")
result = download_polling_places_data()
print(f"Download result: {result}")

if polling_places_path.exists():
    print(f"File exists at: {polling_places_path}")
    with open(polling_places_path, 'r', encoding='utf-8-sig') as f:
        first_line = f.readline().strip()
        print(f"First line of file: {first_line}")
        
        if first_line.startswith('<!DOCTYPE html>') or '<html' in first_line:
            print("ERROR: File contains HTML instead of CSV data")
        else:
            print("SUCCESS: File appears to be valid CSV")
            
            print("\nTesting process_polling_places_file()...")
            polling_places = process_polling_places_file(polling_places_path)
            print(f"Processed {len(polling_places)} polling places")
            
            if polling_places:
                print("\nSample polling place:")
                print(polling_places[0])
                
                north_sydney_booths = [p for p in polling_places if 
                                      'North Sydney' in p['polling_place_name'] or 
                                      'Cammeray' in p['polling_place_name'] or 
                                      'Wollstonecraft' in p['polling_place_name']]
                
                print(f"\nFound {len(north_sydney_booths)} North Sydney area booths:")
                for booth in north_sydney_booths:
                    print(f"  {booth['polling_place_id']} | {booth['polling_place_name']} | {booth['division_name']}")
else:
    print(f"ERROR: File does not exist at {polling_places_path}")
