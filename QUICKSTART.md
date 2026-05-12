# Quick Start Guide

## 5-Minute Setup

### 1. Install Python Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the Backend API
```bash
python3 -m flask --app backend.api.app run
```

Server starts at: `http://localhost:5000`

### 3. Open the Web Interface
- Option A: Open `frontend/index.html` in your browser
- Option B: Serve with Python: `python3 -m http.server 8001 -d frontend`
  - Then visit: `http://localhost:8000`

### 4. Try It Out

#### Step 1: Prepare Test Data
Create a simple test point cloud (XYZ format):
```bash
mkdir -p /tmp/test_data
cat > /tmp/test_data/sample.xyz << 'EOF'
0 0 0
1 0 0
1 1 0
0 1 0
0.5 0.5 1
EOF
```

#### Step 2: Extract Region
```bash
curl -X POST http://localhost:5000/api/extract-region \
  -H "Content-Type: application/json" \
  -d '{
    "point_cloud_path": "/tmp/test_data/sample.xyz",
    "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]
  }'
```

#### Step 3: Generate Mesh
```bash
curl -X POST http://localhost:5000/api/generate-mesh \
  -H "Content-Type: application/json" \
  -d '{
    "point_cloud_path": "/tmp/test_data/sample.xyz",
    "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]],
    "algorithm": "point_cloud",
    "output_path": "/tmp/outputs/mesh.glb"
  }'
```

## Common Tasks

### Load Different Point Cloud Formats

```python
from backend.point_cloud import PointCloudLoaderFactory

factory = PointCloudLoaderFactory()

# Automatically detects format
cloud = factory.load('data/terrain.las')
cloud = factory.load('data/scan.ply')
cloud = factory.load('data/scene.pcd')
cloud = factory.load('data/points.xyz')
```

### Extract a Rectangular Region

```python
import numpy as np
from backend.point_cloud import PointCloudLoaderFactory, PolygonExtractorService

factory = PointCloudLoaderFactory()
extractor = PolygonExtractorService()

cloud = factory.load('data/large_cloud.las')

# Define rectangle: [x_min, y_min] to [x_max, y_max]
rectangle = [
    [1000, 2000],
    [1100, 2000],
    [1100, 2100],
    [1000, 2100],
]

# Extract with Z constraints
extracted = extractor.extract(cloud, rectangle, z_min=0, z_max=50)
```

### Filter Out Noise

```python
from backend.point_cloud import OutlierRemovalFilter, DownsamplingFilter

cloud = factory.load('data/noisy_cloud.las')

# Remove statistical outliers
outlier_filter = OutlierRemovalFilter(neighbors=20, std_ratio=2.0)
filtered = outlier_filter.filter(cloud)

# Downsample to reduce file size
downsample_filter = DownsamplingFilter(voxel_size=0.05)
downsampled = downsample_filter.filter(filtered)
```

### Generate Different Mesh Types

```python
from backend.model import PointCloudToMeshPipeline

pipeline = PointCloudToMeshPipeline()

cloud = factory.load('data/cloud.las')
extracted = pipeline.extract_region(cloud, polygon)
processed = pipeline.process_point_cloud(extracted)

# Poisson reconstruction (smooth surfaces)
mesh = pipeline.generate_mesh(processed, algorithm='poisson', depth=9)
pipeline.export_mesh(mesh, 'output/poisson.glb')

# Ball pivoting (detailed surfaces)
mesh = pipeline.generate_mesh(processed, algorithm='ball_pivoting')
pipeline.export_mesh(mesh, 'output/ball_pivot.glb')

# Convex hull (fast envelope)
mesh = pipeline.generate_mesh(processed, algorithm='convex_hull')
pipeline.export_mesh(mesh, 'output/hull.glb')

# Point cloud visualization
mesh = pipeline.generate_mesh(processed, algorithm='point_cloud', point_size=0.02)
pipeline.export_mesh(mesh, 'output/points.glb')
```

### Export to Different Formats

```python
# Automatic format detection based on file extension
pipeline.export_mesh(mesh, 'output/model.glb')    # glTF binary
pipeline.export_mesh(mesh, 'output/model.gltf')   # glTF JSON
pipeline.export_mesh(mesh, 'output/model.obj')    # Wavefront OBJ
pipeline.export_mesh(mesh, 'output/model.stl')    # STL (3D printing)
pipeline.export_mesh(mesh, 'output/model.ply')    # PLY
```

## API Quick Reference

### POST /api/extract-region
Extract points within polygon boundary
```json
{
  "point_cloud_path": "string",
  "polygon": [[x1, y1], [x2, y2], ...],
  "z_min": number (optional),
  "z_max": number (optional)
}
```

### POST /api/generate-mesh
Generate 3D mesh from point cloud region
```json
{
  "point_cloud_path": "string",
  "polygon": [[x1, y1], ...],
  "algorithm": "poisson|ball_pivoting|convex_hull|point_cloud",
  "output_path": "string",
  "z_min": number (optional),
  "z_max": number (optional),
  "generator_params": {}
}
```

### POST /api/upload-point-cloud
Upload point cloud file
```
Content-Type: multipart/form-data
file: <binary file>
```

### GET /api/supported-algorithms
List available mesh generation algorithms with parameters

### GET /api/supported-formats
List supported input/output file formats

## Keyboard Controls (Web UI)

- **Mouse drag**: Rotate view
- **Mouse scroll**: Zoom in/out
- **Right click + drag**: Pan view

## Performance Tips

1. **Large files**: Downsample before processing
   ```python
   from backend.point_cloud import DownsamplingFilter
   filter = DownsamplingFilter(voxel_size=0.1)
   downsampled = filter.filter(cloud)
   ```

2. **Faster mesh generation**: Use lower octree depth
   ```python
   mesh = pipeline.generate_mesh(processed, algorithm='poisson', depth=8)
   ```

3. **Extract smaller regions**: Process only the area you need

4. **Remove outliers**: Clean data before mesh generation
   ```python
   from backend.point_cloud import OutlierRemovalFilter
   filter = OutlierRemovalFilter()
   cleaned = filter.filter(cloud)
   ```

## Next Steps

1. **Explore different algorithms** on your data
2. **Integrate with your workflow** - use the API in Python or via HTTP
3. **Customize algorithms** - add your own mesh generation methods
4. **Build applications** - use the web UI as a starting point

## Getting Help

- Check `README.md` for detailed documentation
- Review code comments for implementation details
- Test endpoints with `curl` or Postman
- Check backend logs for error messages

Happy meshing! 🚀
