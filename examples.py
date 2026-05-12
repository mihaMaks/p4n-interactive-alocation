"""
Example script demonstrating point cloud to mesh conversion pipeline.
This shows typical usage patterns and best practices.
"""

import os
import numpy as np
from backend.point_cloud import (
    PointCloudLoaderFactory,
    PolygonExtractorService,
    OutlierRemovalFilter,
    DownsamplingFilter,
    CompositeNormalizer,
    CenterNormalizer,
    ScaleNormalizer,
)
from backend.model import PointCloudToMeshPipeline


def example_1_simple_extraction_and_generation():
    """
    Basic example: Load point cloud, extract region, and generate mesh.
    """
    print("\n=== Example 1: Simple Extraction and Generation ===\n")
    
    # Initialize pipeline
    pipeline = PointCloudToMeshPipeline()
    
    # Define paths
    point_cloud_path = 'data/sample_cloud.las'
    output_mesh_path = 'output/mesh_basic.glb'
    
    # Define extraction polygon (world coordinates)
    polygon = np.array([
        [1000, 2000],
        [1100, 2000],
        [1100, 2100],
        [1000, 2100],
    ], dtype=np.float32)
    
    try:
        # Load point cloud
        print(f"Loading point cloud: {point_cloud_path}")
        point_cloud = pipeline.load_point_cloud(point_cloud_path)
        print(f"✓ Loaded {point_cloud.num_points()} points")
        
        # Extract region
        print(f"Extracting polygon region...")
        extracted = pipeline.extract_region(point_cloud, polygon)
        print(f"✓ Extracted {extracted.num_points()} points")
        
        # Process
        print(f"Processing point cloud...")
        processed = pipeline.process_point_cloud(extracted)
        print(f"✓ After processing: {processed.num_points()} points")
        
        # Generate mesh using Poisson algorithm
        print(f"Generating mesh (Poisson)...")
        mesh = pipeline.generate_mesh(processed, algorithm='poisson', depth=9)
        print(f"✓ Generated mesh: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
        
        # Export
        print(f"Exporting to: {output_mesh_path}")
        os.makedirs(os.path.dirname(output_mesh_path), exist_ok=True)
        pipeline.export_mesh(mesh, output_mesh_path)
        print(f"✓ Success!")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def example_2_with_filtering_and_normalization():
    """
    Advanced example: Filter outliers, downsample, and normalize.
    """
    print("\n=== Example 2: Filtering and Normalization ===\n")
    
    # Initialize pipeline with custom filters
    pipeline = PointCloudToMeshPipeline()
    
    # Add custom filters (removes noise)
    pipeline.add_filter(OutlierRemovalFilter(neighbors=20, std_ratio=2.0))
    print("✓ Added outlier removal filter")
    
    # Downsample for faster processing
    pipeline.add_filter(DownsamplingFilter(voxel_size=0.02))
    print("✓ Added downsampling filter")
    
    # Add normalizers
    normalizers = [
        CenterNormalizer(),
        ScaleNormalizer(),
    ]
    for normalizer in normalizers:
        pipeline.add_normalizer(normalizer)
    print("✓ Added normalizers (center and scale)")
    
    point_cloud_path = 'data/noisy_cloud.las'
    polygon = np.array([[0, 0], [50, 0], [50, 50], [0, 50]], dtype=np.float32)
    
    try:
        print(f"\nLoading: {point_cloud_path}")
        point_cloud = pipeline.load_point_cloud(point_cloud_path)
        print(f"Initial points: {point_cloud.num_points()}")
        
        print(f"Extracting region...")
        extracted = pipeline.extract_region(point_cloud, polygon)
        print(f"Extracted points: {extracted.num_points()}")
        
        print(f"Processing (filter + normalize)...")
        processed = pipeline.process_point_cloud(extracted)
        print(f"After processing: {processed.num_points()}")
        
        print(f"Generating mesh...")
        mesh = pipeline.generate_mesh(processed, algorithm='ball_pivoting')
        print(f"Generated: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
        
        os.makedirs('output', exist_ok=True)
        pipeline.export_mesh(mesh, 'output/mesh_filtered.glb')
        print(f"✓ Exported to output/mesh_filtered.glb")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def example_3_multiple_algorithms():
    """
    Compare different mesh generation algorithms.
    """
    print("\n=== Example 3: Multiple Algorithms ===\n")
    
    pipeline = PointCloudToMeshPipeline()
    pipeline.add_filter(DownsamplingFilter(voxel_size=0.05))
    
    point_cloud_path = 'data/cloud.ply'
    polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.float32)
    
    algorithms = [
        ('poisson', {'depth': 9}),
        ('ball_pivoting', {}),
        ('convex_hull', {}),
        ('point_cloud', {'point_size': 0.02}),
    ]
    
    try:
        print(f"Loading: {point_cloud_path}")
        point_cloud = pipeline.load_point_cloud(point_cloud_path)
        extracted = pipeline.extract_region(point_cloud, polygon)
        processed = pipeline.process_point_cloud(extracted)
        
        os.makedirs('output', exist_ok=True)
        
        for algo_name, params in algorithms:
            print(f"\nGenerating mesh with {algo_name}...")
            mesh = pipeline.generate_mesh(processed, algorithm=algo_name, **params)
            
            output_path = f'output/mesh_{algo_name}.glb'
            pipeline.export_mesh(mesh, output_path)
            print(f"✓ {algo_name}: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
            print(f"  Exported to: {output_path}")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def example_4_z_axis_constraints():
    """
    Extract with Z-axis constraints (e.g., terrain height limits).
    """
    print("\n=== Example 4: Z-Axis Constraints ===\n")
    
    pipeline = PointCloudToMeshPipeline()
    
    point_cloud_path = 'data/aerial_cloud.las'
    polygon = np.array([[0, 0], [500, 0], [500, 500], [0, 500]], dtype=np.float32)
    
    # Extract only points between 100m and 150m altitude
    z_min = 100.0
    z_max = 150.0
    
    try:
        print(f"Loading: {point_cloud_path}")
        point_cloud = pipeline.load_point_cloud(point_cloud_path)
        
        print(f"Extracting region with Z constraints [{z_min}, {z_max}]...")
        extracted = pipeline.extract_region(point_cloud, polygon, z_min=z_min, z_max=z_max)
        print(f"✓ Extracted {extracted.num_points()} points")
        
        processed = pipeline.process_point_cloud(extracted)
        mesh = pipeline.generate_mesh(processed, algorithm='poisson')
        
        os.makedirs('output', exist_ok=True)
        pipeline.export_mesh(mesh, 'output/mesh_constrained.glb')
        print(f"✓ Generated mesh: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def example_5_different_export_formats():
    """
    Generate mesh and export to different formats.
    """
    print("\n=== Example 5: Multiple Export Formats ===\n")
    
    pipeline = PointCloudToMeshPipeline()
    pipeline.add_filter(DownsamplingFilter(voxel_size=0.01))
    
    point_cloud_path = 'data/scan.xyz'
    polygon = np.array([[0, 0], [50, 0], [50, 50], [0, 50]], dtype=np.float32)
    
    export_formats = [
        'output/model.glb',   # glTF binary (web)
        'output/model.gltf',  # glTF JSON (web)
        'output/model.obj',   # Wavefront OBJ (universal)
        'output/model.stl',   # STL (3D printing)
        'output/model.ply',   # PLY (point-based)
    ]
    
    try:
        print(f"Loading: {point_cloud_path}")
        point_cloud = pipeline.load_point_cloud(point_cloud_path)
        extracted = pipeline.extract_region(point_cloud, polygon)
        processed = pipeline.process_point_cloud(extracted)
        mesh = pipeline.generate_mesh(processed, algorithm='poisson')
        
        os.makedirs('output', exist_ok=True)
        
        print(f"\nExporting to multiple formats...")
        for export_path in export_formats:
            pipeline.export_mesh(mesh, export_path)
            print(f"✓ {export_path}")
        
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == '__main__':
    print("=" * 60)
    print("Point Cloud to Mesh Conversion - Examples")
    print("=" * 60)
    
    # Run examples
    try:
        example_1_simple_extraction_and_generation()
    except FileNotFoundError:
        print("\nNote: Example 1 requires sample data files.")
        print("Replace 'data/sample_cloud.las' with your actual point cloud file.")
    
    try:
        example_2_with_filtering_and_normalization()
    except FileNotFoundError:
        print("\nNote: Example 2 requires sample data files.")
    
    try:
        example_3_multiple_algorithms()
    except FileNotFoundError:
        print("\nNote: Example 3 requires sample data files.")
    
    try:
        example_4_z_axis_constraints()
    except FileNotFoundError:
        print("\nNote: Example 4 requires sample data files.")
    
    try:
        example_5_different_export_formats()
    except FileNotFoundError:
        print("\nNote: Example 5 requires sample data files.")
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)
