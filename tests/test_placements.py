"""Tests for the vehicle placement store and overlap detection."""
import json
import math
import os
import tempfile
import unittest

from backend.placements.store import (
    Placement,
    PlacementStore,
    _polygons_overlap,
)


class TestPlacement(unittest.TestCase):
    """Unit tests for the Placement value object."""

    def test_round_trip(self):
        data = {
            "mesh_id": "m1",
            "vehicle_id": "sedan",
            "x": 10.0,
            "y": 1.5,
            "z": 20.0,
            "rotation_y": 0.5,
            "length": 4.8,
            "width": 1.8,
            "height": 1.5,
            "color": "#2ecc71",
            "placed_by": "tester",
        }
        p = Placement(data)
        d = p.to_dict()
        self.assertEqual(d["mesh_id"], "m1")
        self.assertEqual(d["vehicle_id"], "sedan")
        self.assertAlmostEqual(d["x"], 10.0)
        self.assertAlmostEqual(d["rotation_y"], 0.5)
        self.assertEqual(d["color"], "#2ecc71")

    def test_corners_no_rotation(self):
        p = Placement({
            "mesh_id": "m1",
            "x": 0,
            "y": 0,
            "z": 0,
            "rotation_y": 0,
            "length": 4,
            "width": 2,
            "height": 1,
        })
        corners = p.corners_2d()
        self.assertEqual(len(corners), 4)
        # Corners should span from -1..1 in X and -2..2 in Z
        xs = [c[0] for c in corners]
        zs = [c[1] for c in corners]
        self.assertAlmostEqual(min(xs), -1.0)
        self.assertAlmostEqual(max(xs), 1.0)
        self.assertAlmostEqual(min(zs), -2.0)
        self.assertAlmostEqual(max(zs), 2.0)

    def test_corners_with_rotation(self):
        p = Placement({
            "mesh_id": "m1",
            "x": 0,
            "y": 0,
            "z": 0,
            "rotation_y": math.pi / 2,  # 90 degrees
            "length": 4,
            "width": 2,
            "height": 1,
        })
        corners = p.corners_2d()
        # After 90-deg rotation, X extent should be ~length/2, Z extent ~width/2
        xs = [c[0] for c in corners]
        zs = [c[1] for c in corners]
        self.assertAlmostEqual(max(xs), 2.0, places=5)
        self.assertAlmostEqual(max(zs), 1.0, places=5)


class TestOverlapDetection(unittest.TestCase):
    """Tests for the polygon overlap (SAT) algorithm."""

    def _make_corners(self, x, z, w, l, rot=0):
        p = Placement({
            "mesh_id": "m1",
            "x": x, "y": 0, "z": z,
            "rotation_y": rot,
            "length": l, "width": w, "height": 1,
        })
        return p.corners_2d()

    def test_identical_boxes_overlap(self):
        a = self._make_corners(0, 0, 2, 4)
        b = self._make_corners(0, 0, 2, 4)
        self.assertTrue(_polygons_overlap(a, b))

    def test_adjacent_boxes_no_overlap(self):
        # Two cars side by side, just touching edges
        a = self._make_corners(0, 0, 2, 4)
        b = self._make_corners(2.1, 0, 2, 4)  # shifted right by more than width
        self.assertFalse(_polygons_overlap(a, b))

    def test_overlapping_boxes(self):
        a = self._make_corners(0, 0, 2, 4)
        b = self._make_corners(1.0, 0, 2, 4)  # overlaps by 0.5 on each side
        self.assertTrue(_polygons_overlap(a, b))

    def test_far_apart_no_overlap(self):
        a = self._make_corners(0, 0, 2, 4)
        b = self._make_corners(100, 100, 2, 4)
        self.assertFalse(_polygons_overlap(a, b))

    def test_rotated_overlap(self):
        a = self._make_corners(0, 0, 2, 4, rot=0)
        b = self._make_corners(0, 0, 2, 4, rot=math.pi / 4)
        self.assertTrue(_polygons_overlap(a, b))

    def test_rotated_no_overlap(self):
        # Place one far enough that even rotated they don't touch
        a = self._make_corners(0, 0, 2, 4, rot=0)
        b = self._make_corners(10, 0, 2, 4, rot=math.pi / 4)
        self.assertFalse(_polygons_overlap(a, b))


class TestPlacementStore(unittest.TestCase):
    """Integration tests for PlacementStore JSON persistence."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_file = os.path.join(self.tmpdir, "placements.json")
        self.store = PlacementStore(self.data_file)

    def tearDown(self):
        if os.path.exists(self.data_file):
            os.remove(self.data_file)
        os.rmdir(self.tmpdir)

    def test_empty_initially(self):
        self.assertEqual(self.store.list_for_mesh("m1"), [])

    def test_commit_and_list(self):
        p, err = self.store.commit({
            "mesh_id": "m1",
            "x": 5, "y": 1, "z": 10,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.assertIsNone(err)
        self.assertIsNotNone(p)

        listed = self.store.list_for_mesh("m1")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, p.id)

    def test_commit_overlap_rejected(self):
        # First placement at origin
        p1, err1 = self.store.commit({
            "mesh_id": "m1",
            "x": 0, "y": 1, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.assertIsNone(err1)

        # Second placement at the same spot — should be rejected
        p2, err2 = self.store.commit({
            "mesh_id": "m1",
            "x": 0, "y": 1, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.assertIsNone(p2)
        self.assertIn("Overlaps", err2)

    def test_commit_different_mesh_no_overlap(self):
        """Vehicles on different meshes never overlap."""
        p1, _ = self.store.commit({
            "mesh_id": "m1",
            "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        p2, err2 = self.store.commit({
            "mesh_id": "m2",
            "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.assertIsNone(err2)
        self.assertIsNotNone(p2)

    def test_commit_adjacent_succeeds(self):
        self.store.commit({
            "mesh_id": "m1",
            "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        # Place next to the first one with a gap
        p2, err2 = self.store.commit({
            "mesh_id": "m1",
            "x": 5, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.assertIsNone(err2)
        self.assertIsNotNone(p2)

    def test_delete_placement(self):
        p, _ = self.store.commit({
            "mesh_id": "m1",
            "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.assertTrue(self.store.delete(p.id))
        self.assertEqual(len(self.store.list_for_mesh("m1")), 0)

    def test_delete_nonexistent(self):
        self.assertFalse(self.store.delete("no-such-id"))

    def test_delete_all_for_mesh(self):
        self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.store.commit({
            "mesh_id": "m1", "x": 10, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        self.store.commit({
            "mesh_id": "m2", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        count = self.store.delete_all_for_mesh("m1")
        self.assertEqual(count, 2)
        self.assertEqual(len(self.store.list_for_mesh("m1")), 0)
        self.assertEqual(len(self.store.list_for_mesh("m2")), 1)

    def test_persistence_across_instances(self):
        self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        # New store instance reads from same file
        store2 = PlacementStore(self.data_file)
        self.assertEqual(len(store2.list_for_mesh("m1")), 1)

    def test_departure_date_stored(self):
        p, err = self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
            "departure_date": "2025-12-31",
        })
        self.assertIsNone(err)
        self.assertEqual(p.departure_date, "2025-12-31")
        d = p.to_dict()
        self.assertEqual(d["departure_date"], "2025-12-31")

    def test_departure_date_persists(self):
        self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
            "departure_date": "2025-06-15",
        })
        store2 = PlacementStore(self.data_file)
        listed = store2.list_for_mesh("m1")
        self.assertEqual(listed[0].departure_date, "2025-06-15")

    def test_update_position(self):
        p, _ = self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        updated, err = self.store.update(p.id, {"x": 10, "z": 10})
        self.assertIsNone(err)
        self.assertAlmostEqual(updated.x, 10)
        self.assertAlmostEqual(updated.z, 10)

    def test_update_departure_date(self):
        p, _ = self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        updated, err = self.store.update(p.id, {"departure_date": "2025-09-01"})
        self.assertIsNone(err)
        self.assertEqual(updated.departure_date, "2025-09-01")

    def test_update_overlap_rejected(self):
        """Moving a vehicle onto another should be rejected."""
        self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        p2, _ = self.store.commit({
            "mesh_id": "m1", "x": 10, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        updated, err = self.store.update(p2.id, {"x": 0, "z": 0})
        self.assertIsNone(updated)
        self.assertIn("overlaps", err.lower())

    def test_update_self_no_overlap(self):
        """Updating a vehicle at its own position should succeed (self-exclusion)."""
        p, _ = self.store.commit({
            "mesh_id": "m1", "x": 0, "y": 0, "z": 0,
            "length": 4, "width": 2, "height": 1.5,
        })
        updated, err = self.store.update(p.id, {"x": 0, "z": 0})
        self.assertIsNone(err)
        self.assertIsNotNone(updated)

    def test_update_nonexistent(self):
        updated, err = self.store.update("no-such-id", {"x": 0})
        self.assertIsNone(updated)
        self.assertIn("not found", err.lower())


if __name__ == "__main__":
    unittest.main()
