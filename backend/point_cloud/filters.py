"""
Filters and normalizers for point cloud processing.
"""
from typing import Optional
import numpy as np
from .core import PointCloud, PointCloudFilter, PointCloudNormalizer
from .data import InMemoryPointCloud


class OutlierRemovalFilter(PointCloudFilter):
    """Remove statistical outliers from point cloud."""
    
    def __init__(self, neighbors: int = 20, std_ratio: float = 2.0):
        """
        Initialize outlier filter.
        
        Args:
            neighbors: Number of neighbors to check
            std_ratio: Standard deviation ratio threshold
        """
        self.neighbors = neighbors
        self.std_ratio = std_ratio
    
    def filter(self, point_cloud: PointCloud) -> PointCloud:
        """Remove outliers based on statistical distance."""
        try:
            from scipy.spatial import KDTree
        except ImportError:
            raise ImportError("scipy is required. Install with: pip install scipy")
        
        points = point_cloud.get_points()
        
        # Build KDTree
        tree = KDTree(points)
        
        # Find distances to neighbors
        distances, _ = tree.query(points, k=self.neighbors + 1)
        distances = distances[:, 1:]  # Exclude self
        
        # Calculate mean and std of neighbor distances
        mean_dist = distances.mean(axis=1)
        std_dist = distances.std(axis=1)
        
        # Keep points within threshold
        threshold = mean_dist + self.std_ratio * std_dist
        mask = distances.mean(axis=1) < threshold
        
        # Extract filtered data
        filtered_points = points[mask]
        
        colors = point_cloud.get_colors()
        filtered_colors = colors[mask] if colors is not None else None
        
        normals = point_cloud.get_normals()
        filtered_normals = normals[mask] if normals is not None else None
        
        return InMemoryPointCloud(filtered_points, filtered_colors, filtered_normals)


class DownsamplingFilter(PointCloudFilter):
    """Downsample point cloud using voxel grid."""
    
    def __init__(self, voxel_size: float = 0.01):
        """
        Initialize downsampling filter.
        
        Args:
            voxel_size: Size of voxel for downsampling
        """
        self.voxel_size = voxel_size
    
    def filter(self, point_cloud: PointCloud) -> PointCloud:
        """Downsample using voxel grid."""
        points = point_cloud.get_points()
        colors = point_cloud.get_colors()
        normals = point_cloud.get_normals()
        
        # Compute voxel coordinates
        voxel_coords = (points / self.voxel_size).astype(np.int32)
        
        # Get unique voxels
        unique_voxels, indices = np.unique(voxel_coords, axis=0, return_index=True)
        
        # Extract downsampled data
        downsampled_points = points[indices]
        downsampled_colors = colors[indices] if colors is not None else None
        downsampled_normals = normals[indices] if normals is not None else None
        
        return InMemoryPointCloud(downsampled_points, downsampled_colors, downsampled_normals)


class CenterNormalizer(PointCloudNormalizer):
    """Normalize point cloud to be centered at origin."""
    
    def normalize(self, point_cloud: PointCloud) -> PointCloud:
        """Center point cloud at origin."""
        points = point_cloud.get_points()
        
        # Calculate center
        center = points.mean(axis=0)
        
        # Center points
        normalized_points = points - center
        
        # Normals don't change, colors stay same
        colors = point_cloud.get_colors()
        normals = point_cloud.get_normals()
        
        return InMemoryPointCloud(normalized_points, colors, normals)


class ScaleNormalizer(PointCloudNormalizer):
    """Normalize point cloud to fit within unit cube."""
    
    def normalize(self, point_cloud: PointCloud) -> PointCloud:
        """Scale point cloud to fit in [-1, 1] range."""
        points = point_cloud.get_points()
        
        # Calculate bounds
        min_point, max_point = point_cloud.get_bounds()
        
        # Calculate scale
        range_vec = max_point - min_point
        max_range = np.max(range_vec)
        
        if max_range == 0:
            scale = 1.0
        else:
            scale = 2.0 / max_range
        
        # Scale points
        scaled_points = (points - (min_point + max_point) / 2) * scale
        
        # Colors and normals don't change
        colors = point_cloud.get_colors()
        normals = point_cloud.get_normals()
        
        return InMemoryPointCloud(scaled_points, colors, normals)


class CompositeNormalizer(PointCloudNormalizer):
    """Apply multiple normalizers in sequence."""
    
    def __init__(self, normalizers: list):
        """Initialize with list of normalizers."""
        self.normalizers = normalizers
    
    def normalize(self, point_cloud: PointCloud) -> PointCloud:
        """Apply all normalizers in sequence."""
        result = point_cloud
        for normalizer in self.normalizers:
            result = normalizer.normalize(result)
        return result
