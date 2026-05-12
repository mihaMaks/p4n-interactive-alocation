"""Persistent vehicle placement store with overlap detection.

Each placement is a box with position, rotation, and dimensions on a mesh.
Before committing, the store checks for collisions with existing placements.
"""
import json
import math
import os
import uuid
from typing import Dict, List, Optional
from datetime import datetime


class Placement:
    """Value object for a single committed vehicle placement."""

    __slots__ = (
        "id", "mesh_id", "vehicle_id",
        "x", "y", "z", "rotation_y",
        "length", "width", "height", "color",
        "placed_by", "vehicle_name", "departure_date",
    )

    def __init__(self, data: dict):
        self.id = data.get("id", str(uuid.uuid4()))
        self.mesh_id = data["mesh_id"]
        self.vehicle_id = data.get("vehicle_id", "custom")
        self.x = float(data.get("x", 0))
        self.y = float(data.get("y", 0))
        self.z = float(data.get("z", 0))
        self.rotation_y = float(data.get("rotation_y", 0))
        self.length = float(data.get("length", 4))
        self.width = float(data.get("width", 2))
        self.height = float(data.get("height", 1.5))
        self.color = data.get("color", "#3498db")
        self.placed_by = data.get("placed_by", "")
        self.vehicle_name = data.get("vehicle_name", "")
        self.departure_date = data.get("departure_date", "")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mesh_id": self.mesh_id,
            "vehicle_id": self.vehicle_id,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "rotation_y": self.rotation_y,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "color": self.color,
            "placed_by": self.placed_by,
            "vehicle_name": self.vehicle_name,
            "departure_date": self.departure_date,
        }

    def corners_2d(self) -> List[tuple]:
        """Return the 4 corners of the vehicle footprint in the XZ plane."""
        hw = self.width / 2
        hl = self.length / 2
        cos_r = math.cos(self.rotation_y)
        sin_r = math.sin(self.rotation_y)
        raw = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]
        return [
            (self.x + c[0] * cos_r - c[1] * sin_r,
             self.z + c[0] * sin_r + c[1] * cos_r)
            for c in raw
        ]


def _project_polygon(corners, axis):
    """Project corners onto axis and return (min, max)."""
    dots = [c[0] * axis[0] + c[1] * axis[1] for c in corners]
    return min(dots), max(dots)


def _polygons_overlap(a_corners, b_corners) -> bool:
    """Separating Axis Theorem for two convex polygons."""
    for poly in (a_corners, b_corners):
        n = len(poly)
        for i in range(n):
            edge = (poly[(i + 1) % n][0] - poly[i][0],
                    poly[(i + 1) % n][1] - poly[i][1])
            axis = (-edge[1], edge[0])
            length = math.hypot(axis[0], axis[1])
            if length < 1e-12:
                continue
            axis = (axis[0] / length, axis[1] / length)
            a_min, a_max = _project_polygon(a_corners, axis)
            b_min, b_max = _project_polygon(b_corners, axis)
            if a_max <= b_min or b_max <= a_min:
                return False
    return True


class PlacementStore:
    """JSON-backed registry for committed vehicle placements."""

    def __init__(self, data_file: str):
        self._data_file = data_file
        self._ensure_storage()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_for_mesh(self, mesh_id: str) -> List[Placement]:
        return [
            Placement(p)
            for p in self._read()["placements"].values()
            if p["mesh_id"] == mesh_id
        ]

    def get(self, placement_id: str) -> Optional[Placement]:
        entry = self._read()["placements"].get(placement_id)
        return Placement(entry) if entry else None

    def list_for_mesh_filtered(self, mesh_id: str) -> list:
        """
        Return only placements for a mesh whose departure_date is in the future or empty.
        """
        now = datetime.now().astimezone()
        filtered = []
        for p in self.list_for_mesh(mesh_id):
            if not p.departure_date:
                filtered.append(p)
                continue
            try:
                # Accept both date and datetime-local formats
                dt = datetime.fromisoformat(p.departure_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=now.tzinfo)
                if dt > now:
                    filtered.append(p)
            except Exception:
                filtered.append(p)  # If parsing fails, keep it
        return filtered

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def commit(self, data: dict) -> tuple:
        """Attempt to commit a placement.

        Returns ``(placement, None)`` on success or ``(None, error_msg)``
        if the position overlaps an existing placement.
        """
        placement = Placement(data)
        new_corners = placement.corners_2d()

        existing = self.list_for_mesh(placement.mesh_id)
        for other in existing:
            if _polygons_overlap(new_corners, other.corners_2d()):
                return None, f"Overlaps with existing vehicle {other.id}"

        store_data = self._read()
        store_data["placements"][placement.id] = placement.to_dict()
        self._write(store_data)
        return placement, None

    def delete(self, placement_id: str) -> bool:
        data = self._read()
        if placement_id not in data["placements"]:
            return False
        del data["placements"][placement_id]
        self._write(data)
        return True

    def update(self, placement_id: str, updates: dict) -> tuple:
        """Move/update an existing placement.

        Checks overlap with other placements (excluding itself).
        Returns ``(placement, None)`` on success or ``(None, error_msg)``.
        """
        data = self._read()
        if placement_id not in data["placements"]:
            return None, "Placement not found"

        entry = dict(data["placements"][placement_id])
        safe_keys = {
            "x", "y", "z", "rotation_y", "departure_date",
            "vehicle_name", "color",
        }
        for k, v in updates.items():
            if k in safe_keys:
                entry[k] = v

        # Re-validate numeric fields that were updated
        for field in ("x", "y", "z", "rotation_y"):
            if field in updates:
                try:
                    entry[field] = float(entry[field])
                except (TypeError, ValueError):
                    return None, f"Invalid numeric value for {field}"

        updated = Placement(entry)

        # Check overlap against all other placements on the same mesh
        new_corners = updated.corners_2d()
        existing = [
            Placement(p)
            for p in data["placements"].values()
            if p["mesh_id"] == updated.mesh_id and p["id"] != placement_id
        ]
        for other in existing:
            if _polygons_overlap(new_corners, other.corners_2d()):
                return None, f"New position overlaps with vehicle {other.id}"

        data["placements"][placement_id] = updated.to_dict()
        self._write(data)
        return updated, None

    def delete_all_for_mesh(self, mesh_id: str) -> int:
        data = self._read()
        to_remove = [
            pid for pid, p in data["placements"].items()
            if p["mesh_id"] == mesh_id
        ]
        for pid in to_remove:
            del data["placements"][pid]
        self._write(data)
        return len(to_remove)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        if not os.path.exists(self._data_file):
            self._write({"placements": {}})

    def _read(self) -> dict:
        with open(self._data_file, "r") as fh:
            return json.load(fh)

    def _write(self, data: dict):
        with open(self._data_file, "w") as fh:
            json.dump(data, fh, indent=2)
