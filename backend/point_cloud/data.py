"""
Concrete implementations of point cloud data structures.
"""
from typing import Optional, Tuple
import numpy as np
from .core import PointCloud


class InMemoryPointCloud(PointCloud):
    """In-memory implementation of point cloud."""
    
    def __init__(
        self,
        points: np.ndarray,
        colors: Optional[np.ndarray] = None,
        normals: Optional[np.ndarray] = None
    ):
        """
        Initialize point cloud.
        
        Args:
            points: (N, 3) array of x, y, z coordinates
            colors: (N, 3) array of RGB values [0-255], optional
            normals: (N, 3) array of normal vectors, optional
        """
        if points.shape[1] != 3:
            raise ValueError("Points must have shape (N, 3)")
        
        if colors is not None and colors.shape[0] != points.shape[0]:
            raise ValueError("Colors must have same number of points as input")
        
        if normals is not None and normals.shape[0] != points.shape[0]:
            raise ValueError("Normals must have same number of points as input")
        
        self._points = points.astype(np.float32)
        self._colors = colors.astype(np.uint8) if colors is not None else None
        self._normals = normals.astype(np.float32) if normals is not None else None
    
    def get_points(self) -> np.ndarray:
        """Returns copy of points array."""
        return self._points.copy()
    
    def get_colors(self) -> Optional[np.ndarray]:
        """Returns copy of colors array or None."""
        return self._colors.copy() if self._colors is not None else None
    
    def get_normals(self) -> Optional[np.ndarray]:
        """Returns copy of normals array or None."""
        return self._normals.copy() if self._normals is not None else None
    
    def get_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns bounding box (min_point, max_point)."""
        min_point = self._points.min(axis=0)
        max_point = self._points.max(axis=0)
        return min_point, max_point
    
    def num_points(self) -> int:
        """Returns number of points."""
        return len(self._points)
