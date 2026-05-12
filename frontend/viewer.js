/**
 * SceneViewer — Three.js 3D viewer for terrain meshes and vehicle placement.
 *
 * Coordinates are in meters (1 unit = 1 m, matching EPSG:3794).
 * LiDAR data is Z-up; WebGL is Y-up, so terrain is rotated on load.
 *
 * Vehicle placement features:
 *   - Mouse-follow with terrain raycasting (ground snapping)
 *   - Y-axis rotation via scroll wheel while placing
 *   - Confirmation step before committing
 *   - Overlap checking done server-side
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { CSS2DObject, CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';

export class SceneViewer {
    constructor(container) {
        this.container = container;
        this.terrainMesh = null;
        this.terrainColor = null;
        this.committedVehicles = [];
        this.placingVehicle = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.isPlacing = false;
        this.placingRotationY = 0;
        this.paintMode = false;
        this.holeFillMode = false;
        this.paintStrokes = [];
        this.onPaintStroke = null;
        this.onHoleFillRequest = null;

        // Multi-mesh & multi-point-cloud scene management
        this.loadedMeshes = new Map();         // meshId → { obj, metadata }
        this.loadedPointClouds = new Map();     // filename → { obj, data }

        // Multi-mesh & multi-point-cloud scene management
        this.loadedMeshes = new Map();         // meshId → { obj, metadata }
        this.loadedPointClouds = new Map();     // filename → { obj, data }

        // Callbacks set by App
        this.onRequestConfirm = null;

        this._initRenderer();
        this._initCamera();
        this._initLighting();
        this._initControls();
        this._initGrid();
        this._addScaleBar();
        this._bindEvents();
        this._animate();
    }

    // ── Setup ────────────────────────────────────────────────────────

    _initRenderer() {
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.shadowMap.enabled = true;
        this.container.appendChild(this.renderer.domElement);

        this.labelRenderer = new CSS2DRenderer();
        this.labelRenderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.labelRenderer.domElement.style.position = 'absolute';
        this.labelRenderer.domElement.style.top = '0';
        this.labelRenderer.domElement.style.pointerEvents = 'none';
        this.container.appendChild(this.labelRenderer.domElement);
    }

    _initCamera() {
        const aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 100000);
        this.camera.position.set(0, 100, 200);
    }

    _initLighting() {
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x111122);

        const hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 1.5);
        this.scene.add(hemi);

        const sun = new THREE.DirectionalLight(0xffffff, 1.0);
        sun.position.set(200, 400, 200);
        sun.castShadow = true;
        this.scene.add(sun);
    }

    _initControls() {
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.1;
    }

    _initGrid() {
        this.grid = new THREE.GridHelper(200, 20, 0x444444, 0x333333);
        this.scene.add(this.grid);
    }

    _addScaleBar() {
        const geo = new THREE.BoxGeometry(10, 0.15, 0.15);
        const mat = new THREE.MeshBasicMaterial({ color: 0x667eea });
        this.scaleBar = new THREE.Mesh(geo, mat);
        this.scaleBar.visible = false;
        this.scene.add(this.scaleBar);
    }

    _bindEvents() {
        window.addEventListener('resize', () => this._onResize());
        this.renderer.domElement.addEventListener('mousemove', (e) => this._onMouseMove(e));
        this.renderer.domElement.addEventListener('click', (e) => this._onClick(e));
        this.renderer.domElement.addEventListener('wheel', (e) => this._onWheel(e), { passive: false });
        this.renderer.domElement.addEventListener('contextmenu', (e) => {
            if (this.isPlacing) e.preventDefault();
        });
    }

    // ── Event handlers ───────────────────────────────────────────────

    _onResize() {
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
        this.labelRenderer.setSize(w, h);
    }

    _onMouseMove(e) {
        if (!this.isPlacing || !this.placingVehicle || !this.terrainMesh) return;

        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        const hits = this.raycaster.intersectObject(this.terrainMesh, true);

        if (hits.length > 0) {
            const pt = hits[0].point;
            const halfH = this.placingVehicle.userData.dims.height / 2;
            this.placingVehicle.position.set(pt.x, pt.y + halfH, pt.z);

            // Align to terrain slope using face normal
            const normal = hits[0].face?.normal;
            if (normal) {
                const worldNormal = normal.clone();
                const normalMatrix = new THREE.Matrix3().getNormalMatrix(
                    hits[0].object.matrixWorld
                );
                worldNormal.applyMatrix3(normalMatrix).normalize();

                const up = new THREE.Vector3(0, 1, 0);
                const qSlope = new THREE.Quaternion().setFromUnitVectors(up, worldNormal);
                const qYaw = new THREE.Quaternion().setFromAxisAngle(up, this.placingRotationY);
                this.placingVehicle.quaternion.copy(qSlope).multiply(qYaw);
            }
        }
    }

    _onWheel(e) {
        if (!this.isPlacing || !this.placingVehicle) return;
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.1 : -0.1;
        this.placingRotationY += delta;
        this.placingVehicle.rotation.y = this.placingRotationY;
    }

    _onClick(e) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);

        // Area selection mode – intersect point cloud
        if (this._areaSelectMode && this.pointCloudObj) {
            this.raycaster.params.Points = { threshold: 0.5 };
            const pcHits = this.raycaster.intersectObject(this.pointCloudObj, false);
            if (pcHits.length > 0) {
                this._handleAreaSelectClick(pcHits[0].point);
            }
            return;
        }

        const hits = this.raycaster.intersectObject(this.terrainMesh, true);

        if (hits.length === 0) return;

        if (this.paintMode) {
            this._paintAtHit(hits[0]);
            return;
        }

        if (this.holeFillMode) {
            const point = hits[0].point;
            if (this.onHoleFillRequest) {
                this.onHoleFillRequest({ x: point.x, y: point.y, z: point.z });
            }
            this.holeFillMode = false;
            return;
        }

        if (!this.isPlacing || !this.placingVehicle) return;

        // Pause placement and request confirmation from app
        if (this.onRequestConfirm) {
            const pos = this.placingVehicle.position.clone();
            this.isPlacing = false;
            this.onRequestConfirm({
                x: pos.x,
                y: pos.y,
                z: pos.z,
                rotation_y: this.placingRotationY,
                dims: { ...this.placingVehicle.userData.dims },
                color: this.placingVehicle.userData.color,
                vehicle_id: this.placingVehicle.userData.vehicle_id,
                vehicle_name: this.placingVehicle.userData.vehicle_name || '',
            });
        }
    }

    // ── Terrain loading ──────────────────────────────────────────────

    loadTerrainFromOBJ(objText, metadata) {
        if (this.terrainMesh) this.scene.remove(this.terrainMesh);
        this.terrainMetadata = metadata || null;

        const loader = new OBJLoader();
        const obj = loader.parse(objText);

        obj.rotation.x = -Math.PI / 2;

        if (metadata) {
            obj.position.set(
                metadata.offset_x || 0,
                metadata.offset_y || 0,
                metadata.offset_z || 0,
            );
            if (metadata.rotation_y) {
                obj.rotation.y = metadata.rotation_y;
            }
        }

        const meshColor = (metadata && metadata.color)
            ? new THREE.Color(metadata.color)
            : new THREE.Color(0xffffff);
        this.terrainColor = metadata?.color || null;
        this.paintStrokes = Array.isArray(metadata?.paint_strokes) ? [...metadata.paint_strokes] : [];

        // Check if OBJ already has vertex colours (from GKOT real-world colours)
        let hasExistingColors = false;
        obj.traverse(child => {
            if (child.isMesh && child.geometry.getAttribute('color')) {
                hasExistingColors = true;
            }
        });

        obj.traverse(child => {
            if (child.isMesh) {
                const geometry = child.geometry;
                if (!geometry.getAttribute('color')) {
                    // No vertex colours — fill with the mesh display colour
                    const pos = geometry.getAttribute('position');
                    const colors = new Float32Array(pos.count * 3);
                    for (let i = 0; i < pos.count; i++) {
                        colors[i * 3] = meshColor.r;
                        colors[i * 3 + 1] = meshColor.g;
                        colors[i * 3 + 2] = meshColor.b;
                    }
                    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
                }
                child.material = new THREE.MeshStandardMaterial({
                    color: hasExistingColors ? 0xffffff : meshColor,
                    vertexColors: true,
                    side: THREE.DoubleSide,
                    roughness: 0.5,
                });
                child.receiveShadow = true;
            }
        });

        this.terrainMesh = obj;
        this.scene.add(obj);
        for (const stroke of this.paintStrokes) {
            this.applyPaintStroke(stroke, false);
        }
        this._fitCamera();

        if (this.grid) {
            this.scene.remove(this.grid);
            this.grid = null;
        }
        this._positionScaleBar();
    }

    /** Check if the current terrain has original vertex colours from point cloud. */
    hasVertexColors() {
        if (!this.terrainMesh) return false;
        let found = false;
        this.terrainMesh.traverse(child => {
            if (child.isMesh && child.geometry.getAttribute('color')) found = true;
        });
        return found;
    }

    /** Switch material to show the original point-cloud vertex RGB colours. */
    applyVertexColorOverlay() {
        if (!this.terrainMesh) return;
        this.terrainMesh.traverse(child => {
            if (!child.isMesh) return;
            child.material = new THREE.MeshStandardMaterial({
                color: 0xffffff,
                vertexColors: true,
                side: THREE.DoubleSide,
                roughness: 0.5,
            });
            child.material.needsUpdate = true;
        });
    }

    /** Restore mesh to its solid display colour (no vertex colours). */
    removeSatelliteTexture() {
        if (!this.terrainMesh) return;
        const c = new THREE.Color(this.terrainColor || '#ffffff');
        this.terrainMesh.traverse(child => {
            if (!child.isMesh) return;
            const geo = child.geometry;
            const pos = geo.getAttribute('position');
            const colors = new Float32Array(pos.count * 3);
            for (let i = 0; i < pos.count; i++) {
                colors[i * 3] = c.r;
                colors[i * 3 + 1] = c.g;
                colors[i * 3 + 2] = c.b;
            }
            geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            child.material = new THREE.MeshStandardMaterial({
                color: c,
                vertexColors: true,
                side: THREE.DoubleSide,
                roughness: 0.5,
            });
        });
    }

    setTerrainColor(hexColor) {
        if (!this.terrainMesh) return;
        this.terrainColor = hexColor;
        const c = new THREE.Color(hexColor);
        this.terrainMesh.traverse(child => {
            if (!child.isMesh) return;
            child.material.color.copy(c);
            const colorAttr = child.geometry.getAttribute('color');
            if (colorAttr) {
                for (let i = 0; i < colorAttr.count; i++) {
                    colorAttr.setXYZ(i, c.r, c.g, c.b);
                }
                colorAttr.needsUpdate = true;
            }
        });
    }

    // ── Multi-mesh management (add/remove from viewer) ───────────────

    /**
     * Add a mesh to the scene by its ID. Loads OBJ text and metadata,
     * stores it in `loadedMeshes`. Also selects it as the active terrain
     * for raycasting (placement, paint, etc.).
     */
    addMeshToScene(meshId, objText, metadata) {
        if (this.loadedMeshes.has(meshId)) return; // already shown

        const loader = new OBJLoader();
        const obj = loader.parse(objText);
        obj.rotation.x = -Math.PI / 2;

        if (metadata) {
            obj.position.set(
                metadata.offset_x || 0,
                metadata.offset_y || 0,
                metadata.offset_z || 0,
            );
            if (metadata.rotation_y) obj.rotation.y = metadata.rotation_y;
        }

        const meshColor = metadata?.color
            ? new THREE.Color(metadata.color) : new THREE.Color(0xffffff);

        let hasExistingColors = false;
        obj.traverse(child => {
            if (child.isMesh && child.geometry.getAttribute('color'))
                hasExistingColors = true;
        });
        obj.traverse(child => {
            if (!child.isMesh) return;
            const geo = child.geometry;
            if (!geo.getAttribute('color')) {
                const pos = geo.getAttribute('position');
                const colors = new Float32Array(pos.count * 3);
                for (let i = 0; i < pos.count; i++) {
                    colors[i * 3] = meshColor.r;
                    colors[i * 3 + 1] = meshColor.g;
                    colors[i * 3 + 2] = meshColor.b;
                }
                geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            }
            child.material = new THREE.MeshStandardMaterial({
                color: hasExistingColors ? 0xffffff : meshColor,
                vertexColors: true,
                side: THREE.DoubleSide,
                roughness: 0.5,
            });
            child.receiveShadow = true;
        });

        this.scene.add(obj);
        this.loadedMeshes.set(meshId, { obj, metadata });

        // Make this the active terrain for interactions
        this.terrainMesh = obj;
        this.terrainMetadata = metadata || null;
        this.terrainColor = metadata?.color || null;
        this.paintStrokes = Array.isArray(metadata?.paint_strokes) ? [...metadata.paint_strokes] : [];
        for (const stroke of this.paintStrokes) {
            this.applyPaintStroke(stroke, false);
        }
        this._fitCamera();
        if (this.grid) { this.scene.remove(this.grid); this.grid = null; }
        this._positionScaleBar();
    }

    /**
     * Remove a mesh from the scene viewer (does NOT delete from backend).
     */
    removeMeshFromScene(meshId) {
        const entry = this.loadedMeshes.get(meshId);
        if (!entry) return;
        this.scene.remove(entry.obj);
        this.loadedMeshes.delete(meshId);

        // If this was the active terrain, pick another or clear
        if (this.terrainMesh === entry.obj) {
            if (this.loadedMeshes.size > 0) {
                const [, last] = [...this.loadedMeshes.entries()].pop();
                this.terrainMesh = last.obj;
                this.terrainMetadata = last.metadata;
            } else {
                this.terrainMesh = null;
                this.terrainMetadata = null;
            }
        }
    }

    /** Check if a mesh is currently displayed in the scene. */
    isMeshInScene(meshId) {
        return this.loadedMeshes.has(meshId);
    }

    // ── Multi-point-cloud management ─────────────────────────────────

    /**
     * Add a point cloud to the scene by filename.
     * `data` has the same shape as loadPointCloud expects.
     */
    addPointCloudToScene(filename, data) {
        if (this.loadedPointClouds.has(filename)) return;

        const posArr = new Float32Array(data.positions);
        const count = posArr.length / 3;
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(posArr, 3));

        // Rotate Z-up → Y-up
        const rotatedPos = geometry.getAttribute('position');
        for (let i = 0; i < count; i++) {
            const y = rotatedPos.getY(i);
            const z = rotatedPos.getZ(i);
            rotatedPos.setY(i, z);
            rotatedPos.setZ(i, -y);
        }
        rotatedPos.needsUpdate = true;

        let material;
        if (data.colors && data.colors.length === posArr.length) {
            const colArr = new Float32Array(data.colors);
            geometry.setAttribute('color', new THREE.BufferAttribute(colArr, 3));
            material = new THREE.PointsMaterial({ size: 0.3, vertexColors: true, sizeAttenuation: true });
        } else {
            material = new THREE.PointsMaterial({ size: 0.3, color: 0x88aaff, sizeAttenuation: true });
        }

        const points = new THREE.Points(geometry, material);
        this.scene.add(points);
        this.loadedPointClouds.set(filename, { obj: points, data });

        // Keep backward compat: set as current point cloud for area selection
        this.pointCloudObj = points;
        this.pointCloudData = data;

        // Fit camera
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        this.controls.target.copy(center);
        this.camera.position.set(center.x + maxDim * 0.5, center.y + maxDim * 0.7, center.z + maxDim * 0.5);
        this.camera.lookAt(center);
        if (this.grid) { this.scene.remove(this.grid); this.grid = null; }
    }

    /**
     * Remove a point cloud from the viewer (does NOT delete from backend).
     */
    removePointCloudFromScene(filename) {
        const entry = this.loadedPointClouds.get(filename);
        if (!entry) return;
        this.scene.remove(entry.obj);
        this.loadedPointClouds.delete(filename);

        // Update backward-compat references
        if (this.pointCloudObj === entry.obj) {
            if (this.loadedPointClouds.size > 0) {
                const [, last] = [...this.loadedPointClouds.entries()].pop();
                this.pointCloudObj = last.obj;
                this.pointCloudData = last.data;
            } else {
                this.pointCloudObj = null;
                this.pointCloudData = null;
            }
            this.clearSelectionBox();
        }
    }

    /** Check if a point cloud is currently displayed. */
    isPointCloudInScene(filename) {
        return this.loadedPointClouds.has(filename);
    }

    enablePaintMode(enabled, options = {}) {
        this.paintMode = enabled;
        if (enabled) {
            this.holeFillMode = false;
            this.controls.enabled = true;
            this.paintColor = options.color || '#ff7f50';
            this.paintRadius = Number(options.radius || 2.5);
            this.onPaintStroke = options.onStroke || null;
        }
    }

    enableHoleFillMode(enabled, callback = null) {
        this.holeFillMode = enabled;
        if (enabled) {
            this.paintMode = false;
            this.onHoleFillRequest = callback;
        }
    }

    applyPaintStroke(stroke, track = true) {
        if (!this.terrainMesh || !stroke) return;
        const color = stroke.color || '#ff7f50';
        const radius = Number(stroke.radius || 2.5);
        const centerWorld = new THREE.Vector3(stroke.x, stroke.y, stroke.z);

        this.terrainMesh.traverse(child => {
            if (!child.isMesh) return;
            const geom = child.geometry;
            const pos = geom.getAttribute('position');
            const cols = geom.getAttribute('color');
            if (!pos || !cols) return;

            const centerLocal = child.worldToLocal(centerWorld.clone());
            const brush = new THREE.Color(color);

            for (let i = 0; i < pos.count; i++) {
                const vx = pos.getX(i);
                const vy = pos.getY(i);
                const vz = pos.getZ(i);
                const d2 = (vx - centerLocal.x) ** 2 + (vy - centerLocal.y) ** 2 + (vz - centerLocal.z) ** 2;
                if (d2 <= radius * radius) {
                    cols.setXYZ(i, brush.r, brush.g, brush.b);
                }
            }
            cols.needsUpdate = true;
        });

        if (track) this.paintStrokes.push(stroke);
    }

    _paintAtHit(hit) {
        const point = hit.point;
        const stroke = {
            x: point.x,
            y: point.y,
            z: point.z,
            color: this.paintColor || '#ff7f50',
            radius: this.paintRadius || 2.5,
        };
        this.applyPaintStroke(stroke, true);
        if (this.onPaintStroke) this.onPaintStroke(stroke);
    }

    clearPaint() {
        this.paintStrokes = [];
        if (!this.terrainMesh) return;
        const baseColor = new THREE.Color(this.terrainColor || '#ffffff');
        this.terrainMesh.traverse(child => {
            if (!child.isMesh) return;
            const cols = child.geometry.getAttribute('color');
            if (!cols) return;
            for (let i = 0; i < cols.count; i++) {
                cols.setXYZ(i, baseColor.r, baseColor.g, baseColor.b);
            }
            cols.needsUpdate = true;
        });
    }

    getPaintStrokes() {
        return [...this.paintStrokes];
    }

    _fitCamera() {
        const box = new THREE.Box3().setFromObject(this.terrainMesh);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);

        this.controls.target.copy(center);
        this.camera.position.set(
            center.x + maxDim * 0.5,
            center.y + maxDim * 0.7,
            center.z + maxDim * 0.5,
        );
        this.camera.lookAt(center);
    }

    _positionScaleBar() {
        if (!this.terrainMesh) return;
        const box = new THREE.Box3().setFromObject(this.terrainMesh);
        const min = box.min;
        this.scaleBar.position.set(min.x + 5, min.y - 1, min.z - 3);
        this.scaleBar.visible = true;
    }

    // ── Terrain corrections (maintainer) ─────────────────────────────

    setTerrainOffset(x, y, z) {
        if (!this.terrainMesh) return;
        this.terrainMesh.position.set(x, y, z);
    }

    setTerrainRotationY(rad) {
        if (!this.terrainMesh) return;
        this.terrainMesh.rotation.y = rad;
    }

    // ── Vehicle placement flow ───────────────────────────────────────

    startPlacingVehicle(dims, color, vehicleId, vehicleName = '') {
        const geometry = new THREE.BoxGeometry(dims.width, dims.height, dims.length);
        const material = new THREE.MeshStandardMaterial({
            color: new THREE.Color(color),
            transparent: true,
            opacity: 0.6,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.userData.dims = dims;
        mesh.userData.color = color;
        mesh.userData.vehicle_id = vehicleId || 'custom';
        mesh.userData.vehicle_name = vehicleName || '';

        if (this.placingVehicle) this.scene.remove(this.placingVehicle);
        this.placingVehicle = mesh;
        this.placingRotationY = 0;
        this.scene.add(mesh);

        this.isPlacing = true;
        this.controls.enabled = false;
    }

    confirmPlacement(placementData) {
        if (!this.placingVehicle) return;
        this.placingVehicle.material.opacity = 1.0;
        this.placingVehicle.material.transparent = false;
        this.placingVehicle.userData.placementId = placementData.id;
        this._attachVehicleLabel(
            this.placingVehicle,
            placementData.vehicle_name || this.placingVehicle.userData.vehicle_name || this.placingVehicle.userData.vehicle_id,
            this.placingVehicle.userData.dims.height,
        );
        this.committedVehicles.push(this.placingVehicle);
        this.placingVehicle = null;
        this.controls.enabled = true;
    }

    cancelPlacing() {
        if (this.placingVehicle) {
            this.scene.remove(this.placingVehicle);
            this.placingVehicle = null;
        }
        this.isPlacing = false;
        this.controls.enabled = true;
    }

    resumePlacing() {
        if (this.placingVehicle) {
            this.isPlacing = true;
            this.controls.enabled = false;
        }
    }

    // ── Rendering committed vehicles from server ─────────────────────

    clearCommittedVehicles() {
        for (const v of this.committedVehicles) {
            this._disposeVehicleLabels(v);
            this.scene.remove(v);
        }
        this.committedVehicles = [];
    }

    addCommittedVehicle(placement) {
        const geometry = new THREE.BoxGeometry(
            placement.width, placement.height, placement.length
        );
        const material = new THREE.MeshStandardMaterial({
            color: new THREE.Color(placement.color || '#3498db'),
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(placement.x, placement.y, placement.z);
        mesh.rotation.y = placement.rotation_y || 0;
        mesh.castShadow = true;
        mesh.userData.placementId = placement.id;
        mesh.userData.dims = {
            length: placement.length,
            width: placement.width,
            height: placement.height,
        };
        let labelText = placement.vehicle_name || placement.vehicle_id || 'vehicle';
        if (placement.departure_date) {
            labelText += `\n🕐 ${placement.departure_date}`;
        }
        this._attachVehicleLabel(mesh, labelText, placement.height);
        this.committedVehicles.push(mesh);
        this.scene.add(mesh);
    }

    _attachVehicleLabel(mesh, text, height) {
        const labelEl = document.createElement('div');
        labelEl.className = 'vehicle-label';
        labelEl.textContent = text;
        const label = new CSS2DObject(labelEl);
        label.position.set(0, height / 2 + 0.8, 0);
        mesh.add(label);
    }

    removeCommittedVehicle(placementId) {
        const idx = this.committedVehicles.findIndex(
            v => v.userData.placementId === placementId
        );
        if (idx !== -1) {
            this._disposeVehicleLabels(this.committedVehicles[idx]);
            this.scene.remove(this.committedVehicles[idx]);
            this.committedVehicles.splice(idx, 1);
        }
    }

    _disposeVehicleLabels(mesh) {
        mesh.traverse(child => {
            if (child.isCSS2DObject && child.element) {
                child.element.remove();
            }
        });
    }

    // ── Export ────────────────────────────────────────────────────────

    exportScene() {
        const exporter = new GLTFExporter();
        exporter.parse(
            this.scene,
            (gltf) => {
                const blob = new Blob([JSON.stringify(gltf)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'scene.gltf';
                a.click();
                URL.revokeObjectURL(url);
            },
            (err) => console.error('Export error', err),
            { binary: false },
        );
    }

    // ── Point Cloud preview ─────────────────────────────────────────

    loadPointCloud(data) {
        /**
         * Render a point cloud preview in the scene.
         * data.positions = flat Float32 [x,y,z, x,y,z, ...]
         * data.colors    = flat Float32 [r,g,b, ...] (optional, 0–1)
         * data.center    = [cx, cy, cz] (EPSG:3794 origin for mesh gen)
         * data.bounds_min / bounds_max  = real-world bounds
         */
        this.clearPointCloud();

        const posArr = new Float32Array(data.positions);
        const count = posArr.length / 3;

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(posArr, 3));

        // Rotate LiDAR Z-up to WebGL Y-up (same as mesh loading)
        const rotatedPos = geometry.getAttribute('position');
        for (let i = 0; i < count; i++) {
            const y = rotatedPos.getY(i);
            const z = rotatedPos.getZ(i);
            rotatedPos.setY(i, z);
            rotatedPos.setZ(i, -y);
        }
        rotatedPos.needsUpdate = true;

        let material;
        if (data.colors && data.colors.length === posArr.length) {
            const colArr = new Float32Array(data.colors);
            geometry.setAttribute('color', new THREE.BufferAttribute(colArr, 3));
            material = new THREE.PointsMaterial({
                size: 0.3,
                vertexColors: true,
                sizeAttenuation: true,
            });
        } else {
            material = new THREE.PointsMaterial({
                size: 0.3,
                color: 0x88aaff,
                sizeAttenuation: true,
            });
        }

        const points = new THREE.Points(geometry, material);
        this.pointCloudObj = points;
        this.pointCloudData = data;
        this.scene.add(points);

        // Fit camera
        geometry.computeBoundingBox();
        const box = geometry.boundingBox;
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        this.controls.target.copy(center);
        this.camera.position.set(
            center.x + maxDim * 0.5,
            center.y + maxDim * 0.7,
            center.z + maxDim * 0.5,
        );
        this.camera.lookAt(center);

        if (this.grid) {
            this.scene.remove(this.grid);
            this.grid = null;
        }
    }

    clearPointCloud() {
        if (this.pointCloudObj) {
            this.scene.remove(this.pointCloudObj);
            this.pointCloudObj = null;
        }
        this.pointCloudData = null;
        this.clearSelectionBox();
    }

    // ── Area selection on point cloud ────────────────────────────────

    startAreaSelection(onComplete) {
        /**
         * Enter area-selection mode: user clicks two corners.
         * onComplete(bounds_min_2d, bounds_max_2d) called with EPSG:3794 coords.
         */
        this._areaSelectCorners = [];
        this._areaSelectCB = onComplete;
        this._areaSelectMode = true;
        this.controls.enabled = true;
    }

    cancelAreaSelection() {
        this._areaSelectMode = false;
        this._areaSelectCorners = [];
        this._areaSelectCB = null;
    }

    _handleAreaSelectClick(point) {
        this._areaSelectCorners.push(point.clone());
        this._addCornerMarker(point);

        if (this._areaSelectCorners.length === 2) {
            const p1 = this._areaSelectCorners[0];
            const p2 = this._areaSelectCorners[1];

            // Show selection box
            this._drawSelectionBox(p1, p2);

            // Convert back from viewer coords (Y-up) to EPSG:3794 (Z-up)
            // In viewer: rotated by -PI/2 around X → y_viewer = z_real, z_viewer = -y_real
            // So: x_real = x_viewer, y_real = -z_viewer (north), z_real = y_viewer
            const pcData = this.pointCloudData;
            if (pcData && pcData.center) {
                const cx = pcData.center[0], cy = pcData.center[1];
                const realX1 = p1.x + cx, realY1 = -p1.z + cy;
                const realX2 = p2.x + cx, realY2 = -p2.z + cy;
                const bmin = [Math.min(realX1, realX2), Math.min(realY1, realY2)];
                const bmax = [Math.max(realX1, realX2), Math.max(realY1, realY2)];
                if (this._areaSelectCB) this._areaSelectCB(bmin, bmax);
            }

            this._areaSelectMode = false;
            this._areaSelectCorners = [];
            this._areaSelectCB = null;
        }
    }

    _addCornerMarker(pos) {
        const geo = new THREE.SphereGeometry(0.4, 8, 8);
        const mat = new THREE.MeshBasicMaterial({ color: 0xff4444 });
        const m = new THREE.Mesh(geo, mat);
        m.position.copy(pos);
        m.userData._selectionMarker = true;
        this.scene.add(m);
    }

    _drawSelectionBox(p1, p2) {
        this.clearSelectionBox();
        const minX = Math.min(p1.x, p2.x), maxX = Math.max(p1.x, p2.x);
        const minZ = Math.min(p1.z, p2.z), maxZ = Math.max(p1.z, p2.z);
        const minY = Math.min(p1.y, p2.y) - 1;
        const maxY = Math.max(p1.y, p2.y) + 5;

        const sx = maxX - minX, sy = maxY - minY, sz = maxZ - minZ;
        const geo = new THREE.BoxGeometry(sx, sy, sz);
        const mat = new THREE.MeshBasicMaterial({
            color: 0x667eea,
            transparent: true,
            opacity: 0.15,
            wireframe: false,
        });
        const box = new THREE.Mesh(geo, mat);
        box.position.set(minX + sx / 2, minY + sy / 2, minZ + sz / 2);
        box.userData._selectionBox = true;
        this.scene.add(box);

        // Wire frame edges
        const edges = new THREE.EdgesGeometry(geo);
        const wire = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x667eea }));
        wire.position.copy(box.position);
        wire.userData._selectionBox = true;
        this.scene.add(wire);
    }

    showSelectionBox(bmin2d, bmax2d) {
        /**
         * Show a selection box from EPSG:3794 bounds (for manual input).
         * Requires pointCloudData to be loaded.
         */
        if (!this.pointCloudData || !this.pointCloudData.center) return;
        const [cx, cy] = this.pointCloudData.center;
        // Convert EPSG:3794 → viewer coords (centered, Y-up)
        const vx1 = bmin2d[0] - cx, vz1 = -(bmin2d[1] - cy);
        const vx2 = bmax2d[0] - cx, vz2 = -(bmax2d[1] - cy);
        const p1 = new THREE.Vector3(vx1, 0, vz1);
        const p2 = new THREE.Vector3(vx2, 0, vz2);
        this._drawSelectionBox(p1, p2);
    }

    clearSelectionBox() {
        const toRemove = [];
        this.scene.traverse(c => {
            if (c.userData._selectionBox || c.userData._selectionMarker) toRemove.push(c);
        });
        toRemove.forEach(c => this.scene.remove(c));
    }

    // ── Render loop ──────────────────────────────────────────────────

    _animate() {
        requestAnimationFrame(() => this._animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
        this.labelRenderer.render(this.scene, this.camera);
    }
}
