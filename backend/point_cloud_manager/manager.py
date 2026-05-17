"""Point cloud management: upload, preview (downsample for web), area extraction, mesh generation.

All coordinate handling uses EPSG:3794 (metres).  Colours are preserved
through every stage of the pipeline when available in the source data.
"""
import json
import math
import os
import uuid
from typing import Optional

import laspy
import numpy as np

import open3d as o3d



class PointCloudManager:
    """Stateless helper — operates on files in *upload_dir* and *mesh_dir*."""

    def __init__(self, upload_dir: str, mesh_dir: str):
        self.upload_dir = upload_dir
        self.mesh_dir = mesh_dir
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(mesh_dir, exist_ok=True)

    # ── helpers ────────────────────────────────────────────────────

    def _laz_path(self, filename: str) -> str:
        return os.path.join(self.upload_dir, filename)

    # ── upload ─────────────────────────────────────────────────────

    def save_upload(self, file_storage) -> dict:
        """Persist a Werkzeug ``FileStorage`` and return summary metadata."""
        from werkzeug.utils import secure_filename as _sec
        name = _sec(file_storage.filename)
        dest = self._laz_path(name)
        file_storage.save(dest)
        return self.inspect(name)

    # ── inspect ────────────────────────────────────────────────────

    def inspect(self, filename: str) -> dict:
        """Return quick metadata for a stored point cloud file."""
        path = self._laz_path(filename)
        with laspy.open(path) as fh:
            header = fh.header
            point_count = header.point_count
            mins = [float(header.min[i]) for i in range(3)]
            maxs = [float(header.max[i]) for i in range(3)]
            has_color = any(
                d.name.lower() in ("red", "r") for d in header.point_format.dimensions
            )
        return {
            "filename": filename,
            "point_count": point_count,
            "bounds_min": mins,
            "bounds_max": maxs,
            "has_color": has_color,
            "size_bytes": os.path.getsize(path),
        }

    # ── list uploads ───────────────────────────────────────────────

    def list_uploads(self) -> list:
        """Return metadata dicts for every .laz/.las file in upload_dir."""
        results = []
        for fname in sorted(os.listdir(self.upload_dir)):
            if fname.lower().endswith((".laz", ".las")):
                try:
                    results.append(self.inspect(fname))
                except Exception:
                    pass
        return results

    # ── preview (downsampled for web) ──────────────────────────────

    def preview(self, filename: str, max_points: int = 200_000) -> dict:
        """Return a JSON-serialisable dict of downsampled positions + colours.

        The result is centred at ``(0, 0, 0)`` so the viewer doesn't need
        to deal with large coordinate offsets.  The ``center`` field holds
        the real-world origin (EPSG:3794) so it can be restored later.
        """
        path = self._laz_path(filename)
        with laspy.open(path) as fh:
            las = fh.read()

        pts = np.vstack((las.x, las.y, las.z)).T  # (N, 3)

        # Colours — normalise 16-bit to [0, 1]
        has_color = hasattr(las, "red")
        colors = None
        if has_color:
            colors = np.vstack((las.red, las.green, las.blue)).T / 65535.0

        # Downsample if necessary
        if len(pts) > max_points:
            step = max(1, len(pts) // max_points)
            pts = pts[::step]
            if colors is not None:
                colors = colors[::step]

        center = np.mean(pts, axis=0)
        pts_centered = pts - center
        bounds_min = pts.min(axis=0)
        bounds_max = pts.max(axis=0)

        result = {
            "center": [float(v) for v in center],
            "bounds_min": [float(v) for v in bounds_min],
            "bounds_max": [float(v) for v in bounds_max],
            "count": len(pts_centered),
            "has_color": has_color,
            # Flat float arrays → compact JSON transfer
            "positions": pts_centered.flatten().tolist(),
            "colors": colors.flatten().tolist() if colors is not None else [],
        }

        return result

    # ── mesh generation from selected area ─────────────────────────

    def generate_mesh(
        self,
        filename: str,
        bounds_min_2d: list,
        bounds_max_2d: list,
        algorithm: str = "poisson",
        color_source: Optional[str] = None,
    ) -> dict:
        """Extract points inside a 2-D rectangle and generate a mesh.

        Parameters
        ----------
        filename : str
            The point cloud file in *upload_dir*.
        bounds_min_2d : [x_min, y_min]
            South-west corner of the selection rectangle (EPSG:3794).
        bounds_max_2d : [x_max, y_max]
            North-east corner.
        algorithm : str
            ``"poisson"`` or ``"bpa"`` (ball-pivoting).
        color_source : Optional[str]
            Optional second .laz file in *upload_dir* to use as colour
            source (e.g. a GKOT file).  If ``None``, uses the main file's
            colours when available.

        Returns
        -------
        dict with ``mesh_filename``, ``meta_filename``, and full metadata.
        """

        path = self._laz_path(filename)
        with laspy.open(path) as fh:
            las = fh.read()

        pts = np.vstack((las.x, las.y, las.z)).T
        has_color = hasattr(las, "red")

        # 2D bounding-box filter
        xmin, ymin = float(bounds_min_2d[0]), float(bounds_min_2d[1])
        xmax, ymax = float(bounds_max_2d[0]), float(bounds_max_2d[1])
        mask = (
            (pts[:, 0] >= xmin) & (pts[:, 0] <= xmax)
            & (pts[:, 1] >= ymin) & (pts[:, 1] <= ymax)
        )
        pts = pts[mask]
        if len(pts) == 0:
            raise ValueError("No points found inside the selected area")

        colors = None
        if has_color:
            all_colors = np.vstack((las.red, las.green, las.blue)).T / 65535.0
            colors = all_colors[mask]

        # Optional colour source (e.g. GKOT)
        if color_source:
            cs_path = self._laz_path(color_source)
            if os.path.exists(cs_path):
                colors = self._transfer_colors(pts, cs_path)

        # Centre at 0,0,0
        center = np.mean(pts, axis=0)
        pts_c = pts - center

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts_c)
        if colors is not None:
            pcd.colors = o3d.utility.Vector3dVector(colors)

        # Prepare
        pcd = pcd.voxel_down_sample(voxel_size=0.1)
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=2.0, max_nn=30)
        )
        pcd.orient_normals_consistent_tangent_plane(k=15)

        has_pcd_colors = pcd.has_colors()

        if algorithm == "bpa":
            dists = pcd.compute_nearest_neighbor_distance()
            avg = np.mean(dists)
            radii = [avg, avg * 2, avg * 4]
            mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
                pcd, o3d.utility.DoubleVector(radii)
            )
        else:
            mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                pcd, depth=9
            )
            to_remove = densities < np.quantile(densities, 0.1)
            mesh.remove_vertices_by_mask(to_remove)

        mesh.compute_vertex_normals()

        # Transfer vertex colours from point cloud → mesh
        if has_pcd_colors:
            pcd_kd = o3d.geometry.KDTreeFlann(pcd)
            mesh_verts = np.asarray(mesh.vertices)
            pcd_cols = np.asarray(pcd.colors)
            vc = np.zeros_like(mesh_verts)
            for i, v in enumerate(mesh_verts):
                _, idx, _ = pcd_kd.search_knn_vector_3d(v, 1)
                vc[i] = pcd_cols[idx[0]]
            mesh.vertex_colors = o3d.utility.Vector3dVector(vc)

        # Save
        mesh_id = str(uuid.uuid4())[:8]
        base = os.path.splitext(filename)[0]
        mesh_name = f"{base}_{algorithm}_{mesh_id}.obj"
        meta_name = f"{base}_{algorithm}_{mesh_id}.meta.json"
        mesh_path = os.path.join(self.mesh_dir, mesh_name)
        meta_path = os.path.join(self.mesh_dir, meta_name)

        o3d.io.write_triangle_mesh(mesh_path, mesh)

        bounds_min_full = pts.min(axis=0)
        bounds_max_full = pts.max(axis=0)
        metadata = {
            "source_file": filename,
            "crs": "EPSG:3794",
            "unit": "meters",
            "center_x": float(center[0]),
            "center_y": float(center[1]),
            "center_z": float(center[2]),
            "bounds_min": [float(v) for v in bounds_min_full],
            "bounds_max": [float(v) for v in bounds_max_full],
            "num_points": len(pts),
            "algorithm": algorithm,
            "filename": mesh_name,
            "has_vertex_colors": has_pcd_colors,
        }
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return {
            "mesh_filename": mesh_name,
            "meta_filename": meta_name,
            "metadata": metadata,
            "mesh_path": mesh_path,
        }

    # ── colour transfer ────────────────────────────────────────────

    def _transfer_colors(self, target_pts: np.ndarray, color_source_path: str) -> np.ndarray:
        """KDTree nearest-neighbour colour transfer from a colour source file."""

        with laspy.open(color_source_path) as fh:
            clas = fh.read()

        cpts = np.vstack((clas.x, clas.y, clas.z)).T
        if not hasattr(clas, "red"):
            return None

        ccols = np.vstack((clas.red, clas.green, clas.blue)).T / 65535.0
        cpcd = o3d.geometry.PointCloud()
        cpcd.points = o3d.utility.Vector3dVector(cpts)
        cpcd.colors = o3d.utility.Vector3dVector(ccols)
        kd = o3d.geometry.KDTreeFlann(cpcd)

        transferred = np.zeros((len(target_pts), 3))
        for i, pt in enumerate(target_pts):
            _, idx, _ = kd.search_knn_vector_3d(pt, 1)
            transferred[i] = ccols[idx[0]]
        return transferred
