import requests
import time

print('Testing full extraction with timeout...')
polygon = [[46.261097838675894, 14.20504280600635], [46.261116197259796, 14.205514873621876], [46.260897469995996, 14.205752516534563], [46.260756267267105, 14.205320618687834]]

test_data = {
    'point_cloud_path': '/tmp/uploads/DMR_438_124.laz',
    'polygon': polygon
}

print(f'Testing extraction with polygon: {polygon}')
start_time = time.time()
try:
    extract_response = requests.post('http://localhost:5005/api/extract-region',
                                   json=test_data,
                                   headers={'Content-Type': 'application/json'},
                                   timeout=120)  # 2 minute timeout
    end_time = time.time()
    print(f'Extract completed in {end_time - start_time:.2f} seconds')
    print(f'Extract status: {extract_response.status_code}')
    if extract_response.status_code == 200:
        data = extract_response.json()
        print(f'Success! Extracted {data.get("data", {}).get("point_count", "unknown")} points')
    else:
        print(f'Extract failed: {extract_response.text[:1000]}...')
except requests.exceptions.Timeout:
    print('Extract request timed out after 120 seconds')
except Exception as e:
    print(f'Extract request failed: {e}')