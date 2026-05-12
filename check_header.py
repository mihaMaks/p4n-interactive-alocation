import laspy
import pyproj

def check_laz_header(file_path):
    with laspy.open(file_path) as fh:
        header = fh.header
        print(f"--- Header Info for {file_path} ---")
        print(f"Points: {header.point_count}")
        print(f"LAS Version: {header.version}")
        
        # Try to parse the CRS (requires pyproj)
        try:
            crs = header.parse_crs()
            print(f"CRS Found: {crs.name}")
            print(f"EPSG Code: {crs.to_epsg()}")
            print(f"Units: {crs.axis_info[0].unit_name}")
        except Exception:
            print("CRS: Not explicitly defined in header. (Common in older files)")

        # Check the bounds to see the coordinate scale
        print(f"X Bounds: {header.min[0]} to {header.max[0]}")
        print(f"Y Bounds: {header.min[1]} to {header.max[1]}")

check_laz_header('DMP_438_124.laz')