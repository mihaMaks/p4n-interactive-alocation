import laspy
import numpy as np
import os
import glob
import ast
from shapely.geometry import Polygon, Point
from pyproj import Transformer

# ==========================================
# CONFIGURATION
# ==========================================
COORD_FILE = "coordinates.txt"
INPUT_EPSG = "epsg:4326"   # Google Maps
OUTPUT_EPSG = "epsg:3794"  # Slovenia 1996
# ==========================================

def process_all_laz():
    if not os.path.exists(COORD_FILE):
        print(f"Error: {COORD_FILE} not found.")
        return

    with open(COORD_FILE, 'r') as f:
        google_coords = ast.literal_eval(f.read())

    transformer = Transformer.from_crs(INPUT_EPSG, OUTPUT_EPSG, always_xy=True)
    transformed_poly_coords = [transformer.transform(lon, lat) for lat, lon in google_coords]
    poly = Polygon(transformed_poly_coords)
    min_x, min_y, max_x, max_y = poly.bounds

    laz_files = glob.glob("*.laz")
    laz_files = [f for f in laz_files if not f.startswith("extracted_")]

    if not laz_files:
        print("No .laz files found.")
        return

    print(f"Found {len(laz_files)} files to process.")

    for file_path in laz_files:
        output_name = f"extracted_{file_path}"
        print(f"--- Processing: {file_path} ---")

        with laspy.open(file_path) as input_las:
            h = input_las.header
            # Header-level bounding box check
            if (h.min[0] > max_x or h.max[0] < min_x or 
                h.min[1] > max_y or h.max[1] < min_y):
                print(f"Skipping: Outside polygon area.")
                continue

            las = input_las.read()
            points = np.vstack((las.x, las.y, las.z)).transpose()

            # Filter points
            mask = (points[:, 0] >= min_x) & (points[:, 0] <= max_x) & \
                   (points[:, 1] >= min_y) & (points[:, 1] <= max_y)
            
            indices_in_bbox = np.where(mask)[0]
            if len(indices_in_bbox) == 0:
                print(f"No points in bounding box.")
                continue

            # Precise polygon mask
            # We only check points that passed the bounding box test
            points_to_check = points[mask]
            poly_mask = [poly.contains(Point(p[0], p[1])) for p in points_to_check]
            final_indices = indices_in_bbox[poly_mask]

            if len(final_indices) == 0:
                print(f"No points inside exact polygon.")
                continue

            # --- HEADER FIX STARTS HERE ---
            # Create a new file by copying the existing header exactly
            new_header = las.header
            
            # Create a new LasData object with the filtered points
            new_las = laspy.LasData(new_header)
            new_las.points = las.points[final_indices]
            # --- HEADER FIX ENDS HERE ---

            new_las.write(output_name)
            print(f"Saved {len(final_indices)} points to {output_name}")

    print("\nAll done!")

if __name__ == "__main__":
    process_all_laz()