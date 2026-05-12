"""Integration tests for the Flask API — placements, processing, colour."""
import io
import json
import os
import tempfile
import unittest

from backend.api.app import create_app


class _BaseAPITest(unittest.TestCase):
    """Common setup: temp dirs, Flask test client, maintainer code."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mesh_dir = os.path.join(self.tmpdir, "meshes")
        self.data_dir = os.path.join(self.tmpdir, "data")
        self.upload_dir = os.path.join(self.tmpdir, "uploads")
        self.frontend_dir = os.path.join(self.tmpdir, "frontend")
        for d in (self.mesh_dir, self.data_dir, self.upload_dir, self.frontend_dir):
            os.makedirs(d, exist_ok=True)
        # Write a minimal index.html so the frontend route doesn't 404
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

        # Read the auto-generated maintainer code
        with open(os.path.join(self.data_dir, "access_codes.json")) as f:
            codes = json.load(f)["codes"]
        self.maintainer_code = list(codes.keys())[0]

        # Create a user code
        res = self.client.post(
            "/api/auth/codes",
            headers={"X-Access-Code": self.maintainer_code, "Content-Type": "application/json"},
            data=json.dumps({"location_id": "LOC-1", "role": "user"}),
        )
        self.user_code = res.get_json()["data"]["code"]

    def _auth(self, code=None):
        return {"X-Access-Code": code or self.maintainer_code}

    def _upload_mesh(self, filename="test.obj", location_id="LOC-1"):
        """Helper to upload a dummy OBJ mesh."""
        obj_content = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
        return self.client.post(
            "/api/meshes",
            headers=self._auth(),
            data={
                "file": (io.BytesIO(obj_content), filename),
                "location_id": location_id,
                "description": "Test mesh",
            },
            content_type="multipart/form-data",
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)


class TestPlacementAPI(_BaseAPITest):
    """Tests for placement endpoints."""

    def test_list_placements_empty(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.get(
            f"/api/meshes/{mesh_id}/placements",
            headers=self._auth(self.user_code),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["data"], [])

    def test_commit_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                "x": 5, "y": 1, "z": 10,
                "rotation_y": 0,
                "length": 4.8, "width": 1.8, "height": 1.5,
                "color": "#2ecc71",
            }),
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.get_json()["success"])

    def test_commit_placement_missing_field(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                # Missing x, y, z, etc.
            }),
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Missing", res.get_json()["error"])

    def test_commit_overlap_rejected(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        placement = {
            "vehicle_id": "sedan",
            "x": 0, "y": 1, "z": 0,
            "rotation_y": 0,
            "length": 4, "width": 2, "height": 1.5,
            "color": "#3498db",
        }

        # First placement succeeds
        res1 = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps(placement),
        )
        self.assertEqual(res1.status_code, 201)

        # Same spot — rejected with 409
        res2 = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps(placement),
        )
        self.assertEqual(res2.status_code, 409)
        self.assertIn("Overlaps", res2.get_json()["error"])

    def test_adjacent_placements_succeed(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        base = {
            "vehicle_id": "sedan", "y": 1, "rotation_y": 0,
            "length": 4, "width": 2, "height": 1.5, "color": "#3498db",
        }

        res1 = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({**base, "x": 0, "z": 0}),
        )
        self.assertEqual(res1.status_code, 201)

        res2 = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({**base, "x": 10, "z": 0}),
        )
        self.assertEqual(res2.status_code, 201)

    def test_delete_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                "x": 0, "y": 1, "z": 0,
                "rotation_y": 0,
                "length": 4, "width": 2, "height": 1.5,
            }),
        )
        pid = res.get_json()["data"]["id"]

        res = self.client.delete(
            f"/api/placements/{pid}",
            headers=self._auth(self.user_code),
        )
        self.assertEqual(res.status_code, 200)

    def test_placement_visible_to_other_users(self):
        """Placements made by one user appear in listings for another."""
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        # Create second user code
        res = self.client.post(
            "/api/auth/codes",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"location_id": "LOC-1", "role": "user"}),
        )
        user2_code = res.get_json()["data"]["code"]

        # User 1 places a vehicle
        self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                "x": 0, "y": 1, "z": 0,
                "rotation_y": 0,
                "length": 4, "width": 2, "height": 1.5,
            }),
        )

        # User 2 sees it
        res = self.client.get(
            f"/api/meshes/{mesh_id}/placements",
            headers=self._auth(user2_code),
        )
        self.assertEqual(len(res.get_json()["data"]), 1)

    def test_unauthenticated_rejected(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.get(f"/api/meshes/{mesh_id}/placements")
        self.assertEqual(res.status_code, 401)

    def test_mesh_uploaded_visible_to_user(self):
        """Meshes uploaded by maintainer are visible to users."""
        res = self._upload_mesh(location_id="LOC-1")
        self.assertEqual(res.status_code, 200)

        res = self.client.get(
            "/api/meshes",
            headers=self._auth(self.user_code),
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.get_json()["data"]) >= 1)

    def test_wildcard_user_sees_all_meshes(self):
        """A user with location_id='*' sees meshes from any location."""
        # Create a wildcard user
        res = self.client.post(
            "/api/auth/codes",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"location_id": "*", "role": "user"}),
        )
        wildcard_code = res.get_json()["data"]["code"]

        # Upload meshes to different locations
        self._upload_mesh(filename="a.obj", location_id="PARK-A")
        self._upload_mesh(filename="b.obj", location_id="PARK-B")
        self._upload_mesh(filename="c.obj", location_id="default")

        res = self.client.get(
            "/api/meshes",
            headers=self._auth(wildcard_code),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["data"]), 3)

    def test_scoped_user_only_sees_own_location(self):
        """A user scoped to LOC-1 only sees LOC-1 and default meshes."""
        self._upload_mesh(filename="a.obj", location_id="LOC-1")
        self._upload_mesh(filename="b.obj", location_id="LOC-OTHER")
        self._upload_mesh(filename="c.obj", location_id="default")

        res = self.client.get(
            "/api/meshes",
            headers=self._auth(self.user_code),
        )
        data = res.get_json()["data"]
        locations = {m["location_id"] for m in data}
        self.assertEqual(len(data), 2)
        self.assertIn("LOC-1", locations)
        self.assertIn("default", locations)
        self.assertNotIn("LOC-OTHER", locations)

    def test_user_can_place_vehicle_and_see_it(self):
        """Full flow: user places vehicle, then fetches placements."""
        res = self._upload_mesh(location_id="LOC-1")
        mesh_id = res.get_json()["data"]["id"]

        placement = {
            "vehicle_id": "sedan",
            "x": 5, "y": 1, "z": 10,
            "rotation_y": 0.5,
            "length": 4.8, "width": 1.8, "height": 1.5,
            "color": "#2ecc71",
        }
        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps(placement),
        )
        self.assertEqual(res.status_code, 201)
        pid = res.get_json()["data"]["id"]

        # Same user can see it
        res = self.client.get(
            f"/api/meshes/{mesh_id}/placements",
            headers=self._auth(self.user_code),
        )
        placements = res.get_json()["data"]
        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0]["id"], pid)
        self.assertAlmostEqual(placements[0]["x"], 5)
        self.assertAlmostEqual(placements[0]["rotation_y"], 0.5)

    def test_two_users_cannot_overlap(self):
        """Two different users trying the same spot — second gets 409."""
        res = self._upload_mesh(location_id="LOC-1")
        mesh_id = res.get_json()["data"]["id"]

        # Create second user
        res = self.client.post(
            "/api/auth/codes",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"location_id": "LOC-1", "role": "user"}),
        )
        user2_code = res.get_json()["data"]["code"]

        spot = {
            "vehicle_id": "sedan",
            "x": 0, "y": 1, "z": 0,
            "rotation_y": 0,
            "length": 4, "width": 2, "height": 1.5,
        }

        # User 1 places successfully
        res1 = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps(spot),
        )
        self.assertEqual(res1.status_code, 201)

        # User 2 tries same spot — overlap rejected
        res2 = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(user2_code), "Content-Type": "application/json"},
            data=json.dumps(spot),
        )
        self.assertEqual(res2.status_code, 409)
        self.assertIn("Overlaps", res2.get_json()["error"])

    def test_overlap_after_delete_allows_reuse(self):
        """After deleting a placement, the same spot can be reused."""
        res = self._upload_mesh(location_id="LOC-1")
        mesh_id = res.get_json()["data"]["id"]

        spot = {
            "vehicle_id": "sedan",
            "x": 0, "y": 1, "z": 0,
            "rotation_y": 0,
            "length": 4, "width": 2, "height": 1.5,
        }

        # Place
        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps(spot),
        )
        pid = res.get_json()["data"]["id"]

        # Delete
        res = self.client.delete(
            f"/api/placements/{pid}",
            headers=self._auth(self.user_code),
        )
        self.assertEqual(res.status_code, 200)

        # Same spot succeeds again
        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps(spot),
        )
        self.assertEqual(res.status_code, 201)


class TestMeshColorAPI(_BaseAPITest):
    """Tests for mesh colour endpoint."""

    def test_set_color(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.put(
            f"/api/meshes/{mesh_id}/color",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"color": "#ff0000"}),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["data"]["color"], "#ff0000")

    def test_set_invalid_color(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.put(
            f"/api/meshes/{mesh_id}/color",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"color": "red"}),
        )
        self.assertEqual(res.status_code, 400)

    def test_color_persists(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        self.client.put(
            f"/api/meshes/{mesh_id}/color",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"color": "#00ff00"}),
        )

        res = self.client.get(
            f"/api/meshes/{mesh_id}/metadata",
            headers=self._auth(self.user_code),
        )
        self.assertEqual(res.get_json()["data"]["color"], "#00ff00")


class TestMeshProcessAPI(_BaseAPITest):
    """Tests for mesh processing endpoint (requires Open3D)."""

    def test_process_requires_maintainer(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/process",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({}),
        )
        self.assertEqual(res.status_code, 403)

    def test_process_nonexistent_mesh(self):
        res = self.client.post(
            "/api/meshes/fake-id/process",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({}),
        )
        self.assertEqual(res.status_code, 404)

    def test_process_invalid_method(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/process",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"smooth_method": "invalid"}),
        )
        self.assertEqual(res.status_code, 400)

    def test_process_invalid_color(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/process",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"color": "not-a-color"}),
        )
        self.assertEqual(res.status_code, 400)


class TestPlacementUpdateAPI(_BaseAPITest):
    """Tests for the PUT /api/placements/<id> endpoint."""

    def _create_placement(self, mesh_id, x=5, z=10, code=None):
        return self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(code or self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                "x": x, "y": 1, "z": z,
                "rotation_y": 0,
                "length": 4.8, "width": 1.8, "height": 1.5,
                "color": "#2ecc71",
            }),
        )

    def test_update_position(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        res = self._create_placement(mesh_id, x=5, z=10)
        pid = res.get_json()["data"]["id"]

        res = self.client.put(
            f"/api/placements/{pid}",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"x": 20, "z": 30}),
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])
        self.assertAlmostEqual(res.get_json()["data"]["x"], 20)

    def test_update_departure_date(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        res = self._create_placement(mesh_id)
        pid = res.get_json()["data"]["id"]

        res = self.client.put(
            f"/api/placements/{pid}",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"departure_date": "2025-12-31"}),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["data"]["departure_date"], "2025-12-31")

    def test_update_overlap_rejected(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        self._create_placement(mesh_id, x=0, z=0)
        res2 = self._create_placement(mesh_id, x=20, z=0)
        pid2 = res2.get_json()["data"]["id"]

        res = self.client.put(
            f"/api/placements/{pid2}",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"x": 0, "z": 0}),
        )
        self.assertEqual(res.status_code, 409)

    def test_update_nonexistent(self):
        res = self.client.put(
            "/api/placements/no-such-id",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({"x": 10}),
        )
        self.assertEqual(res.status_code, 404)

    def test_commit_with_departure_date(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]

        res = self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                "x": 5, "y": 1, "z": 10,
                "rotation_y": 0,
                "length": 4.8, "width": 1.8, "height": 1.5,
                "color": "#2ecc71",
                "departure_date": "2025-08-15",
            }),
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["data"]["departure_date"], "2025-08-15")


class TestPlacementOwnership(_BaseAPITest):
    """Users can only modify/delete their own placements."""

    def _make_user(self, desc=""):
        res = self.client.post(
            "/api/auth/codes",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"location_id": "LOC-1", "role": "user", "description": desc}),
        )
        return res.get_json()["data"]["code"]

    def _place(self, mesh_id, code, x=5):
        return self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan", "x": x, "y": 1, "z": 10,
                "rotation_y": 0, "length": 4.8, "width": 1.8, "height": 1.5,
            }),
        )

    def test_user_can_delete_own_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        code = self._make_user("alice")
        pid = self._place(mesh_id, code).get_json()["data"]["id"]
        res = self.client.delete(f"/api/placements/{pid}", headers=self._auth(code))
        self.assertEqual(res.status_code, 200)

    def test_user_cannot_delete_others_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        alice = self._make_user("alice")
        bob = self._make_user("bob")
        pid = self._place(mesh_id, alice).get_json()["data"]["id"]
        res = self.client.delete(f"/api/placements/{pid}", headers=self._auth(bob))
        self.assertEqual(res.status_code, 403)

    def test_maintainer_can_delete_any_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        alice = self._make_user("alice")
        pid = self._place(mesh_id, alice).get_json()["data"]["id"]
        res = self.client.delete(f"/api/placements/{pid}", headers=self._auth())
        self.assertEqual(res.status_code, 200)

    def test_user_can_update_own_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        code = self._make_user("alice")
        pid = self._place(mesh_id, code).get_json()["data"]["id"]
        res = self.client.put(
            f"/api/placements/{pid}",
            headers={**self._auth(code), "Content-Type": "application/json"},
            data=json.dumps({"x": 20}),
        )
        self.assertEqual(res.status_code, 200)

    def test_user_cannot_update_others_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        alice = self._make_user("alice")
        bob = self._make_user("bob")
        pid = self._place(mesh_id, alice).get_json()["data"]["id"]
        res = self.client.put(
            f"/api/placements/{pid}",
            headers={**self._auth(bob), "Content-Type": "application/json"},
            data=json.dumps({"x": 20}),
        )
        self.assertEqual(res.status_code, 403)

    def test_maintainer_can_update_any_placement(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        alice = self._make_user("alice")
        pid = self._place(mesh_id, alice).get_json()["data"]["id"]
        res = self.client.put(
            f"/api/placements/{pid}",
            headers={**self._auth(), "Content-Type": "application/json"},
            data=json.dumps({"departure_date": "2026-01-01"}),
        )
        self.assertEqual(res.status_code, 200)

    def test_placement_persists_after_unauthorized_delete(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        alice = self._make_user("alice")
        bob = self._make_user("bob")
        pid = self._place(mesh_id, alice).get_json()["data"]["id"]
        self.client.delete(f"/api/placements/{pid}", headers=self._auth(bob))
        # Placement should still exist
        res = self.client.get(f"/api/meshes/{mesh_id}/placements", headers=self._auth(alice))
        pids = [p["id"] for p in res.get_json()["data"]]
        self.assertIn(pid, pids)


class TestActivityLogAPI(_BaseAPITest):
    """Tests for the activity log endpoint."""

    def test_activity_log_records_upload(self):
        self._upload_mesh()
        res = self.client.get("/api/activity-log", headers=self._auth())
        self.assertEqual(res.status_code, 200)
        entries = res.get_json()["data"]
        actions = [e["action"] for e in entries]
        self.assertIn("mesh_upload", actions)

    def test_activity_log_requires_maintainer(self):
        res = self.client.get("/api/activity-log", headers=self._auth(self.user_code))
        self.assertEqual(res.status_code, 403)

    def test_activity_log_filter(self):
        self._upload_mesh()
        res = self.client.get("/api/activity-log?action=mesh_upload", headers=self._auth())
        entries = res.get_json()["data"]
        self.assertTrue(all(e["action"] == "mesh_upload" for e in entries))

    def test_activity_log_records_placement_commit(self):
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        self.client.post(
            f"/api/meshes/{mesh_id}/placements",
            headers={**self._auth(self.user_code), "Content-Type": "application/json"},
            data=json.dumps({
                "vehicle_id": "sedan",
                "x": 5, "y": 1, "z": 10,
                "rotation_y": 0,
                "length": 4.8, "width": 1.8, "height": 1.5,
                "color": "#2ecc71",
            }),
        )
        res = self.client.get("/api/activity-log", headers=self._auth())
        actions = [e["action"] for e in res.get_json()["data"]]
        self.assertIn("placement_commit", actions)


class TestMeshDeleteRemoved(_BaseAPITest):
    """Verify the DELETE /api/meshes/<id> endpoint has been removed."""

    def test_delete_mesh_returns_405(self):
        """DELETE method on meshes endpoint should not be allowed."""
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        res = self.client.delete(
            f"/api/meshes/{mesh_id}",
            headers=self._auth(),
        )
        self.assertEqual(res.status_code, 405)

    def test_mesh_still_exists_after_delete_attempt(self):
        """Mesh data must persist even if someone tries DELETE."""
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        self.client.delete(f"/api/meshes/{mesh_id}", headers=self._auth())
        # Mesh should still be accessible
        res = self.client.get(f"/api/meshes/{mesh_id}", headers=self._auth())
        self.assertEqual(res.status_code, 200)

    def test_mesh_list_unaffected_by_delete_attempt(self):
        """Mesh count should not decrease after a DELETE attempt."""
        self._upload_mesh("a.obj")
        self._upload_mesh("b.obj")
        res = self.client.get("/api/meshes", headers=self._auth())
        before = len(res.get_json()["data"])
        mesh_id = res.get_json()["data"][0]["id"]
        self.client.delete(f"/api/meshes/{mesh_id}", headers=self._auth())
        res = self.client.get("/api/meshes", headers=self._auth())
        after = len(res.get_json()["data"])
        self.assertEqual(before, after)


class TestViewerToggleAPIs(_BaseAPITest):
    """Verify the GET endpoints used by viewer toggles work correctly."""

    def test_mesh_obj_retrievable_for_viewer(self):
        """GET /api/meshes/<id> returns OBJ text for adding to viewer."""
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        res = self.client.get(f"/api/meshes/{mesh_id}", headers=self._auth())
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"v ", res.data)

    def test_mesh_metadata_retrievable_for_viewer(self):
        """GET /api/meshes/<id>/metadata returns JSON metadata."""
        res = self._upload_mesh()
        mesh_id = res.get_json()["data"]["id"]
        res = self.client.get(f"/api/meshes/{mesh_id}/metadata", headers=self._auth())
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

    def test_point_cloud_list_endpoint(self):
        """GET /api/point-clouds returns list (used by toggle UI)."""
        res = self.client.get("/api/point-clouds", headers=self._auth())
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["data"], list)

    def test_multiple_mesh_metadata_independent(self):
        """Each mesh has independent metadata (viewer can load several)."""
        r1 = self._upload_mesh("mesh1.obj", "LOC-A")
        r2 = self._upload_mesh("mesh2.obj", "LOC-B")
        id1 = r1.get_json()["data"]["id"]
        id2 = r2.get_json()["data"]["id"]
        m1 = self.client.get(f"/api/meshes/{id1}/metadata", headers=self._auth()).get_json()
        m2 = self.client.get(f"/api/meshes/{id2}/metadata", headers=self._auth()).get_json()
        self.assertNotEqual(m1["data"]["id"], m2["data"]["id"])


if __name__ == "__main__":
    unittest.main()
