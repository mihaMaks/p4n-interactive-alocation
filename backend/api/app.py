"""Flask REST API with access-code authentication and dual-mode operation.

Routes are organised into four groups:
  /api/auth/*      – verify and manage access codes
  /api/meshes/*    – CRUD for area meshes with real-world metadata
  /api/vehicles/*  – read-only vehicle catalogue
  /                – serves the frontend SPA
"""
import functools
import os
import uuid as _uuid_mod

from flask import Flask, app, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from .models import ExtractPolygonRequest, GenerateMeshRequest
from .services import ProcessingServiceFacade
from ..auth.access_codes import AccessCodeStore
from ..mesh_store.store import MeshStore
from ..vehicles.catalog import get_catalog, get_vehicle
from ..placements.store import PlacementStore
from ..mesh_processing.processor import process_mesh as run_process_mesh
from ..log.activity_log import ActivityLog
from ..point_cloud_manager import PointCloudManager
from .forum import forum_api

try:
    import pyproj
except ImportError:  # pragma: no cover
    pyproj = None


def create_app(config=None):
    """Application factory — returns a configured Flask instance."""
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(forum_api)

    # ── Paths ────────────────────────────────────────────────────────
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    mesh_dir   = os.path.join(base_dir, "meshes")
    data_dir   = os.path.join(base_dir, "data")
    upload_dir = os.path.join(base_dir, "uploads")
    frontend   = os.path.join(base_dir, "frontend")

    for d in (mesh_dir, data_dir, upload_dir):
        os.makedirs(d, exist_ok=True)

    app.config.update(
        MESH_DIR=mesh_dir,
        DATA_DIR=data_dir,
        UPLOAD_DIR=upload_dir,
        FRONTEND_DIR=frontend,
        MAX_CONTENT_LENGTH=500 * 1024 * 1024,  # 500 MB
    )
    if config:
        app.config.update(config)

    # Re-read paths from config (tests may override them)
    mesh_dir = app.config["MESH_DIR"]
    data_dir = app.config["DATA_DIR"]
    upload_dir = app.config["UPLOAD_DIR"]
    frontend = app.config["FRONTEND_DIR"]

    for d in (mesh_dir, data_dir, upload_dir):
        os.makedirs(d, exist_ok=True)

    # ── Stores ───────────────────────────────────────────────────────
    access_store = AccessCodeStore(os.path.join(data_dir, "access_codes.json"))
    mesh_store   = MeshStore(
        data_file=os.path.join(data_dir, "mesh_metadata.json"),
        mesh_dir=mesh_dir,
    )
    processing_facade = ProcessingServiceFacade()
    placement_store = PlacementStore(
        os.path.join(data_dir, "placements.json")
    )
    activity_log = ActivityLog(
        os.path.join(data_dir, "activity_log.json")
    )
    pc_manager = PointCloudManager(
        upload_dir=upload_dir,
        mesh_dir=mesh_dir,
    )
    

    def _augment_satellite_geo(meta_dict):
        """Attach accurate satellite/georeference helpers for frontend overlay."""
        data = dict(meta_dict)
        bounds_min = data.get("bounds_min")
        bounds_max = data.get("bounds_max")
        center_x = float(data.get("center_x", 0.0) or 0.0)
        center_y = float(data.get("center_y", 0.0) or 0.0)

        if not bounds_min or not bounds_max or len(bounds_min) < 2 or len(bounds_max) < 2:
            data["satellite_geo"] = None
            return data

        local_bounds = {
            "x_min": float(bounds_min[0]) - center_x,
            "x_max": float(bounds_max[0]) - center_x,
            # Terrain is rotated by -PI/2 around X in viewer: z = -northing_local
            "z_min": -(float(bounds_max[1]) - center_y),
            "z_max": -(float(bounds_min[1]) - center_y),
        }

        if pyproj is None:
            data["satellite_geo"] = {
                "wgs84_bounds": None,
                "local_bounds": local_bounds,
                "error": "pyproj not available",
            }
            return data

        try:
            src_crs = data.get("crs", "EPSG:3794")
            transformer = pyproj.Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

            lon1, lat1 = transformer.transform(float(bounds_min[0]), float(bounds_min[1]))
            lon2, lat2 = transformer.transform(float(bounds_max[0]), float(bounds_max[1]))

            data["satellite_geo"] = {
                "wgs84_bounds": {
                    "lon_min": min(lon1, lon2),
                    "lon_max": max(lon1, lon2),
                    "lat_min": min(lat1, lat2),
                    "lat_max": max(lat1, lat2),
                },
                "local_bounds": local_bounds,
                "source_crs": src_crs,
            }
        except Exception as exc:
            data["satellite_geo"] = {
                "wgs84_bounds": None,
                "local_bounds": local_bounds,
                "error": str(exc),
            }

        return data

    # ── Auth decorators ──────────────────────────────────────────────
    def _auth_info():
        code = request.headers.get("X-Access-Code", "")
        return access_store.verify(code)

    def require_auth(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            info = _auth_info()
            if not info:
                return jsonify(success=False, error="Invalid access code"), 401
            request.auth = info
            return fn(*a, **kw)
        return wrapper

    def require_maintainer(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            info = _auth_info()
            if not info or info["role"] != "maintainer":
                return jsonify(success=False, error="Maintainer access required"), 403
            request.auth = info
            return fn(*a, **kw)
        return wrapper

    # ── Error handlers ───────────────────────────────────────────────
    @app.errorhandler(400)
    def _bad_request(error):
        return jsonify(success=False, error=str(error)), 400

    @app.errorhandler(413)
    def _too_large(error):
        return jsonify(success=False, error="File too large (max 500 MB)"), 413

    @app.errorhandler(500)
    def _server_error(error):
        return jsonify(success=False, error=str(error)), 500

    # ── Frontend serving ─────────────────────────────────────────────
    @app.route("/")
    def serve_index():
        return send_from_directory(frontend, "index.html")

    @app.route("/<path:path>")
    def serve_static(path):
        return send_from_directory(frontend, path)

    # ── Health ───────────────────────────────────────────────────────
    @app.route("/api/health")
    def health():
        return jsonify(status="healthy")

    @app.route("/health")
    def health_legacy():
        return jsonify(status="healthy")

    # ── Legacy point-cloud pipeline endpoints ───────────────────────
    @app.route('/api/upload-point-cloud', methods=['POST'])
    def upload_point_cloud():
        if 'file' not in request.files:
            return jsonify({'success': False, 'data': None, 'error': 'No file provided'})

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'data': None, 'error': 'No file selected'})

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in {'.las', '.laz'}:
            return jsonify({'success': False, 'data': None, 'error': 'Only .las and .laz files are supported'})

        filename = secure_filename(file.filename)
        save_path = os.path.join(upload_dir, filename)
        file.save(save_path)

        return jsonify({
            'success': True,
            'data': {
                'filename': filename,
                'filepath': save_path,
                'size': os.path.getsize(save_path),
            },
            'error': None,
        })

    @app.route('/api/extract-region', methods=['POST'])
    def extract_region():
        data = request.get_json(silent=True) or {}
        req = ExtractPolygonRequest(data)
        is_valid, error_msg = req.validate()
        if not is_valid:
            return jsonify({'success': False, 'data': None, 'error': error_msg})

        response = processing_facade.extract_region(
            req.point_cloud_path,
            req.polygon,
            req.z_min,
            req.z_max,
        )
        return jsonify(response.to_dict())

    @app.route('/api/generate-mesh', methods=['POST'])
    def generate_mesh_legacy():
        data = request.get_json(silent=True) or {}
        req = GenerateMeshRequest(data)
        is_valid, error_msg = req.validate()
        if not is_valid:
            return jsonify({'success': False, 'data': None, 'error': error_msg})

        # Always save into the server-managed mesh directory; never trust the
        # client-supplied output_path (path-traversal risk + wrong location).
        src_stem = os.path.splitext(os.path.basename(req.point_cloud_path))[0]
        mesh_name = f"{src_stem}_{req.algorithm}_{_uuid_mod.uuid4().hex[:8]}.obj"
        safe_output_path = os.path.join(mesh_dir, mesh_name)

        response = processing_facade.generate_mesh(
            req.point_cloud_path,
            req.polygon,
            safe_output_path,
            algorithm=req.algorithm,
            z_min=req.z_min,
            z_max=req.z_max,
            **req.generator_params,
        )

        if response.success:
            location_id = data.get("location_id", "default")
            description = data.get(
                "description",
                f"Generated from {os.path.basename(req.point_cloud_path)}",
            )
            registered = mesh_store.register(
                filename=mesh_name,
                location_id=location_id,
                description=description,
                algorithm=req.algorithm,
            )
            if registered:
                response.data["mesh_id"] = registered.id
                response.data["mesh_name"] = mesh_name
                response.data["registered"] = True

        return jsonify(response.to_dict())

    # ══════════════════════════════════════════════════════════════════
    # AUTH
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/auth/verify", methods=["POST"])
    def verify_code():
        data = request.get_json(silent=True) or {}
        code = data.get("code", "")
        device_id = data.get("device_id")
        info = access_store.verify(code)
        if not info:
            return jsonify(success=False, error="Invalid access code"), 401
        animal_name = access_store.assign_animal_name(code, device_id)
        return jsonify(success=True, data={
            "role": info["role"],
            "location_id": info["location_id"],
            "description": info.get("description", ""),
            "animal_name": animal_name,
        })

    @app.route("/api/auth/codes", methods=["GET"])
    @require_maintainer
    def list_codes():
        return jsonify(success=True, data=access_store.list_codes())

    @app.route("/api/auth/codes", methods=["POST"])
    @require_maintainer
    def create_code():
        data = request.get_json(silent=True) or {}
        location_id = data.get("location_id", "")
        if not location_id:
            return jsonify(success=False, error="location_id is required"), 400
        role = data.get("role", "user")
        description = data.get("description", "")
        code = access_store.create_code(role, location_id, description)
        return jsonify(success=True, data={"code": code})

    @app.route("/api/auth/codes/<code>", methods=["DELETE"])
    @require_maintainer
    def revoke_code(code):
        if access_store.revoke_code(code):
            return jsonify(success=True)
        return jsonify(success=False, error="Code not found"), 404

    # ══════════════════════════════════════════════════════════════════
    # PUBLIC PREVIEW (no auth required)
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/public/meshes", methods=["GET"])
    def public_list_meshes():
        """List mesh names/ids for read-only preview on the login screen."""
        meshes = mesh_store.list_meshes()
        # Only show public meshes in public endpoint
        public_meshes = [m for m in meshes if getattr(m, "public", False)]
        return jsonify(success=True, data=[
            {"id": m.id, "description": m.description or m.filename, "location_id": m.location_id}
            for m in public_meshes
        ])

    @app.route("/api/public/meshes/<mesh_id>", methods=["GET"])
    def public_download_mesh(mesh_id):
        """Serve mesh file for read-only preview (no auth)."""
        path = mesh_store.filepath_for(mesh_id)
        if not path or not os.path.exists(path):
            return jsonify(success=False, error="Mesh not found"), 404
        return send_file(path, as_attachment=False, max_age=0)

    @app.route("/api/public/meshes/<mesh_id>/metadata", methods=["GET"])
    def public_mesh_metadata(mesh_id):
        """Serve mesh metadata for read-only preview (no auth)."""
        meta = mesh_store.get(mesh_id)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404
        return jsonify(success=True, data=_augment_satellite_geo(meta.to_dict()))

    # ══════════════════════════════════════════════════════════════════
    # MESHES
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/meshes", methods=["GET"])
    @require_auth
    def list_meshes():
        auth = request.auth
        loc_id = auth.get("location_id", "")
        user_id = auth.get("mac") or auth.get("code") or auth.get("description", "user")
        loc = None if auth["role"] == "maintainer" or loc_id == "*" else loc_id
        meshes = mesh_store.list_meshes(location_id=loc)
        # Maintainers see all, others see only public or owned
        if auth["role"] == "maintainer":
            filtered = meshes
        else:
            filtered = [m for m in meshes if getattr(m, "public", False) or getattr(m, "owner", None) == user_id]
        return jsonify(success=True, data=[_augment_satellite_geo(m.to_dict()) for m in filtered])

    @app.route("/api/meshes", methods=["POST"])
    @require_maintainer
    def upload_mesh():
        if "file" not in request.files:
            return jsonify(success=False, error="No file provided"), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify(success=False, error="No file selected"), 400
        allowed = {".obj", ".glb", ".gltf", ".stl", ".ply"}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed:
            return jsonify(success=False,
                           error=f"Unsupported format. Allowed: {allowed}"), 400

        filename = secure_filename(file.filename)
        # Use MAC address if available, else fallback to access code or description
        owner = request.form.get("mac") or request.auth.get("mac") or request.auth.get("code") or request.auth.get("description", "maintainer")
        meta = mesh_store.save_mesh(file, {
            "filename":    filename,
            "location_id": request.form.get("location_id", "default"),
            "description": request.form.get("description", ""),
            "crs":         request.form.get("crs", "EPSG:3794"),
            "center_x":   float(request.form.get("center_x", 0)),
            "center_y":   float(request.form.get("center_y", 0)),
            "center_z":   float(request.form.get("center_z", 0)),
            "unit":        request.form.get("unit", "meters"),
            "algorithm":   request.form.get("algorithm", "poisson"),
            "owner":       owner,
            "public":      False,
        })
        activity_log.log("mesh_upload", owner, {"mesh_id": meta.id, "filename": filename})
        return jsonify(success=True, data=meta.to_dict())

    @app.route("/api/meshes/<mesh_id>/publish", methods=["POST"])
    @require_maintainer
    def publish_mesh(mesh_id):
        meta = mesh_store.update(mesh_id, {"public": True})
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404
        return jsonify(success=True, data=meta.to_dict())

    @app.route("/api/meshes/<mesh_id>", methods=["GET"])
    @require_auth
    def download_mesh(mesh_id):
        path = mesh_store.filepath_for(mesh_id)
        if not path or not os.path.exists(path):
            return jsonify(success=False, error="Mesh not found"), 404
        return send_file(path, as_attachment=False, max_age=0)

    @app.route("/api/meshes/<mesh_id>/metadata", methods=["GET"])
    @require_auth
    def mesh_metadata(mesh_id):
        meta = mesh_store.get(mesh_id)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404
        return jsonify(success=True, data=_augment_satellite_geo(meta.to_dict()))

    @app.route("/api/meshes/<mesh_id>/metadata", methods=["PUT"])
    @require_maintainer
    def update_mesh_metadata(mesh_id):
        data = request.get_json(silent=True) or {}
        meta = mesh_store.update(mesh_id, data)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404
        return jsonify(success=True, data=meta.to_dict())

    # ══════════════════════════════════════════════════════════════════
    # VEHICLES
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/vehicles", methods=["GET"])
    @require_auth
    def list_vehicles():
        return jsonify(success=True, data=get_catalog())

    @app.route("/api/vehicles/<vehicle_id>", methods=["GET"])
    @require_auth
    def vehicle_detail(vehicle_id):
        v = get_vehicle(vehicle_id)
        if not v:
            return jsonify(success=False, error="Vehicle not found"), 404
        return jsonify(success=True, data=v)

    # ══════════════════════════════════════════════════════════════════
    # PLACEMENTS
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/meshes/<mesh_id>/placements", methods=["GET"])
    @require_auth
    def list_placements(mesh_id):
        # Only return vehicles whose departure is in the future
        placements = placement_store.list_for_mesh_filtered(mesh_id)
        return jsonify(success=True, data=[p.to_dict() for p in placements])

    @app.route("/api/meshes/<mesh_id>/placements", methods=["POST"])
    @require_auth
    def commit_placement(mesh_id):
        meta = mesh_store.get(mesh_id)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404

        data = request.get_json(silent=True) or {}
        data["mesh_id"] = mesh_id
        data["placed_by"] = request.auth.get("description", "")

        # Validate required numeric fields
        for field in ("x", "y", "z", "length", "width", "height"):
            if field not in data:
                return jsonify(
                    success=False,
                    error=f"Missing required field: {field}"
                ), 400
            try:
                float(data[field])
            except (TypeError, ValueError):
                return jsonify(
                    success=False,
                    error=f"Invalid numeric value for {field}"
                ), 400

        placement, error = placement_store.commit(data)
        if error:
            return jsonify(success=False, error=error), 409
        activity_log.log("placement_commit", request.auth.get("description", ""),
                         {"placement_id": placement.id, "mesh_id": mesh_id,
                          "vehicle_id": data.get("vehicle_id", "")})
        return jsonify(success=True, data=placement.to_dict()), 201

    @app.route("/api/placements/<placement_id>", methods=["PUT"])
    @require_auth
    def update_placement(placement_id):
        existing = placement_store.get(placement_id)
        if not existing:
            return jsonify(success=False, error="Placement not found"), 404
        if request.auth["role"] != "maintainer" and existing.placed_by != request.auth.get("description", ""):
            return jsonify(success=False, error="You can only modify your own placements"), 403
        data = request.get_json(silent=True) or {}
        placement, error = placement_store.update(placement_id, data)
        if error:
            status = 404 if "not found" in error.lower() else 409
            return jsonify(success=False, error=error), status
        activity_log.log("placement_update", request.auth.get("description", ""),
                         {"placement_id": placement_id, "updates": list(data.keys())})
        return jsonify(success=True, data=placement.to_dict())

    @app.route("/api/placements/<placement_id>", methods=["DELETE"])
    @require_auth
    def delete_placement(placement_id):
        existing = placement_store.get(placement_id)
        if not existing:
            return jsonify(success=False, error="Placement not found"), 404
        if request.auth["role"] != "maintainer" and existing.placed_by != request.auth.get("description", ""):
            return jsonify(success=False, error="You can only remove your own placements"), 403
        if placement_store.delete(placement_id):
            activity_log.log("placement_delete", request.auth.get("description", ""),
                             {"placement_id": placement_id})
            return jsonify(success=True)
        return jsonify(success=False, error="Placement not found"), 404

    # ══════════════════════════════════════════════════════════════════
    # MESH PROCESSING (maintainer)
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/meshes/<mesh_id>/process", methods=["POST"])
    @require_maintainer
    def process_mesh(mesh_id):
        meta = mesh_store.get(mesh_id)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404

        filepath = mesh_store.filepath_for(mesh_id)
        if not filepath or not os.path.exists(filepath):
            return jsonify(success=False, error="Mesh file missing"), 404

        data = request.get_json(silent=True) or {}
        fill = data.get("fill_holes", True)
        smooth = data.get("smooth", True)
        iterations = min(int(data.get("smooth_iterations", 5)), 50)
        method = data.get("smooth_method", "laplacian")
        color = data.get("color")
        hole_size = float(data.get("hole_size", 100.0))

        if method not in ("laplacian", "taubin"):
            return jsonify(success=False, error="Invalid smooth method"), 400
        if color and (len(color) != 7 or color[0] != '#'):
            return jsonify(success=False, error="Color must be #RRGGBB"), 400

        try:
            output_path = run_process_mesh(
                input_path=filepath,
                output_path=filepath,  # overwrite in place
                fill=fill,
                smooth=smooth,
                smooth_iterations=iterations,
                smooth_method=method,
                color=color,
                hole_size=hole_size,
            )
            # Update colour in metadata if specified
            if color:
                mesh_store.update(mesh_id, {"color": color})

            return jsonify(success=True, data={
                "message": "Mesh processed successfully",
                "mesh_id": mesh_id,
            })
        except Exception as exc:
            return jsonify(success=False, error=str(exc)), 500

    @app.route("/api/meshes/<mesh_id>/fill-hole", methods=["POST"])
    @require_maintainer
    def fill_hole_click(mesh_id):
        """Manual hole-fill trigger. Called from maintainer click interaction."""
        meta = mesh_store.get(mesh_id)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404

        filepath = mesh_store.filepath_for(mesh_id)
        if not filepath or not os.path.exists(filepath):
            return jsonify(success=False, error="Mesh file missing"), 404

        data = request.get_json(silent=True) or {}
        hole_size = float(data.get("hole_size", 100.0))

        try:
            run_process_mesh(
                input_path=filepath,
                output_path=filepath,
                fill=True,
                smooth=False,
                hole_size=hole_size,
            )
            return jsonify(success=True, data={"message": "Hole filling applied"})
        except Exception as exc:
            return jsonify(success=False, error=str(exc)), 500

    @app.route("/api/meshes/<mesh_id>/color", methods=["PUT"])
    @require_auth
    def set_mesh_color(mesh_id):
        """Update the display colour stored in metadata (no re-processing)."""
        meta = mesh_store.get(mesh_id)
        if not meta:
            return jsonify(success=False, error="Mesh not found"), 404

        data = request.get_json(silent=True) or {}
        color = data.get("color")
        if not color or len(color) != 7 or color[0] != '#':
            return jsonify(success=False, error="Color must be #RRGGBB"), 400

        updated = mesh_store.update(mesh_id, {"color": color})
        return jsonify(success=True, data=updated.to_dict())

    # ══════════════════════════════════════════════════════════════════
    # ACTIVITY LOG (maintainer)
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/activity-log", methods=["GET"])
    @require_maintainer
    def get_activity_log():
        limit = min(int(request.args.get("limit", 200)), 1000)
        action = request.args.get("action")
        entries = activity_log.list(limit=limit, action=action)
        return jsonify(success=True, data=entries)

    # ══════════════════════════════════════════════════════════════════
    # POINT CLOUD MANAGEMENT (maintainer)
    # ══════════════════════════════════════════════════════════════════

    @app.route("/api/point-clouds", methods=["GET"])
    @require_maintainer
    def list_point_clouds():
        """List all uploaded .laz/.las files with metadata."""
        return jsonify(success=True, data=pc_manager.list_uploads())

    @app.route("/api/point-clouds", methods=["POST"])
    @require_maintainer
    def upload_point_cloud_new():
        """Upload a .laz/.las point cloud file."""
        if "file" not in request.files:
            return jsonify(success=False, error="No file provided"), 400
        f = request.files["file"]
        if not f or not f.filename:
            return jsonify(success=False, error="No file selected"), 400
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".laz", ".las"):
            return jsonify(success=False, error="Only .laz and .las files"), 400
        try:
            info = pc_manager.save_upload(f)
            activity_log.log("pointcloud_upload", request.auth.get("description", ""),
                             {"filename": info["filename"]})
            return jsonify(success=True, data=info), 201
        except Exception as exc:
            return jsonify(success=False, error=str(exc)), 500

    @app.route("/api/point-clouds/<filename>/preview", methods=["GET"])
    @require_maintainer
    def preview_point_cloud(filename):
        """Return downsampled point cloud as JSON (positions + optional colours)."""
        path = os.path.join(upload_dir, filename)
        if not os.path.exists(path):
            return jsonify(success=False, error="File not found"), 404
        max_pts = min(int(request.args.get("max_points", 200000)), 500000)
        try:
            data = pc_manager.preview(filename, max_points=max_pts)
            return jsonify(success=True, data=data)
        except Exception as exc:
            return jsonify(success=False, error=str(exc)), 500

    @app.route("/api/point-clouds/<filename>/generate-mesh", methods=["POST"])
    @require_maintainer
    def generate_mesh_from_pc(filename):
        """Generate a mesh from a selected area of the point cloud.

        Expects JSON body: ``bounds_min``, ``bounds_max`` (2-element arrays
        [x, y] in EPSG:3794), ``algorithm`` (optional, default ``poisson``),
        ``color_source`` (optional filename for GKOT colour transfer),
        ``location_id`` / ``description`` for auto-registration.
        """
        path = os.path.join(upload_dir, filename)
        if not os.path.exists(path):
            return jsonify(success=False, error="File not found"), 404

        data = request.get_json(silent=True) or {}
        bmin = data.get("bounds_min")
        bmax = data.get("bounds_max")
        if not bmin or not bmax or len(bmin) < 2 or len(bmax) < 2:
            return jsonify(success=False, error="bounds_min and bounds_max required ([x,y])"), 400

        algo = data.get("algorithm", "poisson")
        if algo not in ("poisson", "bpa"):
            return jsonify(success=False, error="algorithm must be 'poisson' or 'bpa'"), 400

        color_src = data.get("color_source")

        try:
            result = pc_manager.generate_mesh(
                filename,
                bounds_min_2d=bmin,
                bounds_max_2d=bmax,
                algorithm=algo,
                color_source=color_src,
            )
        except ValueError as ve:
            return jsonify(success=False, error=str(ve)), 400
        except Exception as exc:
            return jsonify(success=False, error=str(exc)), 500

        # Auto-register the generated mesh in the mesh store
        meta = result["metadata"]
        location_id = data.get("location_id", "default")
        description = data.get("description", f"Generated from {filename}")

        registered = mesh_store.register(
            filename=meta["filename"],
            location_id=location_id,
            description=description,
            center_x=meta["center_x"],
            center_y=meta["center_y"],
            center_z=meta["center_z"],
            bounds_min=meta["bounds_min"],
            bounds_max=meta["bounds_max"],
            crs=meta["crs"],
            unit=meta["unit"],
            algorithm=meta["algorithm"],
        )

        activity_log.log("mesh_generate", request.auth.get("description", ""), {
            "source": filename,
            "algorithm": algo,
            "mesh_id": registered.id if registered else meta["filename"],
        })

        resp = {**meta}
        if registered:
            resp["mesh_id"] = registered.id
            resp["registered"] = True

        return jsonify(success=True, data=resp), 201

    return app
