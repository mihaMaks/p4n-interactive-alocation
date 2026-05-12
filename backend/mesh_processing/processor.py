"""Mesh processing utilities: hole filling, smoothing, and colour handling.

Uses Open3D for geometry operations.  All functions accept and return
Open3D TriangleMesh objects so callers can chain operations.
"""
import os
import tempfile
from typing import Optional

import numpy as np

try:
    import open3d as o3d
except ImportError:  # pragma: no cover
    o3d = None


def _require_open3d():
    if o3d is None:
        raise RuntimeError("open3d is required for mesh processing")


# ------------------------------------------------------------------
# Hole filling
# ------------------------------------------------------------------

def fill_holes(mesh, hole_size: float = 100.0):
    """Fill holes up to *hole_size* in a triangle mesh.

    Strategy: detect boundary edges, make the mesh watertight by
    filling small holes via ball-pivoting on boundary vertices, then
    merge back into the original mesh.
    """
    _require_open3d()
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()

    # Compute normals so Poisson can work
    mesh.compute_vertex_normals()

    # Use Poisson reconstruction on boundary points to fill holes
    # Extract boundary
    edges = mesh.get_non_manifold_edges(allow_boundary_edges=True)
    if len(edges) == 0:
        return mesh  # already watertight

    # Simple approach: fill all small holes by attempting to reconstruct
    # a watertight surface via Poisson and combining
    try:
        pcd = o3d.geometry.PointCloud()
        vertices = np.asarray(mesh.vertices)
        pcd.points = o3d.utility.Vector3dVector(vertices)
        if mesh.has_vertex_normals():
            pcd.normals = mesh.vertex_normals
        else:
            pcd.estimate_normals()

        filled, _ = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=8
        )
        # Crop filled mesh to original bounding box + margin
        bbox = mesh.get_axis_aligned_bounding_box()
        margin = np.array([hole_size, hole_size, hole_size])
        bbox_min = np.asarray(bbox.min_bound) - margin
        bbox_max = np.asarray(bbox.max_bound) + margin
        crop_box = o3d.geometry.AxisAlignedBoundingBox(bbox_min, bbox_max)
        filled = filled.crop(crop_box)

        # Transfer colours if present
        if mesh.has_vertex_colors():
            _transfer_colors(mesh, filled)

        return filled
    except Exception:
        # Fall back to original if Poisson fails
        return mesh


# ------------------------------------------------------------------
# Smoothing
# ------------------------------------------------------------------

def smooth_mesh(mesh, iterations: int = 5, method: str = "laplacian"):
    """Smooth a mesh using Laplacian or Taubin filtering."""
    _require_open3d()
    if method == "taubin":
        return mesh.filter_smooth_taubin(
            number_of_iterations=iterations
        )
    # default: Laplacian
    return mesh.filter_smooth_laplacian(
        number_of_iterations=iterations
    )


# ------------------------------------------------------------------
# Colour helpers
# ------------------------------------------------------------------

def set_mesh_color(mesh, hex_color: str):
    """Paint every vertex with the given hex colour."""
    _require_open3d()
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255
    mesh.paint_uniform_color([r, g, b])
    return mesh


def _transfer_colors(source, target):
    """Copy per-vertex colours from *source* to *target* using nearest vertex."""
    src_pts = np.asarray(source.vertices)
    src_cols = np.asarray(source.vertex_colors)
    tgt_pts = np.asarray(target.vertices)

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(src_pts)
    tree = o3d.geometry.KDTreeFlann(pcd)

    colors = np.zeros_like(tgt_pts)
    for i, pt in enumerate(tgt_pts):
        _, idx, _ = tree.search_knn_vector_3d(pt, 1)
        colors[i] = src_cols[idx[0]]
    target.vertex_colors = o3d.utility.Vector3dVector(colors)


# ------------------------------------------------------------------
# High-level pipeline
# ------------------------------------------------------------------

def process_mesh(
    input_path: str,
    output_path: Optional[str] = None,
    fill: bool = True,
    smooth: bool = True,
    smooth_iterations: int = 5,
    smooth_method: str = "laplacian",
    color: Optional[str] = None,
    hole_size: float = 100.0,
) -> str:
    """Read a mesh file, process it, write the result, and return the path."""
    _require_open3d()

    mesh = o3d.io.read_triangle_mesh(input_path)
    if mesh.is_empty():
        raise ValueError(f"Failed to read mesh from {input_path}")

    mesh.compute_vertex_normals()

    if fill:
        mesh = fill_holes(mesh, hole_size=hole_size)

    if smooth:
        mesh = smooth_mesh(mesh, iterations=smooth_iterations, method=smooth_method)

    if color:
        set_mesh_color(mesh, color)

    mesh.compute_vertex_normals()

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_processed{ext}"

    o3d.io.write_triangle_mesh(output_path, mesh, write_vertex_colors=True)
    return output_path
