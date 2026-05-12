#!/usr/bin/env python3
"""
Test script to upload DMR_438_124.laz and extract region with coordinates from coordinates.txt
"""
import requests
import json
import os

def test_upload_and_extract():
    """Test file upload and region extraction."""

    # Test file upload
    print('Testing file upload...')
    file_path = '/Users/maksbertoncelj/Downloads/DMR_438_124.laz'

    if not os.path.exists(file_path):
        print(f'Error: File not found: {file_path}')
        return

    with open(file_path, 'rb') as f:
        files = {'file': ('DMR_438_124.laz', f, 'application/octet-stream')}
        response = requests.post('http://localhost:5005/api/upload-point-cloud', files=files)

    print(f'Upload response status: {response.status_code}')
    print(f'Upload response: {response.text}')

    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            filepath = data['data']['filepath']
            print(f'File uploaded successfully: {filepath}')

            # Test region extraction with coordinates from coordinates.txt
            polygon = [[46.261097838675894, 14.20504280600635],
                      [46.261116197259796, 14.205514873621876],
                      [46.260897469995996, 14.205752516534563],
                      [46.260756267267105, 14.205320618687834]]

            extract_data = {
                'point_cloud_path': filepath,
                'polygon': polygon
            }

            print(f'Testing region extraction with polygon: {polygon}')
            extract_response = requests.post('http://localhost:5005/api/extract-region',
                                           json=extract_data,
                                           headers={'Content-Type': 'application/json'})
            print(f'Extract response status: {extract_response.status_code}')
            print(f'Extract response: {extract_response.text}')

            if extract_response.status_code == 200:
                extract_data = extract_response.json()
                if extract_data.get('success'):
                    print('Region extraction successful!')

                    # Test mesh generation
                    mesh_data = {
                        'point_cloud_path': filepath,
                        'polygon': polygon,
                        'output_path': '/tmp/test_mesh.glb',
                        'algorithm': 'poisson'
                    }

                    print('Testing mesh generation...')
                    mesh_response = requests.post('http://localhost:5005/api/generate-mesh',
                                                json=mesh_data,
                                                headers={'Content-Type': 'application/json'})
                    print(f'Mesh response status: {mesh_response.status_code}')
                    print(f'Mesh response: {mesh_response.text}')
                else:
                    print(f'Region extraction failed: {extract_data.get("error")}')
            else:
                print(f'Region extraction HTTP error: {extract_response.status_code}')
        else:
            print(f'Upload failed: {data.get("error")}')
    else:
        print(f'Upload HTTP error: {response.status_code}')

if __name__ == '__main__':
    test_upload_and_extract()