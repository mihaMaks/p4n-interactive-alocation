import open3d as o3d
import laspy
import numpy as np
import glob
import os
import json

def create_meshes():
    extracted_files = glob.glob("extracted_*.laz")
    
    if not extracted_files:
        print("No 'extracted_*.laz' files found.")
        return

    # Look for GKOT file to use as colour source
    gkot_files = [f for f in extracted_files if "GKOT" in f.upper()]
    color_pcd = None
    color_kd = None

    if gkot_files:
        gkot_path = gkot_files[0]
        print(f"\n=== Loading colour source: {gkot_path} ===")
        with laspy.open(gkot_path) as fh:
            gkot_las = fh.read()
            gkot_pts = np.vstack((gkot_las.x, gkot_las.y, gkot_las.z)).transpose()
            color_pcd = o3d.geometry.PointCloud()
            color_pcd.points = o3d.utility.Vector3dVector(gkot_pts)
            if hasattr(gkot_las, 'red'):
                gkot_colors = np.vstack((gkot_las.red, gkot_las.green, gkot_las.blue)).transpose() / 65535.0
                color_pcd.colors = o3d.utility.Vector3dVector(gkot_colors)
                color_kd = o3d.geometry.KDTreeFlann(color_pcd)
                print(f"  Loaded {len(gkot_pts)} colour points from GKOT")
            else:
                print("  WARNING: GKOT file has no colour data")
                color_pcd = None

    # Process terrain files (DMR/DMP — not the GKOT itself)
    terrain_files = [f for f in extracted_files if "GKOT" not in f.upper()]
    if not terrain_files:
        terrain_files = extracted_files  # fallback: process everything

    for file_path in terrain_files:
        base_name = os.path.splitext(file_path)[0]
        print(f"\n--- Processing: {file_path} ---")

        # 1. Load LAZ
        with laspy.open(file_path) as fh:
            las = fh.read()
            points = np.vstack((las.x, las.y, las.z)).transpose()
            
            # CRITICAL: Center the points at 0,0,0
            # Large coordinate values cause precision errors in meshing math
            center = np.mean(points, axis=0)
            bounds_min = np.min(points, axis=0)
            bounds_max = np.max(points, axis=0)
            points_centered = points - center
            
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points_centered)
            
            # Transfer colours from GKOT via nearest-neighbour lookup
            if color_pcd is not None and color_kd is not None:
                print("  Transferring GKOT vertex colours via nearest-neighbour…")
                gkot_colors_arr = np.asarray(color_pcd.colors)
                transferred = np.zeros((len(points), 3))
                for i, pt in enumerate(points):  # Use original (non-centered) coords
                    _, idx, _ = color_kd.search_knn_vector_3d(pt, 1)
                    transferred[i] = gkot_colors_arr[idx[0]]
                pcd.colors = o3d.utility.Vector3dVector(transferred)
                print("  Colour transfer complete")
            elif hasattr(las, 'red'):
                colors = np.vstack((las.red, las.green, las.blue)).transpose() / 65535.0
                pcd.colors = o3d.utility.Vector3dVector(colors)

        # Build metadata for real-world reference
        metadata = {
            "source_file": file_path,
            "crs": "EPSG:3794",
            "unit": "meters",
            "center_x": float(center[0]),
            "center_y": float(center[1]),
            "center_z": float(center[2]),
            "bounds_min": [float(v) for v in bounds_min],
            "bounds_max": [float(v) for v in bounds_max],
            "num_points": len(points),
        }

        # 2. Prepare Point Cloud
        print("Cleaning and estimating normals...")
        pcd = pcd.voxel_down_sample(voxel_size=0.1) # Reduces noise
        pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=2.0, max_nn=30))
        pcd.orient_normals_consistent_tangent_plane(k=15)

        # --- ALGORITHM 1: Poisson Surface Reconstruction (Best for Terrain) ---
        print("Running Poisson Reconstruction...")
        mesh_poisson, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=9)
        
        # Poisson creates a "bubble" around the points; we crop it to where points actually exist
        vertices_to_remove = densities < np.quantile(densities, 0.1)
        mesh_poisson.remove_vertices_by_mask(vertices_to_remove)
        
        mesh_poisson.compute_vertex_normals()

        # Transfer vertex colours from the point cloud to the mesh via KDTree
        has_colors = pcd.has_colors()
        if has_colors:
            print("  Transferring colours to Poisson mesh…")
            pcd_kd = o3d.geometry.KDTreeFlann(pcd)
            mesh_verts = np.asarray(mesh_poisson.vertices)
            pcd_colors = np.asarray(pcd.colors)
            vert_colors = np.zeros_like(mesh_verts)
            for i, v in enumerate(mesh_verts):
                _, idx, _ = pcd_kd.search_knn_vector_3d(v, 1)
                vert_colors[i] = pcd_colors[idx[0]]
            mesh_poisson.vertex_colors = o3d.utility.Vector3dVector(vert_colors)
        else:
            mesh_poisson.paint_uniform_color([0.8, 0.8, 0.8])

        poisson_name = f"{base_name}_poisson"
        o3d.io.write_triangle_mesh(f"meshes/{poisson_name}.obj", mesh_poisson)
        print(f"Saved: {poisson_name}.obj")

        poisson_meta = {**metadata, "algorithm": "poisson", "filename": f"{poisson_name}.obj",
                        "has_vertex_colors": has_colors}
        with open(f"meshes/{poisson_name}.meta.json", "w") as f:
            json.dump(poisson_meta, f, indent=2)
        print(f"Saved: {poisson_name}.meta.json")

        # --- ALGORITHM 2: Adjusted Ball Pivoting (BPA) ---
        print("Running Ball Pivoting...")
        distances = pcd.compute_nearest_neighbor_distance()
        avg_dist = np.mean(distances)
        radii = [avg_dist, avg_dist * 2, avg_dist * 4]
        
        mesh_bpa = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, o3d.utility.DoubleVector(radii))
        
        mesh_bpa.compute_vertex_normals()

        bpa_name = f"{base_name}_bpa"
        o3d.io.write_triangle_mesh(f"meshes/{bpa_name}.obj", mesh_bpa)
        print(f"Saved: {bpa_name}.obj")

        bpa_meta = {**metadata, "algorithm": "ball_pivoting", "filename": f"{bpa_name}.obj"}
        with open(f"meshes/{bpa_name}.meta.json", "w") as f:
            json.dump(bpa_meta, f, indent=2)
        print(f"Saved: {bpa_name}.meta.json")

    print("\nMeshing complete!")
    print("Upload the .obj files via the web UI or register them with:")
    print("  python register_meshes.py")

if __name__ == "__main__":
    create_meshes()