"""
Core abstractions for point cloud processing.
Defines interfaces based on SOLID principles.
"""
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
import numpy as np


class PointCloud(ABC):
    """Abstract base class for point cloud data."""
    
    @abstractmethod
    def get_points(self) -> np.ndarray:
        """Returns points as (N, 3) array with x, y, z coordinates."""
        pass
    
    @abstractmethod
    def get_colors(self) -> Optional[np.ndarray]:
        """Returns colors as (N, 3) array with RGB values, or None."""
        pass
    
    @abstractmethod
    def get_normals(self) -> Optional[np.ndarray]:
        """Returns normals as (N, 3) array, or None."""
        pass
    
    @abstractmethod
    def get_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (min_point, max_point) bounding box."""
        pass


class PointCloudLoader(ABC):
    """Abstract base class for loading point clouds from various formats."""
    
    @abstractmethod
    def load(self, filepath: str) -> PointCloud:
        """Load point cloud from file."""
        pass
    
    @abstractmethod
    def supports(self, filename: str) -> bool:
        """Check if loader supports this file format."""
        pass


class PolygonExtractor(ABC):
    """Abstract base class for extracting regions from point clouds."""
    
    @abstractmethod
    def extract(self, point_cloud: PointCloud, 
                polygon: np.ndarray) -> PointCloud:
        """
        Extract points within polygon boundary.
        
        Args:
            point_cloud: Input point cloud
            polygon: Polygon vertices as (M, 2) array [x, y] in world coordinates
            
        Returns:
            Extracted point cloud
        """
        pass


class PointCloudFilter(ABC):
    """Abstract base class for filtering point clouds."""
    
    @abstractmethod
    def filter(self, point_cloud: PointCloud) -> PointCloud:
        """Apply filter and return filtered point cloud."""
        pass


class PointCloudNormalizer(ABC):
    """Abstract base class for normalizing point clouds."""
    
    @abstractmethod
    def normalize(self, point_cloud: PointCloud) -> PointCloud:
        """Normalize point cloud and return normalized version."""
        pass
