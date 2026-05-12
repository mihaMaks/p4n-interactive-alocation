# P4NA Location — Area Mesh Viewer

A web application for viewing LiDAR-generated terrain meshes, placing
real-world-scale vehicles on them, and generating meshes interactively from
point cloud files.  Access is controlled by location-specific codes — no
username/password required.

## Features

- **Access-code authentication** — each location has a unique code; no login needed
- **Maintainer mode** — upload OBJ meshes, adjust position/rotation, manage access codes
- **Point Cloud → Mesh** — upload `.laz`/`.las` files, preview them in 3D, select an area, and generate meshes with colour preservation
- **User mode** — select a mesh, pick a vehicle type, click to place it on the terrain
- **Real-world scale** — meshes keep their EPSG:3794 metre coordinates; vehicles are rendered at true dimensions
- **Vehicle catalogue** — predefined types (car, SUV, van, truck, bus, bicycle) plus custom dimensions
- **GKOT colour support** — transfer real-world orthophoto colours from GKOT LiDAR files to meshes
- **Satellite overlay** — toggle ESRI satellite imagery on terrain meshes
- **Mesh processing** — Poisson/BPA surface reconstruction, hole filling, paint mode
- **Activity log** — maintainer audit trail for all operations
- **Scene export** — download the scene as `.gltf` for external tools

## Quick Start

```bash
# 1. Create a virtual environment
python3 -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Generate meshes from LiDAR data
#    Place .laz files and coordinates.txt in the project root, then:
python extract.py
python create_meshes.py
python register_meshes.py --location PARK-438-124

# 4. Start the server
python run_backend.py
```

On first launch the server prints a **maintainer access code** — copy it.
Open `http://localhost:5009`, paste the code, and you are in maintainer mode.

## Architecture

```
p4nAlocation/
├── backend/
│   ├── auth/                    # Access-code store (JSON file)
│   │   └── access_codes.py
│   ├── mesh_store/              # Mesh registry + real-world metadata
│   │   └── store.py
│   ├── vehicles/                # Vehicle catalogue (dimensions in metres)
│   │   └── catalog.py
│   ├── api/                     # Flask REST API
│   │   └── app.py               #   routes: auth, meshes, vehicles, point clouds
│   ├── point_cloud/             # Point cloud processing (loaders, extractors, filters)
│   ├── point_cloud_manager/     # Point cloud upload, preview, area-select, mesh gen
│   │   └── manager.py
│   └── model/                   # Mesh generation (Poisson, BPA, exporters)
├── frontend/
│   ├── index.html               # Single-page app shell
│   ├── style.css                # UI styles
│   ├── app.js                   # Application controller
│   └── viewer.js                # Three.js scene viewer
├── tests/
│   ├── test_api.py              # API integration tests (30 tests)
│   ├── test_placements.py       # Placement + overlap tests (25 tests)
│   ├── test_mesh_processing.py  # Mesh processing tests (7 tests)
│   └── test_point_cloud.py      # Point cloud feature tests (18 tests)
├── data/                        # Runtime data (auto-created)
│   ├── access_codes.json
│   └── mesh_metadata.json
├── meshes/                      # OBJ mesh files
├── uploads/                     # Uploaded point cloud files
├── create_meshes.py             # CLI: LAZ → OBJ + metadata
├── extract.py                   # CLI: polygon extraction from LAZ
├── run_backend.py               # Entry point
└── requirements.txt
```

### Clean Code Principles (Uncle Bob)

| Principle | How it is applied |
|---|---|
| **Single Responsibility** | Each module has one job: `access_codes.py` manages codes, `store.py` manages meshes, `catalog.py` defines vehicles, `app.py` wires HTTP routes. |
| **Open/Closed** | New vehicle types are added to the catalogue list without modifying existing code. New mesh formats can be registered without changing the store. |
| **Liskov Substitution** | Point-cloud loaders and generators implement abstract base classes and are interchangeable. |
| **Interface Segregation** | The frontend only depends on small, focused API endpoints — not a monolithic service. |
| **Dependency Inversion** | `app.py` depends on abstractions (`AccessCodeStore`, `MeshStore`) injected at creation time, not on file-system details. |
| **Small functions** | Every function does one thing; names describe intent. |
| **No duplication** | Auth logic lives in two decorators reused across all protected routes. |

## API Reference

All protected endpoints require the header `X-Access-Code: <code>`.

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/verify` | none | Verify a code → returns role + location |
| GET | `/api/auth/codes` | maintainer | List all codes |
| POST | `/api/auth/codes` | maintainer | Create a new code |
| DELETE | `/api/auth/codes/<code>` | maintainer | Revoke a code |

### Meshes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/meshes` | any | List meshes (filtered by location for users) |
| POST | `/api/meshes` | maintainer | Upload mesh file + metadata |
| GET | `/api/meshes/<id>` | any | Download mesh file |
| GET | `/api/meshes/<id>/metadata` | any | Get mesh metadata |
| PUT | `/api/meshes/<id>/metadata` | maintainer | Update metadata (corrections) |
| DELETE | `/api/meshes/<id>` | maintainer | Delete mesh |

### Vehicles

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/vehicles` | any | List vehicle catalogue |
| GET | `/api/vehicles/<id>` | any | Get single vehicle details |

### Placements

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/meshes/<id>/placements` | any | List committed placements |
| POST | `/api/meshes/<id>/placements` | any | Commit a new placement |
| PUT | `/api/meshes/<id>/placements/<pid>` | any | Move / update placement |
| DELETE | `/api/meshes/<id>/placements/<pid>` | any | Remove placement |

### Point Clouds

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/point-clouds` | maintainer | List uploaded point cloud files |
| POST | `/api/point-clouds` | maintainer | Upload a `.laz`/`.las` file |
| GET | `/api/point-clouds/<file>/preview` | maintainer | Downsampled preview (positions + colours) |
| POST | `/api/point-clouds/<file>/generate-mesh` | maintainer | Generate mesh from selected area |

### Activity Log

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/activity-log` | maintainer | List recent activity entries |

## Mesh Metadata & Real-World Scale

Each mesh is registered with metadata that preserves its real-world reference:

```json
{
  "crs": "EPSG:3794",
  "unit": "meters",
  "center_x": 438123.45,
  "center_y": 124567.89,
  "center_z": 412.3,
  "offset_x": 0, "offset_y": 0, "offset_z": 0,
  "rotation_y": 0
}
```

- **center_x/y/z** — the real-world coordinate that was subtracted when centering the mesh
- **unit** — always `meters` for EPSG:3794, so 1 Three.js unit = 1 metre
- **offset/rotation** — maintainer corrections applied in the viewer

## Vehicle Dimensions

All vehicles are rendered as box geometries at their true dimensions:

| Type | Length | Width | Height |
|---|---|---|---|
| Small Car | 4.0 m | 1.8 m | 1.5 m |
| Sedan | 4.8 m | 1.8 m | 1.5 m |
| SUV | 4.5 m | 1.9 m | 1.7 m |
| Van | 5.3 m | 1.9 m | 2.0 m |
| Truck | 8.0 m | 2.5 m | 3.5 m |
| Bus | 12.0 m | 2.5 m | 3.2 m |
| Motorcycle | 2.2 m | 0.8 m | 1.1 m |
| Bicycle | 1.8 m | 0.6 m | 1.0 m |
| Custom | user-defined | | |

## Workflow

### Maintainer

1. Start the server (`make run` or `python run_backend.py`) and log in with the maintainer code
2. **Option A — CLI mesh generation:** Run `extract.py` → `create_meshes.py` to generate OBJ meshes, then upload via sidebar
3. **Option B — Point Cloud → Mesh in browser:**
   - Go to the "Point Cloud → Mesh" panel
   - Upload a `.laz` or `.las` file
   - Select the file and click "Load Preview" to visualise the point cloud
   - Click "Select Area (Click 2 Corners)" and click two points on the point cloud, or enter bounds manually
   - Choose algorithm (Poisson / BPA), optionally select a GKOT colour source
   - Click "Generate Mesh from Selection" — the mesh is generated server-side and registered automatically
4. Adjust mesh position/rotation with correction sliders, save changes
5. Use the paint tool or hole fill for fine-tuning
6. Generate access codes for users and share them

### User

1. Receive a location code from the maintainer
2. Open the web app and enter the code
3. Select a mesh from the list
4. Choose a vehicle type and click "Place on Mesh"
5. Click on the terrain to place the vehicle; repeat as needed
6. Export the scene as `.gltf` if desired

## Usage

### Starting the Application

```bash
make run          # activates venv, installs deps, runs on port 5009
```

Or manually:

```bash
source venv/bin/activate
pip install -r requirements.txt
python run_backend.py   # serves API + frontend on http://localhost:5009
```

On first launch the server prints a **maintainer access code** — copy it.
Open `http://localhost:5009`, paste the code, and you are in maintainer mode.

### Point Cloud → Mesh API Example

```bash
# Upload a point cloud
curl -X POST http://localhost:5009/api/point-clouds \
  -H "X-Access-Code: <maintainer-code>" \
  -F "file=@DMR_438_124.laz"

# Get downsampled preview
curl http://localhost:5009/api/point-clouds/DMR_438_124.laz/preview \
  -H "X-Access-Code: <maintainer-code>"

# Generate mesh from selected area
curl -X POST http://localhost:5009/api/point-clouds/DMR_438_124.laz/generate-mesh \
  -H "X-Access-Code: <maintainer-code>" \
  -H "Content-Type: application/json" \
  -d '{
    "bounds_min": [438000, 124000],
    "bounds_max": [438200, 124200],
    "algorithm": "poisson",
    "color_source": "GKOT_438_124.laz",
    "location_id": "PARK-438-124",
    "description": "Park terrain"
  }'
```

## Supported File Formats

| Type | Formats | Notes |
|---|---|---|
| Input point clouds | `.laz`, `.las` | LiDAR point clouds (EPSG:3794) |
| Input meshes | `.obj` | Wavefront OBJ with optional vertex colours |
| Output meshes | `.obj` | Generated by Poisson or BPA algorithms |
| Scene export | `.gltf` | From Three.js viewer |

## Mesh Generation Algorithms

### Poisson Surface Reconstruction
- **Best for**: Dense, well-distributed point clouds
- Uses Open3D `create_from_point_cloud_poisson` with depth 9
- Produces smooth, watertight surfaces

### Ball Pivoting Algorithm (BPA)
- **Best for**: Detailed surface features
- Uses Open3D `create_from_point_cloud_ball_pivoting`
- Preserves fine detail; may leave holes in sparse regions

## Testing

```bash
make test          # activates venv, runs pytest
# or
python -m pytest tests/ -v
```

80 tests across 4 modules: API (30), placements (25), point-cloud (18), mesh processing (7).

## Troubleshooting

| Issue | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'open3d'` | `pip install --no-cache-dir open3d==0.17.0` |
| CORS errors | Already handled by Flask-CORS; check port 5009 |
| Memory errors on large point clouds | Use smaller selection area or downsample |
| Mesh generation slow | Reduce selection area; Poisson is faster than BPA for large inputs |

## References

- [Open3D Documentation](http://www.open3d.org/)
- [Three.js Documentation](https://threejs.org/docs/)
- [laspy Documentation](https://laspy.readthedocs.io/)
- [EPSG:3794](https://epsg.io/3794) — Slovenia 1996 / Slovene National Grid
- [Ball Pivoting Algorithm](http://www.cs.unm.edu/~dws/papers/bpa_tvcg.pdf)

## Support

For issues, feature requests, or questions:
1. Check troubleshooting section
2. Review API documentation
3. Create an issue with detailed description

## Authors

- AI Assistant (Claude)
- Based on Uncle Bob's SOLID principles

---

**Happy 3D modeling!** 🚀
