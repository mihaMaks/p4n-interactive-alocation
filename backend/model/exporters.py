"""
Mesh exporters for various 3D file formats.
"""
from typing import List
import numpy as np
from .core import ModelExporter, Mesh


class GLTFExporter(ModelExporter):
    """Export mesh to glTF/glTF2 format."""
    
    def export(self, mesh: Mesh, filepath: str) -> None:
        """Export mesh to glTF format."""
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create Open3D mesh
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
        
        if mesh.colors is not None:
            o3d_mesh.vertex_colors = o3d.utility.Vector3dVector(mesh.colors / 255.0)
        
        # Write glTF
        o3d.io.write_triangle_mesh(filepath, o3d_mesh)
    
    def supports(self, filename: str) -> bool:
        """Check if file is glTF format."""
        return filename.lower().endswith(('.gltf', '.glb'))


class OBJExporter(ModelExporter):
    """Export mesh to OBJ format."""
    
    def export(self, mesh: Mesh, filepath: str) -> None:
        """Export mesh to OBJ format."""
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create Open3D mesh
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
        
        if mesh.colors is not None:
            o3d_mesh.vertex_colors = o3d.utility.Vector3dVector(mesh.colors / 255.0)
        
        # Write OBJ
        o3d.io.write_triangle_mesh(filepath, o3d_mesh)
    
    def supports(self, filename: str) -> bool:
        """Check if file is OBJ format."""
        return filename.lower().endswith('.obj')


class STLExporter(ModelExporter):
    """Export mesh to STL format."""
    
    def export(self, mesh: Mesh, filepath: str) -> None:
        """Export mesh to STL format."""
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create Open3D mesh
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
        
        # Write STL
        o3d.io.write_triangle_mesh(filepath, o3d_mesh)
    
    def supports(self, filename: str) -> bool:
        """Check if file is STL format."""
        return filename.lower().endswith('.stl')


class PLYExporter(ModelExporter):
    """Export mesh to PLY format."""
    
    def export(self, mesh: Mesh, filepath: str) -> None:
        """Export mesh to PLY format."""
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create Open3D mesh
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
        
        if mesh.colors is not None:
            o3d_mesh.vertex_colors = o3d.utility.Vector3dVector(mesh.colors / 255.0)
        
        # Write PLY
        o3d.io.write_triangle_mesh(filepath, o3d_mesh)
    
    def supports(self, filename: str) -> bool:
        """Check if file is PLY format."""
        return filename.lower().endswith('.ply')


class ModelExporterFactory:
    """Factory for selecting appropriate exporter based on file format."""
    
    def __init__(self):
        """Initialize with default exporters."""
        self._exporters: List[ModelExporter] = [
            GLTFExporter(),
            OBJExporter(),
            STLExporter(),
            PLYExporter(),
        ]
    
    def register_exporter(self, exporter: ModelExporter) -> None:
        """Register a custom exporter."""
        self._exporters.insert(0, exporter)
    
    def export(self, mesh: Mesh, filepath: str) -> None:
        """Export mesh using appropriate exporter."""
        for exporter in self._exporters:
            if exporter.supports(filepath):
                exporter.export(mesh, filepath)
                return
        
        raise ValueError(f"No exporter found for file: {filepath}")
