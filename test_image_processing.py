import requests
import json
import os
from pathlib import Path

test_dir = Path.home() / "test_images"
test_dir.mkdir(exist_ok=True)

test_image_path = test_dir / "test_warringah.jpg"

try:
    print("Testing image processing with direct upload:")
    
    if not test_image_path.exists():
        print(f"Creating test image at {test_image_path}")
        sample_path = Path.home() / "repos" / "amalfiResults" / "flask_app" / "static" / "img" / "sample_tally.jpg"
        if sample_path.exists():
            import shutil
            shutil.copy(sample_path, test_image_path)
            print(f"Copied sample image to {test_image_path}")
        else:
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new('RGB', (800, 600), color=(255, 255, 255))
                d = ImageDraw.Draw(img)
                d.text((10, 10), "WARRINGAH TALLY SHEET", fill=(0, 0, 0))
                d.text((10, 50), "BOOTH NAME: Test Booth", fill=(0, 0, 0))
                img.save(test_image_path)
                print(f"Created test image with PIL at {test_image_path}")
            except ImportError:
                print("PIL not available, cannot create test image")
                exit(1)
    
    with open(test_image_path, 'rb') as f:
        files = {'file': (test_image_path.name, f, 'image/jpeg')}
        response = requests.post('http://localhost:8000/scan-image', files=files)
    
    print(f"Status code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    result = response.json()
    if 'result_id' in result:
        result_response = requests.get(f"http://localhost:8000/result/{result['result_id']}")
        result_data = result_response.json()
        print(f"\nResult details: {json.dumps(result_data, indent=2)}")
        
        if result_data.get('status') == 'success' and 'result' in result_data:
            electorate = result_data['result'].get('electorate')
            print(f"\nElectorate detected: {electorate}")
            print(f"Electorate is WARRINGAH: {electorate == 'WARRINGAH'}")
    
except Exception as e:
    print(f"Error: {e}")
