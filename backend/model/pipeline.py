"""
High-level API for point cloud to 3D model pipeline.
Facade pattern for easy orchestration.
"""
from typing import Optional, List
import numpy as np
from ..point_cloud import (
    PointCloud,
    PointCloudLoaderFactory,
    PolygonExtractorService,
    PointCloudFilter,
    PointCloudNormalizer,
)
from .core import Mesh, ModelGenerator, ModelExporter
from .generators import (
    PoissonMeshGenerator,
    BallPivotingMeshGenerator,
    ConvexHullMeshGenerator,
    PointCloudMeshGenerator,
)
from .exporters import ModelExporterFactory


class PointCloudToMeshPipeline:
    """Orchestrates the entire pipeline from point cloud to 3D model."""
    
    def __init__(self):
        """Initialize pipeline with default components."""
        self.loader_factory = PointCloudLoaderFactory()
        self.extractor_service = PolygonExtractorService()
        self.exporter_factory = ModelExporterFactory()
        
        self.generators = {
            'poisson': PoissonMeshGenerator(),
            'ball_pivoting': BallPivotingMeshGenerator(),
            'convex_hull': ConvexHullMeshGenerator(),
            'point_cloud': PointCloudMeshGenerator(),
        }
        
        self.filters: List[PointCloudFilter] = []
        self.normalizers: List[PointCloudNormalizer] = []
    
    def add_filter(self, filter_obj: PointCloudFilter) -> 'PointCloudToMeshPipeline':
        """Add a filter to the pipeline."""
        self.filters.append(filter_obj)
        return self
    
    def add_normalizer(self, normalizer: PointCloudNormalizer) -> 'PointCloudToMeshPipeline':
        """Add a normalizer to the pipeline."""
        self.normalizers.append(normalizer)
        return self
    
    def load_point_cloud(self, filepath: str) -> PointCloud:
        """Load point cloud from file."""
        return self.loader_factory.load(filepath)
    
    def extract_region(
        self,
        point_cloud: PointCloud,
        polygon: np.ndarray,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
    ) -> PointCloud:
        """Extract polygon region from point cloud."""
        return self.extractor_service.extract(point_cloud, polygon, z_min, z_max)
    
    def process_point_cloud(self, point_cloud: PointCloud) -> PointCloud:
        """Apply all filters and normalizers."""
        result = point_cloud
        
        # Apply filters
        for filter_obj in self.filters:
            result = filter_obj.filter(result)
        
        # Apply normalizers
        for normalizer in self.normalizers:
            result = normalizer.normalize(result)
        
        return result
    
    def generate_mesh(
        self,
        point_cloud: PointCloud,
        algorithm: str = 'poisson',
        **kwargs
    ) -> Mesh:
        """Generate mesh from point cloud using specified algorithm."""
        if algorithm not in self.generators:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        
        generator = self.generators[algorithm]
        points = point_cloud.get_points()
        colors = point_cloud.get_colors()
        normals = point_cloud.get_normals()
        
        return generator.generate(points, colors, normals, **kwargs)
    
    def export_mesh(self, mesh: Mesh, filepath: str) -> None:
        """Export mesh to file."""
        self.exporter_factory.export(mesh, filepath)
    
    def process_and_export(
        self,
        point_cloud_path: str,
        polygon: np.ndarray,
        mesh_output_path: str,
        algorithm: str = 'poisson',
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
        **generator_kwargs
    ) -> Mesh:
        """
        Complete pipeline: load -> extract -> process -> generate -> export.
        
        Args:
            point_cloud_path: Input point cloud file
            polygon: Polygon boundary (M, 2) array
            mesh_output_path: Output mesh file
            algorithm: Mesh generation algorithm
            z_min: Minimum z coordinate
            z_max: Maximum z coordinate
            **generator_kwargs: Additional arguments for mesh generator
            
        Returns:
            Generated mesh
        """
        # Load
        point_cloud = self.load_point_cloud(point_cloud_path)
        
        # Extract region
        extracted = self.extract_region(point_cloud, polygon, z_min, z_max)
        
        # Process
        processed = self.process_point_cloud(extracted)
        
        # Generate
        mesh = self.generate_mesh(processed, algorithm, **generator_kwargs)
        
        # Export
        self.export_mesh(mesh, mesh_output_path)
        
        return mesh
