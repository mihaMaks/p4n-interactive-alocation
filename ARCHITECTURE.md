# Architecture

## Directory Structure

```
p4nAlocation/
├── backend/
│   ├── auth/                        # Access-code authentication
│   │   ├── __init__.py
│   │   └── access_codes.py         # AccessCodeStore — JSON-backed code registry
│   ├── mesh_store/                  # Mesh file storage + real-world metadata
│   │   ├── __init__.py
│   │   └── store.py                # MeshStore, MeshMetadata
│   ├── vehicles/                    # Vehicle catalogue (dimensions in metres)
│   │   ├── __init__.py
│   │   └── catalog.py              # VEHICLE_CATALOG list, get_catalog(), get_vehicle()
│   ├── point_cloud_manager/         # Interactive point cloud → mesh workflow
│   │   ├── __init__.py
│   │   └── manager.py              # PointCloudManager — upload, preview, generate
│   ├── api/                         # Flask REST API
│   │   ├── __init__.py
│   │   ├── app.py                  # create_app() — auth, meshes, vehicles, point clouds
│   │   ├── models.py               # Request/response models (legacy)
│   │   └── services.py             # Processing service (legacy)
│   ├── point_cloud/                 # Point cloud I/O and processing
│   │   ├── core.py                 # Abstract interfaces
│   │   ├── data.py                 # InMemoryPointCloud
│   │   ├── loaders.py              # LAS, PLY, PCD, XYZ loaders
│   │   ├── extractors.py           # Polygon & bounding-box extraction
│   │   ├── filters.py              # Outlier, downsampling, normalising
│   │   └── transforms.py           # Coordinate transformations (WGS84 ↔ EPSG:3794)
│   └── model/                       # 3D model generation
│       ├── core.py                 # Mesh dataclass, abstract generator/exporter
│       ├── generators.py           # Poisson, BPA, Convex Hull, Point Cloud
│       ├── exporters.py            # glTF, OBJ, STL, PLY export
│       └── pipeline.py             # End-to-end orchestration
├── frontend/
│   ├── index.html                   # SPA shell
│   ├── style.css                    # UI styles
│   ├── app.js                       # Application controller (login, API, UI logic)
│   └── viewer.js                    # SceneViewer — Three.js 3D + point cloud viewer
├── tests/
│   ├── test_api.py                  # API integration tests (30)
│   ├── test_placements.py           # Placement + overlap tests (25)
│   ├── test_mesh_processing.py      # Mesh processing tests (7)
│   └── test_point_cloud.py          # Point cloud feature tests (18)
├── data/                            # Runtime JSON data (auto-created)
├── meshes/                          # OBJ mesh files
├── uploads/                         # Uploaded point cloud files
├── extract.py                       # CLI: polygon extraction from LAZ files
├── create_meshes.py                 # CLI: LAZ → OBJ + .meta.json sidecar
├── run_backend.py                   # Server entry point (port 5009)
└── requirements.txt
```

## Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         WEB BROWSER                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Login Screen ──► access code ──► role + location          │  │
│  │                                                            │  │
│  │  Maintainer Mode               │   User Mode               │  │
│  │  • Upload point clouds (.laz)  │   • Browse meshes         │  │
│  │  • Preview point cloud in 3D   │   • Place vehicles        │  │
│  │  • Select area → generate mesh │   • Export scene           │  │
│  │  • Upload OBJ meshes           │                           │  │
│  │  • Correct position/rotation   │                           │  │
│  │  • Paint / hole fill           │                           │  │
│  │  • Manage access codes         │                           │  │
│  │                                                            │  │
│  │     Three.js SceneViewer (viewer.js) — mesh + point cloud  │  │
│  └─────────────────────┬──────────────────────────────────────┘  │
└────────────────────────┼─────────────────────────────────────────┘
                         │  X-Access-Code header
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FLASK API (port 5009)                         │
│                                                                  │
│  /api/auth/*           AccessCodeStore (JSON file)              │
│  /api/meshes/*         MeshStore (JSON metadata + OBJ files)    │
│  /api/point-clouds/*   PointCloudManager (upload, preview, gen) │
│  /api/vehicles/*       Vehicle catalogue (in-memory)            │
│  /api/activity-log     ActivityLog (JSON file)                  │
│  /                     Serves frontend/                          │
└──────────────────────────────────────────────────────────────────┘

Point Cloud → Mesh Flow:
  1. Upload .laz → /uploads/
  2. Preview → downsample + centre → JSON {positions, colors}
  3. Browser renders as THREE.Points with vertex colours
  4. User selects area (click 2 corners or manual bounds)
  5. Generate → extract 2D bbox → voxel downsample → normals → Poisson/BPA
  6. Optional GKOT colour transfer via KDTree nearest-neighbour
  7. OBJ saved to /meshes/, auto-registered in MeshStore

CLI tools (offline):
  extract.py ──► create_meshes.py
  (LAZ files)    (OBJ + .meta.json in meshes/)
```

## Authentication Model

- No username or password — a **location code** is the sole credential
- Each code maps to a **role** (`maintainer` or `user`) and a **location ID**
- Maintainer codes use `location_id: "*"` for full access
- Codes are checked on every API request via the `X-Access-Code` header
- On first run, the server generates and prints an initial maintainer code

## Real-World Scale

- Point clouds are in **EPSG:3794** (Slovenian spatial reference, unit = metre)
- `create_meshes.py` centres the mesh at 0,0,0 and records the **center offset** in `.meta.json`
- The web viewer uses metres as its native unit — `1 Three.js unit = 1 metre`
- Vehicle catalogue dimensions are in metres, so they render at correct scale
- Maintainer corrections (offset, rotation) are stored in metadata and applied on load
