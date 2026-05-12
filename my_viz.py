import laspy
import numpy as np
import open3d as o3d
from shapely.geometry import Polygon, Point
from pyproj import Transformer
import ast
import os

# ==========================================
# CONFIGURATION
# ==========================================
LAZ_FILE = "GKOT_438_124.laz"
COORD_FILE = "coordinates.txt"
INPUT_EPSG = "epsg:4326"  # Google Maps (WGS84)
OUTPUT_EPSG = "epsg:3794" # Slovenia 1996 / National Grid
# ==========================================

def main():
    if not os.path.exists(LAZ_FILE):
        print(f"Error: Could not find the file '{LAZ_FILE}'")
        return

    # 1. Load the Google Maps coordinates from file
    with open(COORD_FILE, 'r') as f:
        google_coords = ast.literal_eval(f.read())

    # 2. Setup the Transformer
    # always_xy=True treats input as (Lon, Lat) and output as (East, North)
    transformer = Transformer.from_crs(INPUT_EPSG, OUTPUT_EPSG, always_xy=True)

    # Convert [Lat, Lon] from Google to [X, Y] in Meters
    transformed_poly_coords = [transformer.transform(lon, lat) for lat, lon in google_coords]
    poly = Polygon(transformed_poly_coords)

    # 3. Read the LAZ File
    print(f"Reading points from {LAZ_FILE}...")
    with laspy.open(LAZ_FILE) as fh:
        las = fh.read()
        points = np.vstack((las.x, las.y, las.z)).transpose()

    # 4. Spatial Filtering (Bounding Box then Polygon)
    min_x, min_y, max_x, max_y = poly.bounds
    mask = (points[:, 0] >= min_x) & (points[:, 0] <= max_x) & \
           (points[:, 1] >= min_y) & (points[:, 1] <= max_y)

    inside_bbox = points[mask]
    
    if len(inside_bbox) == 0:
        print(f"Warning: No points from {LAZ_FILE} fall within the polygon's area.")
        return

    # Precise point-in-polygon check
    final_mask = [poly.contains(Point(p[0], p[1])) for p in inside_bbox]
    filtered_points = inside_bbox[final_mask]

    print(f"Extraction complete.")
    print(f"Displaying {len(filtered_points)} points from: {LAZ_FILE}")

    # 5. Visualize with Open3D
    if len(filtered_points) > 0:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(filtered_points)
        
        # Apply colors if the LAZ file contains RGB data
        if hasattr(las, 'red'):
            # Laspy colors are 16-bit (0-65535), Open3D wants 0.0-1.0
            colors = np.vstack((las.red, las.green, las.blue)).transpose() / 65535.0
            pcd.colors = o3d.utility.Vector3dVector(colors[mask][final_mask])
            
        # Create the visualizer window
        o3d.visualization.draw_geometries([pcd], 
                                          window_name=f"Viewing: {LAZ_FILE}",
                                          width=1024, 
                                          height=768)
    else:
        print("Search resulted in 0 points. Double-check your coordinates!")

if __name__ == "__main__":
    main()