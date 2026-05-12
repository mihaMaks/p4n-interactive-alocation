"""
Implementation of point cloud processing service.
"""
import os
import sys
from typing import Optional
import numpy as np
from ..point_cloud import PointCloudLoaderFactory, PolygonExtractorService
from ..point_cloud import OutlierRemovalFilter, DownsamplingFilter
from ..point_cloud import CenterNormalizer, ScaleNormalizer, CompositeNormalizer
from ..point_cloud.transforms import transform_user_polygon
from ..model import PointCloudToMeshPipeline
from .models import PointCloudProcessingService, APIResponse


class DefaultPointCloudProcessingService(PointCloudProcessingService):
    """Default implementation of point cloud processing service."""
    
    def __init__(self):
        """Initialize service with default components."""
        self.pipeline = PointCloudToMeshPipeline()
        
        # Add default filters
        self.pipeline.add_filter(OutlierRemovalFilter(neighbors=20, std_ratio=2.0))
        self.pipeline.add_filter(DownsamplingFilter(voxel_size=0.01))
        
        # Center so the mesh sits at the viewer origin, but do NOT scale —
        # preserving real-world metres so size correlates with vehicle sizes.
        self.pipeline.add_normalizer(CenterNormalizer())
    
    def load_point_cloud(self, filepath: str):
        """Load point cloud from file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Point cloud file not found: {filepath}")
        
        return self.pipeline.load_point_cloud(filepath)
    
    def extract_region(self, point_cloud, polygon, z_min=None, z_max=None):
        """Extract region from point cloud."""
        polygon_array = np.array(polygon, dtype=np.float32)
        return self.pipeline.extract_region(point_cloud, polygon_array, z_min, z_max)
    
    def process_point_cloud(self, point_cloud):
        """Apply filters and normalizers."""
        return self.pipeline.process_point_cloud(point_cloud)
    
    def generate_mesh(self, point_cloud, algorithm: str = 'poisson', **kwargs):
        """Generate mesh from point cloud."""
        return self.pipeline.generate_mesh(point_cloud, algorithm, **kwargs)
    
    def export_mesh(self, mesh, filepath: str):
        """Export mesh to file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.pipeline.export_mesh(mesh, filepath)


class ProcessingServiceFacade:
    """Facade for simplified point cloud processing."""
    
    def __init__(self, service: Optional[PointCloudProcessingService] = None):
        """Initialize with service implementation."""
        self.service = service or DefaultPointCloudProcessingService()
    
    def extract_and_generate(
        self,
        point_cloud_path: str,
        polygon: list,
        output_path: str,
        algorithm: str = 'poisson',
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
        **kwargs
    ) -> APIResponse:
        """
        Complete pipeline in one call.
        
        Args:
            point_cloud_path: Path to input point cloud
            polygon: List of [x, y] vertices
            output_path: Path for output mesh
            algorithm: Mesh generation algorithm
            z_min: Minimum z coordinate
            z_max: Maximum z coordinate
            **kwargs: Additional generator parameters
            
        Returns:
            APIResponse with success status
        """
        try:
            # Load and extract
            point_cloud = self.service.load_point_cloud(point_cloud_path)
            extracted = self.service.extract_region(point_cloud, polygon, z_min, z_max)
            
            # Process
            processed = self.service.process_point_cloud(extracted)
            
            # Generate
            mesh = self.service.generate_mesh(processed, algorithm, **kwargs)
            
            # Export
            self.service.export_mesh(mesh, output_path)
            
            return APIResponse(
                success=True,
                data={
                    'output_path': output_path,
                    'num_vertices': len(mesh.vertices),
                    'num_faces': len(mesh.faces),
                }
            )
        
        except Exception as e:
            return APIResponse(
                success=False,
                error=str(e)
            )
    
    def extract_region(
        self,
        point_cloud_path: str,
        polygon: list,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
    ) -> APIResponse:
        """Extract region from point cloud and return statistics."""
        try:
            print(f"Loading point cloud: {point_cloud_path}", file=sys.stderr)
            point_cloud = self.service.load_point_cloud(point_cloud_path)
            print(f"Loaded point cloud with {len(point_cloud.get_points())} points", file=sys.stderr)
            cloud_bounds = point_cloud.get_bounds()
            
            # Transform coordinates if needed
            print(f"Original polygon: {polygon}", file=sys.stderr)
            print(f"Polygon type: {type(polygon)}, length: {len(polygon) if polygon else 'None'}", file=sys.stderr)
            transformed_polygon = transform_user_polygon(polygon, point_cloud_bounds=cloud_bounds)
            print(f"Transformed polygon: {transformed_polygon}", file=sys.stderr)
            print(f"Transformed polygon type: {type(transformed_polygon)}, length: {len(transformed_polygon) if transformed_polygon else 'None'}", file=sys.stderr)
            
            print(f"Extracting region with transformed polygon", file=sys.stderr)
            extracted = self.service.extract_region(point_cloud, transformed_polygon, z_min, z_max)
            print(f"Extracted {len(extracted.get_points())} points from region", file=sys.stderr)
            
            # Get statistics and handle empty results explicitly.
            points = extracted.get_points()
            cloud_min, cloud_max = cloud_bounds
            poly_arr = np.array(transformed_polygon, dtype=np.float64)
            poly_min = poly_arr.min(axis=0).tolist() if len(poly_arr) else None
            poly_max = poly_arr.max(axis=0).tolist() if len(poly_arr) else None

            if len(points) == 0:
                reason = "No points found in the selected polygon area."
                hint = "Check coordinate system and polygon bounds."

                if poly_min and poly_max:
                    outside = (
                        poly_max[0] < float(cloud_min[0])
                        or poly_min[0] > float(cloud_max[0])
                        or poly_max[1] < float(cloud_min[1])
                        or poly_min[1] > float(cloud_max[1])
                    )
                    if outside:
                        reason = "Selected polygon is outside the point-cloud extent."
                        hint = "Use the world map polygon near the uploaded point-cloud location or verify CRS transformation."

                return APIResponse(
                    success=False,
                    error=f"{reason} {hint}",
                    data={
                        'num_points': 0,
                        'point_count': 0,
                        'reason': reason,
                        'hint': hint,
                        'point_cloud_bounds_min': cloud_min.tolist(),
                        'point_cloud_bounds_max': cloud_max.tolist(),
                        'polygon_bounds_min': poly_min,
                        'polygon_bounds_max': poly_max,
                        'coordinate_transformed': transformed_polygon != polygon,
                        'original_polygon': polygon,
                        'transformed_polygon': transformed_polygon,
                    }
                )

            bounds_min, bounds_max = extracted.get_bounds()
            
            response = APIResponse(
                success=True,
                data={
                    'num_points': len(points),
                    'point_count': len(points),
                    'bounds_min': bounds_min.tolist(),
                    'bounds_max': bounds_max.tolist(),
                    'point_cloud_bounds_min': cloud_min.tolist(),
                    'point_cloud_bounds_max': cloud_max.tolist(),
                    'polygon_bounds_min': poly_min,
                    'polygon_bounds_max': poly_max,
                    'coordinate_transformed': transformed_polygon != polygon,
                    'original_polygon': polygon,
                    'transformed_polygon': transformed_polygon,
                }
            )

            if len(points) < 200:
                response.data['warning'] = (
                    "Very few points were extracted. The polygon may be too small, partly outside data coverage, "
                    "or transformed to a nearby but not exact location."
                )
                response.data['hint'] = (
                    "Try expanding the selected area on the map or verify the uploaded point cloud corresponds to that location."
                )

            return response
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Extract region error: {str(e)}", file=sys.stderr)
            print(f"Traceback: {error_details}", file=sys.stderr)
            return APIResponse(
                success=False,
                error=str(e)
            )
    
    def generate_mesh(
        self,
        point_cloud_path: str,
        polygon: list,
        output_path: str,
        algorithm: str = 'poisson',
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
        **kwargs
    ) -> APIResponse:
        """Generate mesh from point cloud region."""
        try:
            print(f"Loading point cloud for mesh generation: {point_cloud_path}")
            point_cloud = self.service.load_point_cloud(point_cloud_path)
            print(f"Loaded point cloud with {len(point_cloud.get_points())} points")
            cloud_bounds = point_cloud.get_bounds()
            
            # Transform coordinates if needed
            print(f"Original polygon: {polygon[:3]}... (showing first 3 vertices)")
            transformed_polygon = transform_user_polygon(polygon, point_cloud_bounds=cloud_bounds)
            print(f"Transformed polygon: {transformed_polygon[:3]}... (showing first 3 vertices)")
            
            print(f"Extracting region for mesh generation")
            extracted = self.service.extract_region(point_cloud, transformed_polygon, z_min, z_max)
            print(f"Extracted {len(extracted.get_points())} points")

            if len(extracted.get_points()) == 0:
                return APIResponse(
                    success=False,
                    error="No points found in the selected polygon area. Mesh generation aborted.",
                    data={
                        'num_points': 0,
                        'point_count': 0,
                        'coordinate_transformed': transformed_polygon != polygon,
                        'original_polygon': polygon,
                        'transformed_polygon': transformed_polygon,
                    }
                )
            
            print(f"Processing point cloud")
            processed = self.service.process_point_cloud(extracted)
            print(f"Processed point cloud has {len(processed.get_points())} points")
            
            print(f"Generating mesh with algorithm: {algorithm}")
            mesh = self.service.generate_mesh(processed, algorithm, **kwargs)
            print(f"Generated mesh with {len(mesh.vertices)} vertices and {len(mesh.faces)} faces")
            
            print(f"Exporting mesh to: {output_path}")
            self.service.export_mesh(mesh, output_path)
            print(f"Mesh exported successfully")
            
            return APIResponse(
                success=True,
                data={
                    'output_path': output_path,
                    'algorithm': algorithm,
                    'num_vertices': len(mesh.vertices),
                    'num_faces': len(mesh.faces),
                    'coordinate_transformed': transformed_polygon != polygon,
                    'original_polygon': polygon,
                    'transformed_polygon': transformed_polygon,
                }
            )
        
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Generate mesh error: {str(e)}")
            print(f"Traceback: {error_details}")
            return APIResponse(
                success=False,
                error=str(e)
            )
