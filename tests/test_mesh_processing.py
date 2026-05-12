"""Tests for the mesh processing module."""
import os
import tempfile
import unittest

try:
    import open3d as o3d
    HAS_OPEN3D = True
except ImportError:
    HAS_OPEN3D = False

from backend.mesh_processing.processor import (
    fill_holes,
    smooth_mesh,
    set_mesh_color,
    process_mesh,
)


@unittest.skipUnless(HAS_OPEN3D, "open3d not installed")
class TestMeshProcessing(unittest.TestCase):
    """Unit tests for mesh processing functions."""

    def _make_simple_mesh(self):
        """Create a small box mesh for testing."""
        mesh = o3d.geometry.TriangleMesh.create_box(1.0, 1.0, 1.0)
        mesh.compute_vertex_normals()
        return mesh

    def test_smooth_laplacian(self):
        mesh = self._make_simple_mesh()
        verts_before = len(mesh.vertices)
        result = smooth_mesh(mesh, iterations=3, method="laplacian")
        self.assertFalse(result.is_empty())
        # Vertex count unchanged, only positions smoothed
        self.assertEqual(len(result.vertices), verts_before)

    def test_smooth_taubin(self):
        mesh = self._make_simple_mesh()
        result = smooth_mesh(mesh, iterations=3, method="taubin")
        self.assertFalse(result.is_empty())

    def test_set_mesh_color(self):
        mesh = self._make_simple_mesh()
        result = set_mesh_color(mesh, "#ff0000")
        self.assertTrue(result.has_vertex_colors())
        import numpy as np
        colors = np.asarray(result.vertex_colors)
        # All vertices should be red
        self.assertTrue(all(c[0] > 0.99 for c in colors))

    def test_fill_holes_on_closed_mesh(self):
        mesh = self._make_simple_mesh()
        result = fill_holes(mesh)
        # Closed mesh should return without error
        self.assertFalse(result.is_empty())

    def test_process_mesh_pipeline(self):
        mesh = self._make_simple_mesh()
        tmpdir = tempfile.mkdtemp()
        input_path = os.path.join(tmpdir, "test.obj")
        output_path = os.path.join(tmpdir, "test_processed.obj")

        o3d.io.write_triangle_mesh(input_path, mesh)

        try:
            result_path = process_mesh(
                input_path=input_path,
                output_path=output_path,
                fill=True,
                smooth=True,
                smooth_iterations=2,
                color="#00ff00",
            )
            self.assertTrue(os.path.exists(result_path))
            result_mesh = o3d.io.read_triangle_mesh(result_path)
            self.assertFalse(result_mesh.is_empty())
        finally:
            for f in (input_path, output_path):
                if os.path.exists(f):
                    os.remove(f)
            os.rmdir(tmpdir)

    def test_process_mesh_skip_operations(self):
        mesh = self._make_simple_mesh()
        tmpdir = tempfile.mkdtemp()
        input_path = os.path.join(tmpdir, "test.obj")
        output_path = os.path.join(tmpdir, "test_out.obj")

        o3d.io.write_triangle_mesh(input_path, mesh)

        try:
            result_path = process_mesh(
                input_path=input_path,
                output_path=output_path,
                fill=False,
                smooth=False,
                color=None,
            )
            self.assertTrue(os.path.exists(result_path))
        finally:
            for f in (input_path, output_path):
                if os.path.exists(f):
                    os.remove(f)
            os.rmdir(tmpdir)

    def test_process_mesh_bad_input(self):
        with self.assertRaises(ValueError):
            process_mesh("/nonexistent/file.obj")


if __name__ == "__main__":
    unittest.main()
