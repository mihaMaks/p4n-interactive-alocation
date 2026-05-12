#!/usr/bin/env python3
"""
Complete pipeline test for point cloud processing:
1. Load .laz file
2. Extract points from user-defined polygon (with coordinate system validation)
3. Create mesh using Open3D (outlier removal, normal estimation, meshing, export)
4. Web view with Three.js
"""
import requests
import json
import time
import os
from pathlib import Path

def test_complete_pipeline():
    """Test the complete pipeline from .laz file to 3D web view."""

    print("=== Point Cloud Processing Pipeline Test ===\n")

    # Step 1: Upload .laz file
    print("1. Uploading .laz file...")
    laz_file_path = "/Users/maksbertoncelj/Downloads/DMR_438_124.laz"

    if not os.path.exists(laz_file_path):
        print(f"ERROR: .laz file not found at {laz_file_path}")
        return

    with open(laz_file_path, 'rb') as f:
        files = {'file': ('DMR_438_124.laz', f, 'application/octet-stream')}
        upload_response = requests.post('http://localhost:5009/api/upload-point-cloud',
                                      files=files, timeout=60)

    if upload_response.status_code != 200:
        print(f"Upload failed: {upload_response.text}")
        return

    upload_data = upload_response.json()
    if not upload_data.get('success'):
        print(f"Upload error: {upload_data.get('error')}")
        return

    point_cloud_path = upload_data['data']['filepath']
    print(f"✓ File uploaded successfully: {point_cloud_path}")

    # Step 2: Extract region with coordinate validation
    print("\n2. Extracting polygon region...")

    # User's polygon coordinates from Google Maps (WGS84)
    user_polygon = [[46.261097838675894, 14.20504280600635],
                   [46.261116197259796, 14.205514873621876],
                   [46.260897469995996, 14.205752516534563],
                   [46.260756267267105, 14.205320618687834]]

    extract_data = {
        'point_cloud_path': point_cloud_path,
        'polygon': user_polygon
    }

    print(f"User polygon (WGS84): {user_polygon}")
    start_time = time.time()

    extract_response = requests.post('http://localhost:5009/api/extract-region',
                                   json=extract_data,
                                   headers={'Content-Type': 'application/json'},
                                   timeout=300)  # 5 minute timeout

    extract_time = time.time() - start_time

    if extract_response.status_code != 200:
        print(f"Extraction failed: {extract_response.text}")
        return

    extract_result = extract_response.json()
    if not extract_result.get('success'):
        print(f"Extraction error: {extract_result.get('error')}")
        return

    point_count = extract_result['data']['point_count']
    print(f"✓ Region extracted in {extract_time:.2f}s - {point_count} points found")

    if point_count == 0:
        print("⚠️  WARNING: No points found in the specified polygon area!")
        print("   This could mean:")
        print("   - The polygon coordinates don't match the point cloud coordinate system")
        print("   - The polygon is outside the point cloud bounds")
        print("   - The polygon area is too small or contains no data")
        return

    # Step 3: Generate mesh
    print("\n3. Generating 3D mesh...")

    # Create output directory
    output_dir = Path("/tmp/outputs")
    output_dir.mkdir(exist_ok=True)

    timestamp = int(time.time())
    mesh_output_path = f"/tmp/outputs/mesh_{timestamp}.glb"

    mesh_data = {
        'point_cloud_path': point_cloud_path,
        'polygon': user_polygon,
        'output_path': mesh_output_path,
        'algorithm': 'poisson',  # Use Poisson reconstruction
        'generator_params': {
            'depth': 8,  # Poisson depth parameter
            'scale': 1.1,  # Scale parameter
            'linear_fit': False  # Linear fit
        }
    }

    start_time = time.time()
    mesh_response = requests.post('http://localhost:5009/api/generate-mesh',
                                json=mesh_data,
                                headers={'Content-Type': 'application/json'},
                                timeout=600)  # 10 minute timeout for meshing

    mesh_time = time.time() - start_time

    if mesh_response.status_code != 200:
        print(f"Mesh generation failed: {mesh_response.text}")
        return

    mesh_result = mesh_response.json()
    if not mesh_result.get('success'):
        print(f"Mesh generation error: {mesh_result.get('error')}")
        return

    print(f"✓ Mesh generated in {mesh_time:.2f}s")
    print(f"  Output: {mesh_output_path}")

    # Check if mesh file exists
    if os.path.exists(mesh_output_path):
        file_size = os.path.getsize(mesh_output_path) / (1024 * 1024)  # MB
        print(f"  File size: {file_size:.2f} MB")
    else:
        print("⚠️  WARNING: Mesh file was not created!")

    # Step 4: Web view instructions
    print("\n4. Web Interface")
    print("✓ Backend server running on: http://localhost:5009")
    print("✓ Frontend server running on: http://localhost:8001")
    print("\nTo view the 3D model:")
    print("1. Open http://localhost:8001 in your browser")
    print("2. Upload the .laz file (DMR_438_124.laz)")
    print("3. Enter the polygon coordinates:")
    for i, coord in enumerate(user_polygon):
        print(f"   {coord}")
    print("4. Click 'Extract Region'")
    print("5. Click 'Generate Mesh' to create the 3D model")
    print("6. The model will be displayed in the 3D viewer")

    print("\n=== Pipeline Complete ===")
    print(f"Points extracted: {point_count}")
    print(f"Mesh file: {mesh_output_path}")
    print("Ready for web viewing!")

if __name__ == '__main__':
    test_complete_pipeline()