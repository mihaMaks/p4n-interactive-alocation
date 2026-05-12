"""Register mesh files that already exist in meshes/ with their .meta.json sidecar files.

Run this after create_meshes.py to make meshes available in the web UI
without uploading them manually.

Usage:
    python register_meshes.py [--location LOCATION_ID]
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend.mesh_store.store import MeshStore


def main():
    parser = argparse.ArgumentParser(description="Register meshes from sidecar metadata files.")
    parser.add_argument("--location", default="default", help="Location ID to assign (default: 'default')")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    mesh_dir = os.path.join(base_dir, "meshes")
    data_dir = os.path.join(base_dir, "data")

    store = MeshStore(
        data_file=os.path.join(data_dir, "mesh_metadata.json"),
        mesh_dir=mesh_dir,
    )

    meta_files = glob.glob(os.path.join(mesh_dir, "*.meta.json"))
    if not meta_files:
        print("No .meta.json files found in meshes/")
        return

    for meta_path in meta_files:
        with open(meta_path, "r") as f:
            meta = json.load(f)

        obj_path = os.path.join(mesh_dir, meta["filename"])
        if not os.path.exists(obj_path):
            print(f"  SKIP {meta['filename']} — file not found")
            continue

        # Check if already registered
        existing = store.list_meshes()
        already = any(m.filename == meta["filename"] for m in existing)
        if already:
            print(f"  SKIP {meta['filename']} — already registered")
            continue

        meta["location_id"] = args.location
        meta["description"] = meta.get("description", meta["filename"])
        from backend.mesh_store.store import MeshMetadata
        mm = MeshMetadata(meta)
        store._register(mm)
        print(f"  OK   {meta['filename']} (id={mm.id})")

    print("Done.")


if __name__ == "__main__":
    main()
