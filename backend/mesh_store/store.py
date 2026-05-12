"""Mesh storage with real-world coordinate metadata.

Each mesh is stored as a file in the meshes/ directory with an entry
in a JSON metadata registry that records the real-world origin, CRS,
and unit so the web viewer can display correct scale.
"""
import json
import os
import uuid
from typing import List, Optional


class MeshMetadata:
    """Value object holding real-world metadata for a single mesh."""

    def __init__(self, data: dict):
        self.id = data.get("id", str(uuid.uuid4()))
        self.filename = data["filename"]
        self.location_id = data.get("location_id", "default")
        self.description = data.get("description", "")
        self.crs = data.get("crs", "EPSG:3794")
        self.center_x = float(data.get("center_x", 0.0))
        self.center_y = float(data.get("center_y", 0.0))
        self.center_z = float(data.get("center_z", 0.0))
        self.bounds_min = data.get("bounds_min", [0, 0, 0])
        self.bounds_max = data.get("bounds_max", [0, 0, 0])
        self.unit = data.get("unit", "meters")
        self.algorithm = data.get("algorithm", "poisson")
        self.rotation_y = float(data.get("rotation_y", 0.0))
        self.offset_x = float(data.get("offset_x", 0.0))
        self.offset_y = float(data.get("offset_y", 0.0))
        self.offset_z = float(data.get("offset_z", 0.0))
        self.color = data.get("color", None)  # hex colour or None
        self.paint_strokes = data.get("paint_strokes", [])
        self.owner = data.get("owner", None)  # user identifier (e.g., MAC or access code)
        self.public = bool(data.get("public", False))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "location_id": self.location_id,
            "description": self.description,
            "crs": self.crs,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "center_z": self.center_z,
            "bounds_min": self.bounds_min,
            "bounds_max": self.bounds_max,
            "unit": self.unit,
            "algorithm": self.algorithm,
            "rotation_y": self.rotation_y,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "offset_z": self.offset_z,
            "color": self.color,
            "paint_strokes": self.paint_strokes,
            "owner": self.owner,
            "public": self.public,
        }


class MeshStore:
    """Registry for mesh files and their real-world metadata."""

    def __init__(self, data_file: str, mesh_dir: str):
        self._data_file = data_file
        self._mesh_dir = mesh_dir
        self._ensure_storage()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save_mesh(self, file_storage, metadata: dict) -> MeshMetadata:
        """Save an uploaded mesh file and register its metadata."""
        meta = MeshMetadata(metadata)
        filepath = os.path.join(self._mesh_dir, meta.filename)
        file_storage.save(filepath)
        self._register(meta)
        return meta

    def register(self, **kwargs) -> MeshMetadata:
        """Register a mesh file that already exists in *mesh_dir*.

        Accepts keyword arguments matching :class:`MeshMetadata` fields.
        Returns the registered metadata object or ``None`` if file missing.
        """
        meta = MeshMetadata(kwargs)
        filepath = os.path.join(self._mesh_dir, meta.filename)
        if not os.path.exists(filepath):
            return None
        self._register(meta)
        return meta

    def get(self, mesh_id: str) -> Optional[MeshMetadata]:
        """Look up mesh metadata by id."""
        entry = self._read()["meshes"].get(mesh_id)
        if not entry:
            return None
        return MeshMetadata(self._merge_reference_metadata(entry))

    def list_meshes(self, location_id: Optional[str] = None) -> List[MeshMetadata]:
        """List meshes, optionally filtered by location.

        If *location_id* is ``None`` or ``"*"``, all meshes are returned.
        Otherwise only meshes whose location matches, or with location
        ``"default"``, are included.
        """
        all_meshes = [
            MeshMetadata(self._merge_reference_metadata(m))
            for m in self._read()["meshes"].values()
        ]
        if location_id and location_id != "*":
            location_normalized = str(location_id).strip().lower()
            return [
                m for m in all_meshes
                if str(m.location_id).strip().lower() in {location_normalized, "default"}
            ]
        return all_meshes

    def update(self, mesh_id: str, updates: dict) -> Optional[MeshMetadata]:
        """Patch metadata fields for a mesh."""
        data = self._read()
        if mesh_id not in data["meshes"]:
            return None
        # Only allow updating known fields
        safe_keys = {
            "description", "location_id", "crs", "center_x", "center_y",
            "center_z", "unit", "algorithm", "rotation_y",
            "offset_x", "offset_y", "offset_z",
            "bounds_min", "bounds_max", "color", "paint_strokes",
            "public"
        }
        for key in updates:
            if key in safe_keys:
                data["meshes"][mesh_id][key] = updates[key]
        self._write(data)
        return MeshMetadata(data["meshes"][mesh_id])

    def delete(self, mesh_id: str) -> bool:
        """Delete mesh file and metadata. Returns ``True`` if found."""
        data = self._read()
        if mesh_id not in data["meshes"]:
            return False
        filename = data["meshes"][mesh_id]["filename"]
        filepath = os.path.join(self._mesh_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        del data["meshes"][mesh_id]
        self._write(data)
        return True

    def filepath_for(self, mesh_id: str) -> Optional[str]:
        """Return absolute path to the mesh file, or ``None``."""
        meta = self.get(mesh_id)
        if not meta:
            return None
        return os.path.join(self._mesh_dir, meta.filename)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
        os.makedirs(self._mesh_dir, exist_ok=True)
        if not os.path.exists(self._data_file):
            self._write({"meshes": {}})

    def _register(self, meta: MeshMetadata):
        data = self._read()
        data["meshes"][meta.id] = meta.to_dict()
        self._write(data)

    def _read(self) -> dict:
        with open(self._data_file, "r") as fh:
            return json.load(fh)

    def _write(self, data: dict):
        with open(self._data_file, "w") as fh:
            json.dump(data, fh, indent=2)

    def _merge_reference_metadata(self, entry: dict) -> dict:
        """Merge accurate georeference from mesh sidecar meta file.

        Sidecar naming: <mesh-file-stem>.meta.json
        """
        merged = dict(entry)
        sidecar = self._read_sidecar_meta(merged.get("filename", ""))
        if not sidecar:
            return merged

        for key in ("crs", "unit", "center_x", "center_y", "center_z", "bounds_min", "bounds_max"):
            candidate = sidecar.get(key)
            if candidate is not None:
                merged[key] = candidate

        return merged

    def _read_sidecar_meta(self, filename: str) -> Optional[dict]:
        if not filename:
            return None
        stem, _ = os.path.splitext(filename)
        sidecar_path = os.path.join(self._mesh_dir, f"{stem}.meta.json")
        if not os.path.exists(sidecar_path):
            return None
        try:
            with open(sidecar_path, "r") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
