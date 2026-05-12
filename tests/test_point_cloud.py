"""Tests for point-cloud upload, preview, and mesh-generation endpoints."""
import io
import json
import os
import tempfile
import unittest

import laspy
import numpy as np

from backend.api.app import create_app


def _make_laz_bytes(n=500, with_color=True, bounds=((438000, 438050), (124000, 124050), (300, 320))):
    """Create an in-memory LAZ file with *n* random points and return bytes."""
    # Point format 2 includes RGB; format 0 does not.
    fmt = 2 if with_color else 0
    header = laspy.LasHeader(point_format=fmt, version="1.2")
    las = laspy.LasData(header)

    rng = np.random.default_rng(42)
    las.x = rng.uniform(bounds[0][0], bounds[0][1], n)
    las.y = rng.uniform(bounds[1][0], bounds[1][1], n)
    las.z = rng.uniform(bounds[2][0], bounds[2][1], n)

    if with_color:
        las.red = rng.integers(0, 65535, n, dtype=np.uint16)
        las.green = rng.integers(0, 65535, n, dtype=np.uint16)
        las.blue = rng.integers(0, 65535, n, dtype=np.uint16)

    buf = io.BytesIO()
    las.write(buf)
    buf.seek(0)
    return buf.read()


class _Base(unittest.TestCase):
    """Shared setup: temp dirs, Flask test client, maintainer code."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mesh_dir = os.path.join(self.tmpdir, "meshes")
        self.data_dir = os.path.join(self.tmpdir, "data")
        self.upload_dir = os.path.join(self.tmpdir, "uploads")
        self.frontend_dir = os.path.join(self.tmpdir, "frontend")
        for d in (self.mesh_dir, self.data_dir, self.upload_dir, self.frontend_dir):
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(self.frontend_dir, "index.html"), "w") as f:
            f.write("<html></html>")

        app = create_app({
            "MESH_DIR": self.mesh_dir,
            "DATA_DIR": self.data_dir,
            "UPLOAD_DIR": self.upload_dir,
            "FRONTEND_DIR": self.frontend_dir,
            "TESTING": True,
        })
        self.client = app.test_client()

        with open(os.path.join(self.data_dir, "access_codes.json")) as f:
            codes = json.load(f)["codes"]
        self.maintainer_code = list(codes.keys())[0]
        res = self.client.post(
            "/api/auth/codes",
            headers={"X-Access-Code": self.maintainer_code, "Content-Type": "application/json"},
            data=json.dumps({"location_id": "LOC-1", "role": "user"}),
        )
        self.user_code = res.get_json()["data"]["code"]

    def _auth(self, code=None):
        return {"X-Access-Code": code or self.maintainer_code}

    def _upload_laz(self, filename="test.laz", n=500, with_color=True):
        """Upload a LAZ file via the API and return the response JSON."""
        data = _make_laz_bytes(n=n, with_color=with_color)
        return self.client.post(
            "/api/point-clouds",
            headers=self._auth(),
            content_type="multipart/form-data",
            data={"file": (io.BytesIO(data), filename)},
        )


class TestPointCloudUpload(_Base):
    """Upload and list endpoints."""

    def test_upload_laz(self):
        res = self._upload_laz()
        body = res.get_json()
        self.assertEqual(res.status_code, 201)
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["filename"], "test.laz")
        self.assertGreater(body["data"]["point_count"], 0)

    def test_upload_rejects_non_laz(self):
        res = self.client.post(
            "/api/point-clouds",
            headers=self._auth(),
            content_type="multipart/form-data",
            data={"file": (io.BytesIO(b"not a real file"), "test.txt")},
        )
        self.assertEqual(res.status_code, 400)

    def test_upload_no_file(self):
        res = self.client.post("/api/point-clouds", headers=self._auth())
        self.assertEqual(res.status_code, 400)

    def test_upload_requires_maintainer(self):
        data = _make_laz_bytes(n=10)
        res = self.client.post(
            "/api/point-clouds",
            headers=self._auth(self.user_code),
            content_type="multipart/form-data",
            data={"file": (io.BytesIO(data), "test.laz")},
        )
        self.assertEqual(res.status_code, 403)

    def test_list_point_clouds(self):
        self._upload_laz("a.laz")
        self._upload_laz("b.laz")
        res = self.client.get("/api/point-clouds", headers=self._auth())
        body = res.get_json()
        self.assertTrue(body["success"])
        names = [pc["filename"] for pc in body["data"]]
        self.assertIn("a.laz", names)
        self.assertIn("b.laz", names)


class TestPointCloudPreview(_Base):
    """Preview (downsample) endpoint."""

    def test_preview_returns_positions(self):
        self._upload_laz("preview.laz", n=100, with_color=True)
        res = self.client.get(
            "/api/point-clouds/preview.laz/preview",
            headers=self._auth(),
        )
        body = res.get_json()
        self.assertTrue(body["success"])
        d = body["data"]
        self.assertIn("positions", d)
        self.assertIn("colors", d)
        self.assertGreater(len(d["positions"]), 0)
        # positions length must be a multiple of 3
        self.assertEqual(len(d["positions"]) % 3, 0)
        # colors same length as positions
        self.assertEqual(len(d["colors"]), len(d["positions"]))
        self.assertTrue(d["has_color"])

    def test_preview_without_colors(self):
        self._upload_laz("nocolor.laz", n=100, with_color=False)
        res = self.client.get(
            "/api/point-clouds/nocolor.laz/preview",
            headers=self._auth(),
        )
        body = res.get_json()
        self.assertTrue(body["success"])
        # colors array should be empty
        self.assertEqual(len(body["data"]["colors"]), 0)
        self.assertFalse(body["data"]["has_color"])

    def test_preview_not_found(self):
        res = self.client.get(
            "/api/point-clouds/missing.laz/preview",
            headers=self._auth(),
        )
        self.assertEqual(res.status_code, 404)

    def test_preview_returns_bounds(self):
        self._upload_laz("bounds.laz", n=200)
        res = self.client.get(
            "/api/point-clouds/bounds.laz/preview",
            headers=self._auth(),
        )
        d = res.get_json()["data"]
        self.assertIn("bounds_min", d)
        self.assertIn("bounds_max", d)
        self.assertEqual(len(d["bounds_min"]), 3)
        self.assertEqual(len(d["bounds_max"]), 3)


class TestPointCloudMeshGeneration(_Base):
    """Generate-mesh endpoint."""

    def test_generate_mesh_poisson(self):
        self._upload_laz("gen.laz", n=2000, with_color=True)
        res = self.client.post(
            "/api/point-clouds/gen.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [438000, 124000],
                "bounds_max": [438050, 124050],
                "algorithm": "poisson",
                "location_id": "LOC-GEN",
                "description": "Test mesh from point cloud",
            }),
        )
        body = res.get_json()
        self.assertEqual(res.status_code, 201, body)
        self.assertTrue(body["success"], body)
        self.assertIn("filename", body["data"])
        self.assertTrue(body["data"]["filename"].endswith(".obj"))
        # Mesh file should exist on disk
        mesh_path = os.path.join(self.mesh_dir, body["data"]["filename"])
        self.assertTrue(os.path.exists(mesh_path))

    def test_generate_mesh_bpa(self):
        self._upload_laz("gen_bpa.laz", n=2000, with_color=True)
        res = self.client.post(
            "/api/point-clouds/gen_bpa.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [438000, 124000],
                "bounds_max": [438050, 124050],
                "algorithm": "bpa",
            }),
        )
        body = res.get_json()
        self.assertEqual(res.status_code, 201, body)
        self.assertTrue(body["success"], body)

    def test_generate_mesh_missing_bounds(self):
        self._upload_laz("nb.laz", n=100)
        res = self.client.post(
            "/api/point-clouds/nb.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"algorithm": "poisson"}),
        )
        self.assertEqual(res.status_code, 400)

    def test_generate_mesh_bad_algorithm(self):
        self._upload_laz("ba.laz", n=100)
        res = self.client.post(
            "/api/point-clouds/ba.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [438000, 124000],
                "bounds_max": [438050, 124050],
                "algorithm": "invalid",
            }),
        )
        self.assertEqual(res.status_code, 400)

    def test_generate_mesh_not_found(self):
        res = self.client.post(
            "/api/point-clouds/nothere.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [0, 0],
                "bounds_max": [100, 100],
            }),
        )
        self.assertEqual(res.status_code, 404)

    def test_generate_mesh_auto_registers(self):
        """The generated mesh should appear in the mesh list."""
        self._upload_laz("reg.laz", n=2000, with_color=True)
        gen = self.client.post(
            "/api/point-clouds/reg.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [438000, 124000],
                "bounds_max": [438050, 124050],
                "algorithm": "poisson",
                "location_id": "LOC-REG",
                "description": "Auto-registered mesh",
            }),
        )
        self.assertEqual(gen.status_code, 201)
        body = gen.get_json()
        self.assertTrue(body["data"].get("registered"))

        meshes = self.client.get("/api/meshes", headers=self._auth())
        names = [m["filename"] for m in meshes.get_json()["data"]]
        self.assertIn(body["data"]["filename"], names)

    def test_generate_mesh_with_color_source(self):
        """Supply a separate GKOT file as colour source."""
        self._upload_laz("terrain.laz", n=2000, with_color=False)
        self._upload_laz("GKOT_test.laz", n=2000, with_color=True)
        res = self.client.post(
            "/api/point-clouds/terrain.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [438000, 124000],
                "bounds_max": [438050, 124050],
                "algorithm": "poisson",
                "color_source": "GKOT_test.laz",
            }),
        )
        body = res.get_json()
        self.assertEqual(res.status_code, 201, body)
        self.assertTrue(body["success"], body)


class TestPointCloudActivityLog(_Base):
    """Verify point-cloud actions appear in the activity log."""

    def test_upload_logged(self):
        self._upload_laz("logged.laz")
        log = self.client.get("/api/activity-log", headers=self._auth())
        actions = [e["action"] for e in log.get_json()["data"]]
        self.assertIn("pointcloud_upload", actions)

    def test_generate_logged(self):
        self._upload_laz("glog.laz", n=2000)
        self.client.post(
            "/api/point-clouds/glog.laz/generate-mesh",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({
                "bounds_min": [438000, 124000],
                "bounds_max": [438050, 124050],
            }),
        )
        log = self.client.get("/api/activity-log", headers=self._auth())
        actions = [e["action"] for e in log.get_json()["data"]]
        self.assertIn("mesh_generate", actions)


class TestMapStyleExtractionWorkflow(_Base):
    """Workflow tests: define coordinates, extract points, then generate mesh."""

    def test_upload_define_coordinates_extract_and_generate(self):
        laz_bytes = _make_laz_bytes(n=2500, with_color=True)

        upload = self.client.post(
            "/api/upload-point-cloud",
            content_type="multipart/form-data",
            data={"file": (io.BytesIO(laz_bytes), "workflow.laz")},
        )
        self.assertEqual(upload.status_code, 200)
        up = upload.get_json()
        self.assertTrue(up["success"])
        path = up["data"]["filepath"]

        # Define a polygon in the same CRS as generated test data.
        polygon = [
            [438005, 124005],
            [438045, 124005],
            [438045, 124045],
            [438005, 124045],
        ]

        extract = self.client.post(
            "/api/extract-region",
            data=json.dumps({"point_cloud_path": path, "polygon": polygon}),
            content_type="application/json",
        )
        self.assertEqual(extract.status_code, 200)
        ex = extract.get_json()
        self.assertTrue(ex["success"], ex)
        self.assertGreater(ex["data"]["point_count"], 0)

        output_path = os.path.join(self.tmpdir, "out", "workflow_mesh.obj")
        generate = self.client.post(
            "/api/generate-mesh",
            data=json.dumps({
                "point_cloud_path": path,
                "polygon": polygon,
                "output_path": output_path,
                "algorithm": "poisson",
                "generator_params": {"depth": 8},
            }),
            content_type="application/json",
        )
        self.assertEqual(generate.status_code, 200)
        gen = generate.get_json()
        self.assertTrue(gen["success"], gen)
        self.assertTrue(os.path.exists(output_path))

    def test_extract_returns_clear_reason_when_area_has_no_points(self):
        laz_bytes = _make_laz_bytes(n=500, with_color=True)
        upload = self.client.post(
            "/api/upload-point-cloud",
            content_type="multipart/form-data",
            data={"file": (io.BytesIO(laz_bytes), "empty-check.laz")},
        )
        path = upload.get_json()["data"]["filepath"]

        # Deliberately outside synthetic cloud extent.
        polygon = [
            [900000, 900000],
            [900010, 900000],
            [900010, 900010],
            [900000, 900010],
        ]

        extract = self.client.post(
            "/api/extract-region",
            data=json.dumps({"point_cloud_path": path, "polygon": polygon}),
            content_type="application/json",
        )
        ex = extract.get_json()
        self.assertFalse(ex["success"])
        self.assertIn("reason", ex["data"])
        self.assertIn("hint", ex["data"])
        self.assertEqual(ex["data"]["point_count"], 0)


if __name__ == "__main__":
    unittest.main()
