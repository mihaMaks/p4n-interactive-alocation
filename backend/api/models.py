"""
Core abstractions for API routes and services.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import json


class APIRequest(ABC):
    """Base class for API requests."""
    
    @abstractmethod
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate request data. Returns (is_valid, error_message)."""
        pass


class APIResponse:
    """Standardized API response."""
    
    def __init__(self, success: bool = True, data: Any = None, error: Optional[str] = None):
        self.success = success
        self.data = data
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error
        }


class PointCloudProcessingService(ABC):
    """Abstract service for point cloud processing."""
    
    @abstractmethod
    def load_point_cloud(self, filepath: str):
        """Load point cloud."""
        pass
    
    @abstractmethod
    def extract_region(self, point_cloud, polygon, z_min=None, z_max=None):
        """Extract region from point cloud."""
        pass
    
    @abstractmethod
    def generate_mesh(self, point_cloud, algorithm: str, **kwargs):
        """Generate mesh from point cloud."""
        pass
    
    @abstractmethod
    def export_mesh(self, mesh, filepath: str):
        """Export mesh to file."""
        pass


class ExtractPolygonRequest(APIRequest):
    """Request to extract polygon region from point cloud."""
    
    def __init__(self, data: Dict):
        self.point_cloud_path = data.get('point_cloud_path')
        self.polygon = data.get('polygon')  # List of [x, y] coordinates
        self.z_min = data.get('z_min')
        self.z_max = data.get('z_max')
        self.output_format = data.get('output_format', 'ply')
        
        # Debug print
        print(f"DEBUG ExtractPolygonRequest: polygon = {self.polygon}")
        print(f"DEBUG ExtractPolygonRequest: polygon type = {type(self.polygon)}")
        print(f"DEBUG ExtractPolygonRequest: polygon length = {len(self.polygon) if hasattr(self.polygon, '__len__') else 'no len'}")
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate request."""
        if not self.point_cloud_path:
            return False, "point_cloud_path is required"
        
        if not self.polygon or len(self.polygon) < 3:
            return False, "polygon must have at least 3 vertices"
        
        for vertex in self.polygon:
            if len(vertex) != 2:
                return False, "each polygon vertex must have [x, y]"
        
        return True, None


class GenerateMeshRequest(APIRequest):
    """Request to generate mesh from point cloud."""
    
    def __init__(self, data: Dict):
        self.point_cloud_path = data.get('point_cloud_path')
        self.polygon = data.get('polygon')
        self.algorithm = data.get('algorithm', 'poisson')
        self.z_min = data.get('z_min')
        self.z_max = data.get('z_max')
        self.output_path = data.get('output_path')
        self.generator_params = data.get('generator_params', {})
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate request."""
        if not self.point_cloud_path:
            return False, "point_cloud_path is required"
        
        if not self.polygon or len(self.polygon) < 3:
            return False, "polygon must have at least 3 vertices"
        
        valid_algorithms = ['poisson', 'ball_pivoting', 'convex_hull', 'point_cloud']
        if self.algorithm not in valid_algorithms:
            return False, f"algorithm must be one of {valid_algorithms}"
        
        return True, None
