"""
Polygon extraction from point clouds using various algorithms.
"""
from typing import Optional
import numpy as np
from shapely.geometry import Polygon as ShapelyPolygon, Point
from .core import PointCloud, PolygonExtractor
from .data import InMemoryPointCloud


class ShapelyPolygonExtractor(PolygonExtractor):
    """Extract points within polygon using Shapely library."""
    
    def extract(
        self,
        point_cloud: PointCloud,
        polygon: np.ndarray,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None
    ) -> PointCloud:
        """
        Extract points within polygon boundary.
        
        Args:
            point_cloud: Input point cloud
            polygon: Polygon vertices as (M, 2) array [x, y]
            z_min: Minimum z coordinate (if None, no filter)
            z_max: Maximum z coordinate (if None, no filter)
            
        Returns:
            Extracted point cloud
        """
        points = point_cloud.get_points()
        
        # Create Shapely polygon from vertices
        if len(polygon) < 3:
            raise ValueError("Polygon must have at least 3 vertices")
        
        shapely_polygon = ShapelyPolygon(polygon)
        
        # Get polygon bounds for pre-filtering
        min_x, min_y, max_x, max_y = shapely_polygon.bounds
        
        # Pre-filter points using bounding box (fast)
        bbox_mask = (
            (points[:, 0] >= min_x) & (points[:, 0] <= max_x) &
            (points[:, 1] >= min_y) & (points[:, 1] <= max_y)
        )
        
        # Only check points within bounding box
        candidate_points = points[bbox_mask]
        
        if len(candidate_points) == 0:
            # Return empty point cloud
            return InMemoryPointCloud(
                np.empty((0, 3), dtype=np.float32),
                np.empty((0, 3), dtype=np.uint8) if point_cloud.get_colors() is not None else None,
                np.empty((0, 3), dtype=np.float32) if point_cloud.get_normals() is not None else None
            )
        
        # Use vectorized Shapely operations for better performance
        # Create Point objects for candidates
        candidate_mask = np.zeros(len(candidate_points), dtype=bool)
        
        # Process in batches to avoid memory issues
        batch_size = 10000
        for i in range(0, len(candidate_points), batch_size):
            batch_end = min(i + batch_size, len(candidate_points))
            batch_points = candidate_points[i:batch_end]
            
            # Create Shapely Points for this batch
            shapely_points = [Point(p[0], p[1]) for p in batch_points]
            
            # Check containment for batch
            batch_mask = np.array([shapely_polygon.contains(pt) for pt in shapely_points])
            candidate_mask[i:batch_end] = batch_mask
        
        # Apply z-bounds filter if specified
        if z_min is not None:
            candidate_mask &= candidate_points[:, 2] >= z_min
        if z_max is not None:
            candidate_mask &= candidate_points[:, 2] <= z_max
        
        # Extract final points
        extracted_points = candidate_points[candidate_mask]
        
        # Extract corresponding colors and normals if they exist
        extracted_colors = None
        if point_cloud.get_colors() is not None:
            colors = point_cloud.get_colors()
            extracted_colors = colors[bbox_mask][candidate_mask]
        
        extracted_normals = None
        if point_cloud.get_normals() is not None:
            normals = point_cloud.get_normals()
            extracted_normals = normals[bbox_mask][candidate_mask]
        
        return InMemoryPointCloud(extracted_points, extracted_colors, extracted_normals)


class FastBoundingBoxExtractor(PolygonExtractor):
    """Fast extraction using axis-aligned bounding box (for simple rectangular areas)."""
    
    def extract(
        self,
        point_cloud: PointCloud,
        polygon: np.ndarray,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None
    ) -> PointCloud:
        """
        Extract points within bounding box (polygon should be rectangular).
        Much faster than general polygon extraction.
        """
        points = point_cloud.get_points()
        
        # Calculate bounding box from polygon
        x_coords = polygon[:, 0]
        y_coords = polygon[:, 1]
        
        x_min, x_max = x_coords.min(), x_coords.max()
        y_min, y_max = y_coords.min(), y_coords.max()
        
        # Create mask
        mask = (
            (points[:, 0] >= x_min) & (points[:, 0] <= x_max) &
            (points[:, 1] >= y_min) & (points[:, 1] <= y_max)
        )
        
        if z_min is not None:
            mask &= points[:, 2] >= z_min
        
        if z_max is not None:
            mask &= points[:, 2] <= z_max
        
        # Extract data
        extracted_points = points[mask]
        
        colors = point_cloud.get_colors()
        extracted_colors = colors[mask] if colors is not None else None
        
        normals = point_cloud.get_normals()
        extracted_normals = normals[mask] if normals is not None else None
        
        return InMemoryPointCloud(extracted_points, extracted_colors, extracted_normals)


class PolygonExtractorService:
    """Service for extracting polygon regions, with strategy selection."""
    
    def __init__(self):
        """Initialize with default extractors."""
        self._general_extractor = ShapelyPolygonExtractor()
        self._fast_extractor = FastBoundingBoxExtractor()
    
    def _is_rectangle(self, polygon: np.ndarray, tolerance: float = 0.001) -> bool:
        """Check if polygon is approximately rectangular."""
        if len(polygon) != 4:
            return False
        
        # Check if all angles are approximately 90 degrees
        # This is a simple heuristic check
        edges = np.vstack([polygon, polygon[0]]) - np.vstack([polygon[-1:], polygon])
        dot_products = [
            np.dot(edges[i], edges[(i+1) % 4])
            for i in range(4)
        ]
        
        for dot in dot_products:
            if abs(dot) > tolerance:
                return False
        
        return True
    
    def extract(
        self,
        point_cloud: PointCloud,
        polygon: np.ndarray,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
        fast: bool = True
    ) -> PointCloud:
        """
        Extract polygon region with automatic strategy selection.
        
        Args:
            point_cloud: Input point cloud
            polygon: Polygon vertices as (M, 2) array [x, y]
            z_min: Minimum z coordinate
            z_max: Maximum z coordinate
            fast: If True, use fast extraction for rectangular areas
            
        Returns:
            Extracted point cloud
        """
        # Select extraction strategy
        if fast and self._is_rectangle(polygon):
            extractor = self._fast_extractor
        else:
            extractor = self._general_extractor
        
        return extractor.extract(point_cloud, polygon, z_min, z_max)
