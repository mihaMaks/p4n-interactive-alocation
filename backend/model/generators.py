"""
Implementations of various 3D model generation algorithms.
"""
from typing import Optional
import numpy as np
from .core import ModelGenerator, Mesh


class PoissonMeshGenerator(ModelGenerator):
    """Generate mesh using Poisson surface reconstruction."""
    
    def generate(
        self,
        points: np.ndarray,
        colors: Optional[np.ndarray] = None,
        normals: Optional[np.ndarray] = None,
        depth: int = 9,
        **kwargs
    ) -> Mesh:
        """
        Generate mesh using Poisson reconstruction.
        
        Args:
            points: (N, 3) point coordinates
            colors: (N, 3) optional RGB colors
            normals: (N, 3) optional normal vectors
            depth: Maximum depth for octree
            **kwargs: Additional arguments
            
        Returns:
            Generated mesh
        """
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create Open3D point cloud
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        
        if colors is not None:
            pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)
        
        if normals is not None:
            pcd.normals = o3d.utility.Vector3dVector(normals)
        else:
            # Estimate normals if not provided
            pcd.estimate_normals()
        
        # Run Poisson reconstruction
        mesh_o3d, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd,
            depth=depth
        )
        
        # Extract mesh data
        vertices = np.asarray(mesh_o3d.vertices).astype(np.float32)
        faces = np.asarray(mesh_o3d.triangles).astype(np.uint32)
        
        mesh_colors = None
        if mesh_o3d.has_vertex_colors():
            mesh_colors = (np.asarray(mesh_o3d.vertex_colors) * 255).astype(np.uint8)
        
        mesh_normals = None
        if mesh_o3d.has_vertex_normals():
            mesh_normals = np.asarray(mesh_o3d.vertex_normals).astype(np.float32)
        
        return Mesh(vertices, faces, mesh_colors, mesh_normals)


class BallPivotingMeshGenerator(ModelGenerator):
    """Generate mesh using Ball Pivoting Algorithm."""
    
    def generate(
        self,
        points: np.ndarray,
        colors: Optional[np.ndarray] = None,
        normals: Optional[np.ndarray] = None,
        radii: Optional[list] = None,
        **kwargs
    ) -> Mesh:
        """
        Generate mesh using Ball Pivoting Algorithm.
        
        Args:
            points: (N, 3) point coordinates
            colors: (N, 3) optional RGB colors
            normals: (N, 3) optional normal vectors
            radii: List of radii for ball pivoting
            **kwargs: Additional arguments
            
        Returns:
            Generated mesh
        """
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create Open3D point cloud
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        
        if colors is not None:
            pcd.colors = o3d.utility.Vector3dVector(colors / 255.0)
        
        if normals is not None:
            pcd.normals = o3d.utility.Vector3dVector(normals)
        else:
            pcd.estimate_normals()
        
        # Set default radii if not provided
        if radii is None:
            # Estimate reasonable radii; convert pcd.points to numpy to avoid
            # pybind11 IntVector indexing error when using search results.
            pts_array = np.asarray(pcd.points)
            kd_tree = o3d.geometry.KDTreeFlann(pcd)
            avg_dist = 0.0
            sample_count = min(100, len(pts_array))
            for i in range(sample_count):
                _, indices, _ = kd_tree.search_knn_vector_3d(pts_array[i], 15)
                idx = np.asarray(indices)
                avg_dist += np.mean(np.linalg.norm(pts_array[idx] - pts_array[i], axis=1))
            avg_dist /= sample_count
            radii = [avg_dist, avg_dist * 2, avg_dist * 4]

        # Run Ball Pivoting
        mesh_o3d = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd,
            o3d.utility.DoubleVector(radii)
        )

        # Extract mesh data
        vertices = np.asarray(mesh_o3d.vertices).astype(np.float32)
        faces = np.asarray(mesh_o3d.triangles).astype(np.uint32)

        # Ball pivoting does not copy colors automatically; transfer them via
        # nearest-neighbour lookup from the original point cloud.
        mesh_colors = None
        if colors is not None and len(vertices) > 0:
            pc_colors_norm = colors.astype(np.float64) / 255.0
            kd_tree = o3d.geometry.KDTreeFlann(pcd)
            pts_array = np.asarray(pcd.points)
            mesh_colors_arr = np.zeros((len(vertices), 3), dtype=np.float64)
            for i, v in enumerate(vertices):
                _, idx, _ = kd_tree.search_knn_vector_3d(v.tolist(), 1)
                mesh_colors_arr[i] = pc_colors_norm[idx[0]]
            mesh_o3d.vertex_colors = o3d.utility.Vector3dVector(mesh_colors_arr)
            mesh_colors = (mesh_colors_arr * 255).astype(np.uint8)

        mesh_normals = None
        if mesh_o3d.has_vertex_normals():
            mesh_normals = np.asarray(mesh_o3d.vertex_normals).astype(np.float32)

        return Mesh(vertices, faces, mesh_colors, mesh_normals)


class ConvexHullMeshGenerator(ModelGenerator):
    """Generate mesh using Convex Hull."""
    
    def generate(
        self,
        points: np.ndarray,
        colors: Optional[np.ndarray] = None,
        normals: Optional[np.ndarray] = None,
        **kwargs
    ) -> Mesh:
        """
        Generate convex hull mesh.
        
        Args:
            points: (N, 3) point coordinates
            colors: (N, 3) optional RGB colors
            normals: (N, 3) optional normal vectors
            **kwargs: Additional arguments
            
        Returns:
            Generated mesh
        """
        try:
            from scipy.spatial import ConvexHull
        except ImportError:
            raise ImportError("scipy is required. Install with: pip install scipy")
        
        # Compute convex hull
        hull = ConvexHull(points)
        
        vertices = hull.points.astype(np.float32)
        faces = hull.simplices.astype(np.uint32)
        
        # Sample colors for vertices if provided
        mesh_colors = None
        if colors is not None:
            mesh_colors = colors[hull.vertices] if len(colors) > 0 else None
        
        return Mesh(vertices, faces, mesh_colors, None)


class PointCloudMeshGenerator(ModelGenerator):
    """Generate mesh by attributing a sphere to each point."""
    
    def generate(
        self,
        points: np.ndarray,
        colors: Optional[np.ndarray] = None,
        normals: Optional[np.ndarray] = None,
        point_size: float = 0.01,
        **kwargs
    ) -> Mesh:
        """
        Generate mesh with spheres at each point.
        
        Args:
            points: (N, 3) point coordinates
            colors: (N, 3) optional RGB colors
            normals: (N, 3) optional normal vectors
            point_size: Radius of each sphere
            **kwargs: Additional parameters
            
        Returns:
            Generated mesh
        """
        try:
            import open3d as o3d
        except ImportError:
            raise ImportError("open3d is required. Install with: pip install open3d")
        
        # Create mesh from points as spheres
        mesh = o3d.geometry.TriangleMesh()
        
        for i, point in enumerate(points):
            sphere = o3d.geometry.TriangleMesh.create_sphere(radius=point_size, resolution=8)
            sphere.translate(point)
            
            if colors is not None:
                color = colors[i] / 255.0
                sphere.paint_uniform_color(color)
            
            mesh += sphere
        
        vertices = np.asarray(mesh.vertices).astype(np.float32)
        faces = np.asarray(mesh.triangles).astype(np.uint32)
        
        mesh_colors = None
        if mesh.has_vertex_colors():
            mesh_colors = (np.asarray(mesh.vertex_colors) * 255).astype(np.uint8)
        
        return Mesh(vertices, faces, mesh_colors, None)
