"""
Point cloud loaders for various file formats.
Implements multiple file format support using composition.
"""
from typing import List, Optional
import numpy as np
from .core import PointCloudLoader, PointCloud
from .data import InMemoryPointCloud


class LASLoader(PointCloudLoader):
    """Loader for LAS/LAZ point cloud files."""
    
    def load(self, filepath: str) -> PointCloud:
        """Load LAS/LAZ file."""
        try:
            import laspy
        except ImportError:
            raise ImportError("laspy is required for LAS format. Install with: pip install laspy")
        
        # Configure laspy to use Lazrs backend for LAZ decompression
        try:
            # Try to configure Lazrs backend for .laz files
            if filepath.lower().endswith('.laz'):
                laspy.LazBackend.Lazrs.configure()
        except (AttributeError, ImportError) as e:
            print(f"Warning: Could not configure Lazrs backend for .laz files: {e}")
            print("Trying with default backend...")
        
        try:
            las_file = laspy.read(filepath)
        except Exception as e:
            raise RuntimeError(f"Failed to read LAS/LAZ file {filepath}: {str(e)}")
        
        # Extract XYZ coordinates
        points = np.vstack([
            las_file.x,
            las_file.y,
            las_file.z
        ]).T.astype(np.float32)
        
        # Extract colors if available
        colors = None
        if hasattr(las_file, 'red') and hasattr(las_file, 'green') and hasattr(las_file, 'blue'):
            colors = np.vstack([
                las_file.red,
                las_file.green,
                las_file.blue
            ]).T.astype(np.uint8)
        
        return InMemoryPointCloud(points, colors=colors)
    
    def supports(self, filename: str) -> bool:
        """Check if file is LAS/LAZ format."""
        return filename.lower().endswith(('.las', '.laz'))


class PLYLoader(PointCloudLoader):
    """Loader for PLY point cloud files."""
    
    def load(self, filepath: str) -> PointCloud:
        """Load PLY file."""
        try:
            from plyfile import PlyData
        except ImportError:
            raise ImportError("plyfile is required for PLY format. Install with: pip install plyfile")
        
        ply_data = PlyData.read(filepath)
        vertex_data = ply_data['vertex']
        
        # Extract XYZ coordinates
        points = np.vstack([
            vertex_data['x'],
            vertex_data['y'],
            vertex_data['z']
        ]).T.astype(np.float32)
        
        # Extract colors if available
        colors = None
        if all(prop in vertex_data for prop in ['red', 'green', 'blue']):
            colors = np.vstack([
                vertex_data['red'],
                vertex_data['green'],
                vertex_data['blue']
            ]).T.astype(np.uint8)
        
        return InMemoryPointCloud(points, colors=colors)
    
    def supports(self, filename: str) -> bool:
        """Check if file is PLY format."""
        return filename.lower().endswith('.ply')


class PCDLoader(PointCloudLoader):
    """Loader for PCD point cloud files (Open3D format)."""
    
    def load(self, filepath: str) -> PointCloud:
        """Load PCD file."""
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required for PCD format. Install with: pip install open3d")
        
        pcd = o3d.io.read_point_cloud(filepath)
        
        points = np.asarray(pcd.points).astype(np.float32)
        colors = None
        normals = None
        
        if pcd.has_colors():
            colors = (np.asarray(pcd.colors) * 255).astype(np.uint8)
        
        if pcd.has_normals():
            normals = np.asarray(pcd.normals).astype(np.float32)
        
        return InMemoryPointCloud(points, colors=colors, normals=normals)
    
    def supports(self, filename: str) -> bool:
        """Check if file is PCD format."""
        return filename.lower().endswith('.pcd')


class XYZLoader(PointCloudLoader):
    """Loader for simple XYZ text files."""
    
    def load(self, filepath: str) -> PointCloud:
        """Load XYZ text file."""
        # Load data: x y z [r g b]
        data = np.loadtxt(filepath)
        
        if data.shape[1] < 3:
            raise ValueError("XYZ file must have at least 3 columns (x, y, z)")
        
        points = data[:, :3].astype(np.float32)
        colors = None
        
        if data.shape[1] >= 6:
            colors = data[:, 3:6].astype(np.uint8)
        
        return InMemoryPointCloud(points, colors=colors)
    
    def supports(self, filename: str) -> bool:
        """Check if file is XYZ format."""
        return filename.lower().endswith(('.xyz', '.txt'))


class PointCloudLoaderFactory:
    """Factory for selecting appropriate loader based on file format."""
    
    def __init__(self):
        """Initialize with default loaders."""
        self._loaders: List[PointCloudLoader] = [
            LASLoader(),
            PLYLoader(),
            PCDLoader(),
            XYZLoader(),
        ]
    
    def register_loader(self, loader: PointCloudLoader) -> None:
        """Register a custom loader."""
        self._loaders.insert(0, loader)
    
    def load(self, filepath: str) -> PointCloud:
        """Load point cloud from file using appropriate loader."""
        for loader in self._loaders:
            if loader.supports(filepath):
                return loader.load(filepath)
        
        raise ValueError(f"No loader found for file: {filepath}")
