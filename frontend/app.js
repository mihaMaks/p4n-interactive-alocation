/**
 * App — main controller for the P4NA Location viewer.
 *
 * Handles authentication, mesh management, vehicle placement with
 * server-side commit and overlap detection, mesh processing, and
 * maintainer corrections.
 */
import { SceneViewer } from './viewer.js';

const POLL_INTERVAL = 5000; // ms between placement refreshes
const MESH_REFRESH_INTERVAL = 10000;

class App {
    constructor() {
        this.accessCode = '';
        this.role = '';
        this.locationId = '';
        this.viewer = null;
        this.meshes = [];
        this.vehicles = [];
        this.currentMeshId = null;
        this.currentMeta = null;
        this._pollTimer = null;
        this._meshRefreshTimer = null;
        this._pendingPaintStrokes = [];
        this.map = null;
        this.mapDrawnLayer = null;
        this.mapPolygon = null;
        this.mapPointCloudPath = null;
        this.mapExtractResult = null;
        this.forumMessages = [];
        this._bindLogin();
        this._loadPreviewMeshes();
    }

    // ══════════════════════════════════════════════════════════════════
    // Authentication
    // ══════════════════════════════════════════════════════════════════

    _bindLogin() {
        const btn = document.getElementById('login-btn');
        const input = document.getElementById('access-code-input');
        btn.addEventListener('click', () => this._login());
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') this._login(); });
    }

    async _loadPreviewMeshes() {
        try {
            const res = await fetch('/api/public/meshes');
            const data = await res.json();
            const list = document.getElementById('preview-mesh-list');
            if (!data.success || !data.data.length) {
                list.innerHTML = '<p class="hint">No meshes available</p>';
                return;
            }
            list.innerHTML = data.data.map(m =>
                `<button class="preview-mesh-btn" data-id="${m.id}">${this._esc(m.description)} <small style="color:#888">${this._esc(m.location_id)}</small></button>`
            ).join('');
            list.querySelectorAll('.preview-mesh-btn').forEach(btn => {
                btn.addEventListener('click', () => this._openPreview(btn.dataset.id));
            });
        } catch {
            const list = document.getElementById('preview-mesh-list');
            if (list) list.innerHTML = '<p class="hint">Could not load meshes</p>';
        }
    }

    _openPreview(meshId) {
        document.getElementById('login-screen').style.display = 'none';
        const app = document.getElementById('app');
        app.style.display = 'flex';

        document.getElementById('role-badge').textContent = 'PREVIEW';
        document.getElementById('role-badge').className = 'badge badge-user';
        document.getElementById('location-label').textContent = 'Read-only';

        // Hide all sidebar panels except mesh info
        document.querySelectorAll('#sidebar .panel').forEach(p => p.style.display = 'none');
        document.getElementById('mesh-info-panel').style.display = 'block';

        document.getElementById('logout-btn').addEventListener('click', () => location.reload());

        this.viewer = new SceneViewer(document.getElementById('viewer-container'));
        this._previewMode = true;
        this._loadPreviewMesh(meshId);
    }

    async _loadPreviewMesh(meshId) {
        try {
            let meta = {};
            try {
                const metaRes = await fetch(`/api/public/meshes/${meshId}/metadata`);
                const metaData = await metaRes.json();
                if (metaData.success) meta = metaData.data;
            } catch { /* fallback */ }

            this._showMeshInfo(meta);

            const res = await fetch(`/api/public/meshes/${meshId}`);
            const text = await res.text();
            this.viewer.loadTerrainFromOBJ(text, meta);

            // Auto-apply vertex RGB colours if available
            if (this.viewer.hasVertexColors()) {
                this.viewer.applyVertexColorOverlay();
            }
        } catch {
            document.getElementById('mesh-info').innerHTML = '<p class="hint">Failed to load mesh</p>';
        }
    }

    async _login() {
        const code = document.getElementById('access-code-input').value.trim();
        if (!code) return;

        // Generate a persistent device ID on first use
        let deviceId = localStorage.getItem('device_id');
        if (!deviceId) {
            deviceId = crypto.randomUUID();
            localStorage.setItem('device_id', deviceId);
        }
        this.deviceId = deviceId;

        try {
            const res = await fetch('/api/auth/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, device_id: deviceId }),
            });
            const data = await res.json();
            if (!data.success) {
                this._loginError(data.error || 'Invalid code');
                return;
            }
            this.accessCode = code;
            this.role = data.data.role;
            this.locationId = data.data.location_id;
            this.userDescription = data.data.description || '';
            this.animalName = data.data.animal_name || '';
            this._enterApp();
        } catch {
            this._loginError('Cannot reach server');
        }
    }

    _loginError(msg) {
        const el = document.getElementById('login-error');
        el.textContent = msg;
        el.style.display = 'block';
    }

    // ══════════════════════════════════════════════════════════════════
    // App initialisation
    // ══════════════════════════════════════════════════════════════════

    _enterApp() {
        document.getElementById('login-screen').style.display = 'none';
        const app = document.getElementById('app');
        app.style.display = 'flex';

        const badge = document.getElementById('role-badge');
        badge.textContent = this.role.toUpperCase();
        badge.className = `badge badge-${this.role}`;

        document.getElementById('location-label').textContent =
            this.locationId === '*' ? 'All Locations' : this.locationId;

        if (this.role === 'maintainer') {
            document.getElementById('maintainer-section').style.display = 'block';
            document.getElementById('maintainer-mesh-controls').style.display = 'block';
            document.getElementById('process-section').style.display = 'block';
            document.getElementById('paint-section').style.display = 'block';
            document.getElementById('log-section').style.display = 'block';
            document.getElementById('open-map-btn').style.display = 'block';
        } else {
            // Regular users: only mesh list, vehicle placement, and mesh info
            document.getElementById('mesh-appearance-panel').style.display = 'none';
        }

        this.viewer = new SceneViewer(document.getElementById('viewer-container'));

        // Wire up the confirmation flow
        this.viewer.onRequestConfirm = (info) => this._showConfirmDialog(info);

        this._bindAppEvents();
        this._loadMeshes();
        this._startMeshRefresh();
        this._loadVehicles();
    }

    _api(path, opts = {}) {
        const headers = { 'X-Access-Code': this.accessCode, ...(opts.headers || {}) };
        return fetch(path, { ...opts, headers });
    }
    // ══════════════════════════════════════════════════════════════════
    // Messages
    // ══════════════════════════════════════════════════════════════════

    async _loadForumMessages() {
        try {
            const res = await this._api('/api/forum/messages');
            const data = await res.json();
            if (data.success) {
                this.forumMessages = data.data;
                this._renderForumMessages();
            }
        } catch (err) {
            console.error('Failed to load forum messages', err);
        }
    }

    _renderForumMessages() {
        const container = document.getElementById('forum-messages');
        if (!container) return;

        if (!this.forumMessages.length) {
            container.innerHTML = '<p class="hint">No messages yet</p>';
            return;
        }

        container.innerHTML = this.forumMessages.map(m => {
            const time = m.ts ? new Date(m.ts).toLocaleString() : '';
            const isOwn = m.animal_name === this.animalName;
            return `
            <div class="forum-msg${isOwn ? ' forum-msg--own' : ''}">
                <div class="forum-msg-header">
                    <strong>${this._esc(m.animal_name)}</strong>
                    <small>${this._esc(time)}</small>
                </div>
                <div class="forum-msg-body">${this._esc(m.text)}</div>
            </div>`;
        }).join('');

        container.scrollTop = container.scrollHeight;
    }

    async _sendForumMessage() {
        const input = document.getElementById('forum-input');
        const text = input?.value?.trim();
        if (!text) return;

        const msg = {
            animal_name: this.animalName || 'Anonymous',
            text,
            ts: new Date().toISOString(),
        };

        try {
            const res = await this._api('/api/forum/messages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(msg),
            });
            const data = await res.json();
            if (data.success) {
                input.value = '';
                await this._loadForumMessages();
            } else {
                this._toast(data.error || 'Failed to send message', 'error');
            }
        } catch {
            this._toast('Failed to send message', 'error');
        }
    }
    // ══════════════════════════════════════════════════════════════════
    // Mesh list
    // ══════════════════════════════════════════════════════════════════

    async _loadMeshes() {
        try {
            const res = await this._api('/api/meshes');
            const data = await res.json();
            if (data.success) {
                this.meshes = data.data;
                this._renderMeshList();
            }
        } catch (err) {
            console.error('Failed to load meshes', err);
        }
    }

    _renderMeshList() {
        const q = (document.getElementById('mesh-search-input')?.value || '').trim().toLowerCase();
        const filtered = q
            ? this.meshes.filter(m => {
                const blob = `${m.description || ''} ${m.filename || ''} ${m.location_id || ''}`.toLowerCase();
                return blob.includes(q);
            })
            : this.meshes;

        const c = document.getElementById('mesh-list-container');
        if (filtered.length === 0) {
            c.innerHTML = '<p class="hint">No meshes available</p>';
            return;
        }
        const isMaintainer = this.role === 'maintainer';
        c.innerHTML = filtered.map(m => {
            const inScene = this.viewer?.isMeshInScene(m.id);
            const publishBtn = isMaintainer && !m.public
                ? `<button class="btn-publish" data-publish-mesh="${m.id}" title="Make mesh public">🌐 Publish</button>`
                : '';
            const unpublishBtn = isMaintainer && m.public
                ? `<button class="btn-publish" data-unpublish-mesh="${m.id}" title="Unpublish mesh">🔒 Unpublish</button>`
                : '';
            const deleteBtn = isMaintainer
                ? `<button class="btn-publish" data-delete-mesh="${m.id}" title="Delete mesh">🗑 Delete</button>`
                : '';
            const publicLabel = !isMaintainer && m.public
                ? '<span class="mesh-public-label" title="Public mesh">🌐</span>'
                : '';
            return `<div class="mesh-item${inScene ? ' in-scene' : ''}" data-id="${m.id}">
                ${publishBtn}
                ${unpublishBtn}
                ${deleteBtn}
                ${publicLabel}
                <div class="mesh-item-text">
                    <strong>${this._esc(m.description || m.filename)}</strong>
                    <small>${this._esc(m.location_id)} | ${m.algorithm}</small>
                </div>
            </div>`;
        }).join('');

        c.querySelectorAll('.mesh-item .mesh-item-text').forEach(el => {
            el.addEventListener('click', () => this._selectMesh(el.closest('.mesh-item').dataset.id));
        });

        c.querySelectorAll('[data-toggle-mesh]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._toggleMeshInViewer(btn.dataset.toggleMesh);
            });
        });

        c.querySelectorAll('[data-publish-mesh]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const meshId = btn.dataset.publishMesh;
                try {
                    const res = await this._api(`/api/meshes/${meshId}/publish`, { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        this._toast('Mesh published');
                        const mesh = this.meshes.find(m => m.id === meshId);
                        if (mesh) mesh.public = true;
                        this._renderMeshList();
                    } else {
                        this._toast('Failed to publish mesh', 'error');
                    }
                } catch {
                    this._toast('Failed to publish mesh', 'error');
                }
            });
        });

        c.querySelectorAll('[data-unpublish-mesh]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const meshId = btn.dataset.unpublishMesh;
                try {
                    const res = await this._api(`/api/meshes/${meshId}/unpublish`, { method: 'POST' });
                    const data = await res.json();
                    if (data.success) {
                        this._toast('Mesh unpublished');
                        const mesh = this.meshes.find(m => m.id === meshId);
                        if (mesh) mesh.public = false;
                        this._renderMeshList();
                    } else {
                        this._toast('Failed to unpublish mesh', 'error');
                    }
                } catch {
                    this._toast('Failed to unpublish mesh', 'error');
                }
            });
        });

        c.querySelectorAll('[data-delete-mesh]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (!confirm('Delete this mesh permanently?')) return;
                const meshId = btn.dataset.deleteMesh;
                try {
                    const res = await this._api(`/api/meshes/${meshId}`, { method: 'DELETE' });
                    const data = await res.json();
                    if (data.success) {
                        this._toast('Mesh deleted');
                        this.meshes = this.meshes.filter(m => m.id !== meshId);
                        this._renderMeshList();
                    } else {
                        this._toast(data.error || 'Delete failed', 'error');
                    }
                } catch {
                    this._toast('Delete failed', 'error');
                }
            });
        });
    }

    async _toggleMeshInViewer(meshId) {
        if (this.viewer.isMeshInScene(meshId)) {
            this.viewer.removeMeshFromScene(meshId);
            this._renderMeshList();
            this._toast('Mesh removed from viewer');
            return;
        }
        // Load and add to scene
        try {
            const meta = this.meshes.find(m => m.id === meshId);
            let metadata = meta;
            try {
                const metaRes = await this._api(`/api/meshes/${meshId}/metadata`);
                const metaData = await metaRes.json();
                if (metaData.success && metaData.data) metadata = metaData.data;
            } catch { /* use list meta */ }

            const res = await this._api(`/api/meshes/${meshId}`);
            const objText = await res.text();
            this.viewer.addMeshToScene(meshId, objText, metadata);
            this._renderMeshList();
            this._toast('Mesh added to viewer');
        } catch {
            this._toast('Failed to load mesh', 'error');
        }
    }

    async _selectMesh(meshId) {
        this.currentMeshId = meshId;
        const listMeta = this.meshes.find(m => m.id === meshId);
        let meta = listMeta;

        try {
            const metaRes = await this._api(`/api/meshes/${meshId}/metadata`);
            const metaData = await metaRes.json();
            if (metaData.success && metaData.data) {
                meta = metaData.data;
            }
        } catch {
            // Fallback to list metadata if detail fetch fails.
        }

        this.currentMeta = meta;
        this._pendingPaintStrokes = [...(meta?.paint_strokes || [])];

        document.querySelectorAll('.mesh-item').forEach(el => el.classList.remove('selected'));
        document.querySelector(`.mesh-item[data-id="${meshId}"]`)?.classList.add('selected');

        this._showMeshInfo(meta);

        // Set colour picker to current mesh colour
        const colPicker = document.getElementById('mesh-color-input');
        if (colPicker) colPicker.value = meta.color || '#ffffff';

        try {
            const res = await this._api(`/api/meshes/${meshId}`);
            const text = await res.text();
            this.viewer.loadTerrainFromOBJ(text, meta);
            document.getElementById('place-vehicle-btn').disabled = false;

            // Auto-apply vertex RGB overlay if mesh has vertex colours
            this._satelliteOn = false;
            const satBtn = document.getElementById('satellite-toggle-btn');
            if (satBtn) satBtn.textContent = '🛰️ RGB Overlay';
            if (this.viewer.hasVertexColors()) {
                this.viewer.applyVertexColorOverlay();
                this._satelliteOn = true;
                if (satBtn) satBtn.textContent = '🗺️ Remove RGB';
            }

            // Load existing committed vehicles for this mesh
            await this._loadPlacements();
            this._startPolling();

            if (this.role === 'maintainer') this._showCorrectionPanel(meta);
        } catch (err) {
            this._toast('Failed to load mesh', 'error');
        }
    }

    _showMeshInfo(meta) {
        document.getElementById('mesh-info-panel').style.display = 'block';
        document.getElementById('mesh-info').innerHTML = `
            <p><strong>File:</strong> ${this._esc(meta.filename || '')}</p>
            <p><strong>Location:</strong> ${this._esc(meta.location_id || '')}</p>
            <p><strong>CRS:</strong> ${meta.crs || ''}</p>
            <p><strong>Center:</strong> ${(meta.center_x || 0).toFixed(1)}, ${(meta.center_y || 0).toFixed(1)}, ${(meta.center_z || 0).toFixed(1)}</p>
            <p><strong>Unit:</strong> ${meta.unit || ''}</p>
            <p><strong>Algorithm:</strong> ${meta.algorithm || ''}</p>
        `;
    }

    // ══════════════════════════════════════════════════════════════════
    // Placements — load, poll, commit
    // ══════════════════════════════════════════════════════════════════

    async _loadPlacements() {
        if (!this.currentMeshId) return;
        try {
            const res = await this._api(`/api/meshes/${this.currentMeshId}/placements`);
            const data = await res.json();
            if (data.success) {
                this.viewer.clearCommittedVehicles();
                for (const p of data.data) {
                    this.viewer.addCommittedVehicle(p);
                }
                document.getElementById('placed-count').textContent =
                    `Vehicles placed: ${data.data.length}`;
                this._renderPlacedVehiclesList(data.data);
            }
        } catch (err) {
            console.error('Failed to load placements', err);
        }
    }


    _renderPlacedVehiclesList(placements) {
        const c = document.getElementById('placed-vehicles-list');
        if (!placements.length) {
            c.innerHTML = '<p class="hint">No vehicles placed yet</p>';
            return;
        }
        const isMaintainer = this.role === 'maintainer';
        c.innerHTML = placements.map(p => {
            const isOwn = isMaintainer || p.placed_by === this.userDescription;
            return `
            <div class="placed-vehicle-item" data-pid="${p.id}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <strong>${this._esc(p.vehicle_name || p.vehicle_id)}</strong>
                    <small style="color:#999">${p.departure_date || 'No departure set'}</small>
                </div>
                <div style="font-size:11px;color:#aaa;margin:2px 0">
                    Pos: ${Number(p.x).toFixed(1)}, ${Number(p.y).toFixed(1)}, ${Number(p.z).toFixed(1)}
                    | Rot: ${(Number(p.rotation_y) * 180 / Math.PI).toFixed(0)}°
                </div>
                ${isOwn ? `<div style="display:flex;gap:4px;margin-top:4px">
                    <button class="btn-sm btn-secondary" data-action="move" data-pid="${p.id}">Move</button>
                    <button class="btn-sm btn-secondary" data-action="edit-dep" data-pid="${p.id}">Departure</button>
                    <button class="btn-sm btn-danger" data-action="delete" data-pid="${p.id}">Remove</button>
                </div>` : ''}
            </div>`;
        }).join('');

        c.querySelectorAll('[data-action="move"]').forEach(btn => {
            btn.addEventListener('click', () => this._startMovePlacement(btn.dataset.pid));
        });
        c.querySelectorAll('[data-action="edit-dep"]').forEach(btn => {
            btn.addEventListener('click', () => this._editDeparture(btn.dataset.pid));
        });
        c.querySelectorAll('[data-action="delete"]').forEach(btn => {
            btn.addEventListener('click', () => this._deletePlacement(btn.dataset.pid));
        });
    }

    async _startMovePlacement(placementId) {
        // Enter a special "move" mode: user clicks terrain → we update placement position
        this._movingPlacementId = placementId;
        this._toast('Click on terrain to set new position for vehicle', 'success');

        // Set a one-time click handler on the viewer
        const orig = this.viewer.onRequestConfirm;
        this.viewer.onRequestConfirm = async (info) => {
            this.viewer.onRequestConfirm = orig;
            try {
                const res = await this._api(`/api/placements/${placementId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        x: info.x, y: info.y, z: info.z,
                        rotation_y: info.rotation_y,
                    }),
                });
                const data = await res.json();
                if (data.success) {
                    this._toast('Vehicle moved');
                    this.viewer.cancelPlacing();
                    await this._loadPlacements();
                } else {
                    this._toast(data.error || 'Move failed', 'error');
                    this.viewer.cancelPlacing();
                }
            } catch {
                this._toast('Move request failed', 'error');
                this.viewer.cancelPlacing();
            }
            this._movingPlacementId = null;
        };

        // Start placing ghost with the same dims as the existing vehicle
        const existing = this.viewer.committedVehicles.find(
            v => v.userData.placementId === placementId
        );
        if (existing) {
            const dims = existing.userData.dims;
            this.viewer.startPlacingVehicle(dims, '#ffaa00', 'move', 'Moving…');
        }
    }

    async _editDeparture(placementId) {
        const newDate = prompt('Enter departure date (YYYY-MM-DD):');
        if (newDate === null) return;
        try {
            const res = await this._api(`/api/placements/${placementId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ departure_date: newDate }),
            });
            const data = await res.json();
            if (data.success) {
                this._toast('Departure date updated');
                await this._loadPlacements();
            } else {
                this._toast(data.error || 'Update failed', 'error');
            }
        } catch {
            this._toast('Update failed', 'error');
        }
    }

    async _deletePlacement(placementId) {
        if (!confirm('Remove this vehicle?')) return;
        try {
            const res = await this._api(`/api/placements/${placementId}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                this._toast('Vehicle removed');
                await this._loadPlacements();
            } else {
                this._toast(data.error || 'Delete failed', 'error');
            }
        } catch {
            this._toast('Delete failed', 'error');
        }
    }

    _startPolling() {
        this._stopPolling();
        this._pollTimer = setInterval(() => this._loadPlacements(), POLL_INTERVAL);
    }

    _stopPolling() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    }

    _startMeshRefresh() {
        this._stopMeshRefresh();
        this._meshRefreshTimer = setInterval(() => this._loadMeshes(), MESH_REFRESH_INTERVAL);
    }

    _stopMeshRefresh() {
        if (this._meshRefreshTimer) {
            clearInterval(this._meshRefreshTimer);
            this._meshRefreshTimer = null;
        }
    }

    // ── Confirm dialog ───────────────────────────────────────────────

    _showConfirmDialog(info) {
        // Remove any existing dialog
        document.getElementById('confirm-dialog')?.remove();

        const depDate = document.getElementById('departure-date-input')?.value || '';
        info.departure_date = depDate;

        const dialog = document.createElement('div');
        dialog.id = 'confirm-dialog';
        dialog.innerHTML = `
            <h4>Confirm Placement</h4>
            <p>Vehicle: <strong>${this._esc(info.vehicle_id)}</strong></p>
            <p>Position: ${info.x.toFixed(1)}, ${info.y.toFixed(1)}, ${info.z.toFixed(1)}</p>
            <p>Rotation: ${(info.rotation_y * 180 / Math.PI).toFixed(1)}°</p>
            <p>Departure: <strong>${depDate ? depDate.replace('T', ' ') : ''}</strong></p>
            <div class="confirm-actions">
                <button class="btn-primary" id="confirm-yes">Confirm</button>
                <button class="btn-secondary" id="confirm-no">Cancel</button>
            </div>
        `;
        document.getElementById('viewer-container').appendChild(dialog);

        document.getElementById('confirm-yes').addEventListener('click', async () => {
            dialog.remove();
            await this._commitPlacement(info);
        });
        document.getElementById('confirm-no').addEventListener('click', () => {
            dialog.remove();
            this.viewer.resumePlacing();
        });
    }

    async _commitPlacement(info) {
        try {
            const res = await this._api(`/api/meshes/${this.currentMeshId}/placements`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vehicle_id: info.vehicle_id,
                    vehicle_name: info.vehicle_name || '',
                    x: info.x,
                    y: info.y,
                    z: info.z,
                    rotation_y: info.rotation_y,
                    length: info.dims.length,
                    width: info.dims.width,
                    height: info.dims.height,
                    color: info.color,
                    departure_date: info.departure_date || '',
                }),
            });
            const data = await res.json();

            if (data.success) {
                this.viewer.confirmPlacement(data.data);
                this._toast('Vehicle placed');
                document.getElementById('placed-count').textContent =
                    `Vehicles placed: ${this.viewer.committedVehicles.length}`;
            } else {
                // Overlap or other rejection
                this._toast(data.error || 'Placement rejected', 'error');
                this.viewer.cancelPlacing();
            }
        } catch {
            this._toast('Failed to commit placement', 'error');
            this.viewer.cancelPlacing();
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // Maintainer: mesh correction overlay
    // ══════════════════════════════════════════════════════════════════

    _showCorrectionPanel(meta) {
        document.getElementById('correction-panel')?.remove();

        this._corValues = {
            ox: meta.offset_x || 0,
            oy: meta.offset_y || 0,
            oz: meta.offset_z || 0,
            ry: meta.rotation_y || 0,
        };

        const panel = document.createElement('div');
        panel.id = 'correction-panel';
        panel.innerHTML = `
            <h4>Mesh Corrections</h4>
            <div class="cor-row"><span>Offset X</span><button data-cor="ox" data-dir="-1">−</button><span id="cor-ox-val">${this._corValues.ox.toFixed(1)}</span><button data-cor="ox" data-dir="1">+</button></div>
            <div class="cor-row"><span>Offset Y</span><button data-cor="oy" data-dir="-1">−</button><span id="cor-oy-val">${this._corValues.oy.toFixed(1)}</span><button data-cor="oy" data-dir="1">+</button></div>
            <div class="cor-row"><span>Offset Z</span><button data-cor="oz" data-dir="-1">−</button><span id="cor-oz-val">${this._corValues.oz.toFixed(1)}</span><button data-cor="oz" data-dir="1">+</button></div>
            <div class="cor-row"><span>Rotation Y</span><button data-cor="ry" data-dir="-1">−</button><span id="cor-ry-val">${this._corValues.ry.toFixed(2)}</span><button data-cor="ry" data-dir="1">+</button></div>
        `;
        document.getElementById('viewer-container').appendChild(panel);

        panel.querySelectorAll('button[data-cor]').forEach(btn => {
            btn.addEventListener('click', () => {
                const key = btn.dataset.cor;
                const dir = parseInt(btn.dataset.dir);
                const step = key === 'ry' ? 0.05 : 1;
                this._corValues[key] += dir * step;
                const valEl = panel.querySelector(`#cor-${key}-val`);
                valEl.textContent = key === 'ry' ? this._corValues[key].toFixed(2) : this._corValues[key].toFixed(1);
                this._applyCorrectionLive();
            });
        });
    }

    _applyCorrectionLive() {
        if (!this._corValues) return;
        this.viewer.setTerrainOffset(this._corValues.ox, this._corValues.oy, this._corValues.oz);
        this.viewer.setTerrainRotationY(this._corValues.ry);
    }

    // ══════════════════════════════════════════════════════════════════
    // Vehicle catalogue
    // ══════════════════════════════════════════════════════════════════

    async _loadVehicles() {
        try {
            const res = await this._api('/api/vehicles');
            const data = await res.json();
            if (data.success) {
                this.vehicles = data.data;
                this._renderVehicleSelect();
            }
        } catch (err) {
            console.error('Failed to load vehicles', err);
        }
    }

    _renderVehicleSelect() {
        const sel = document.getElementById('vehicle-select');
        sel.innerHTML = '<option value="">-- Select Vehicle --</option>';
        for (const v of this.vehicles) {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = `${v.name} (${v.length} × ${v.width} × ${v.height} m)`;
            sel.appendChild(opt);
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // Event binding
    // ══════════════════════════════════════════════════════════════════

    _bindAppEvents() {
        document.getElementById('logout-btn').addEventListener('click', () => {
            this._stopPolling();
            this._stopMeshRefresh();
            location.reload();
        });

        document.getElementById('mesh-search-input')?.addEventListener('input', () => {
            this._renderMeshList();
        });

        // Vehicle selection
        document.getElementById('vehicle-select').addEventListener('change', (e) => {
            const v = this.vehicles.find(x => x.id === e.target.value);
            if (v) {
                document.getElementById('dim-l').textContent = v.length;
                document.getElementById('dim-w').textContent = v.width;
                document.getElementById('dim-h').textContent = v.height;
                document.getElementById('custom-dims').style.display =
                    v.id === 'custom' ? 'block' : 'none';
            }
        });

        // Place vehicle — starts ghost, clicking terrain triggers confirm
        document.getElementById('place-vehicle-btn').addEventListener('click', () => {
            const vid = document.getElementById('vehicle-select').value;
            const v = this.vehicles.find(x => x.id === vid);
            if (!v) return;

            // Get and validate departure date & time
            const depDateInput = document.getElementById('departure-date-input');
            const depDate = depDateInput?.value?.trim();
            if (!depDate) {
                this._toast('Please select a departure date and time before placing the vehicle.', 'error');
                depDateInput?.focus();
                return;
            }

            let dims;
            if (v.id === 'custom') {
                dims = {
                    length: parseFloat(document.getElementById('custom-length').value),
                    width:  parseFloat(document.getElementById('custom-width').value),
                    height: parseFloat(document.getElementById('custom-height').value),
                };
            } else {
                dims = { length: v.length, width: v.width, height: v.height };
            }
            const vehicleName = document.getElementById('vehicle-name-input')?.value?.trim() || v.name || v.id;
            // Pass departure date to the viewer for confirmation dialog
            this.viewer._pendingDepartureDate = depDate;
            this.viewer.startPlacingVehicle(dims, v.color, v.id, vehicleName);
            this._toast('Click on terrain to place. Scroll to rotate.', 'success');
        });

        // Cancel placing
        document.getElementById('cancel-place-btn').addEventListener('click', () => {
            this.viewer.cancelPlacing();
        });

        // Export
        document.getElementById('export-btn').addEventListener('click', () => {
            this.viewer.exportScene();
        });

        // Mesh colour picker
        document.getElementById('mesh-color-input')?.addEventListener('input', (e) => {
            this.viewer.setTerrainColor(e.target.value);
        });
        document.getElementById('save-mesh-color-btn')?.addEventListener('click', () => {
            this._saveMeshColor();
        });

        // Satellite overlay toggle
        document.getElementById('satellite-toggle-btn')?.addEventListener('click', () => {
            this._toggleSatellite();
        });

        // Forum events
        document.getElementById('forum-send-btn').addEventListener('click', () => this._sendForumMessage());
        this._loadForumMessages();

        // ── Maintainer-only ─────────────────────────────────────────
        if (this.role === 'maintainer') {
            document.getElementById('upload-mesh-btn').addEventListener('click', () => this._uploadMesh());
            document.getElementById('create-code-btn').addEventListener('click', () => this._createCode());
            document.getElementById('edit-metadata-btn').addEventListener('click', () => this._saveCorrections());
            document.getElementById('process-mesh-btn')?.addEventListener('click', () => this._processMesh());
            document.getElementById('enable-hole-fill-btn')?.addEventListener('click', () => this._enableHoleFillMode());
            document.getElementById('enable-paint-btn')?.addEventListener('click', () => this._togglePaintMode());
            document.getElementById('clear-paint-btn')?.addEventListener('click', () => this._clearPaint());
            document.getElementById('save-paint-btn')?.addEventListener('click', () => this._savePaint());
            document.getElementById('refresh-log-btn')?.addEventListener('click', () => this._loadActivityLog());
            document.getElementById('log-filter')?.addEventListener('change', () => this._loadActivityLog());
            this._loadActivityLog();
        }

        // ── Open map page ───────────────────────────────────────────
        document.getElementById('open-map-btn')?.addEventListener('click', () => {
            window.open(`map.html?code=${encodeURIComponent(this.accessCode)}`, '_blank');
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // Maintainer actions
    // ══════════════════════════════════════════════════════════════════

    async _uploadMesh() {
        const fileInput = document.getElementById('mesh-file-input');
        if (!fileInput.files[0]) { this._toast('Select a file first', 'error'); return; }

        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        fd.append('location_id', document.getElementById('upload-location-id').value || 'default');
        fd.append('description',  document.getElementById('upload-description').value);
        fd.append('center_x',     document.getElementById('upload-cx').value);
        fd.append('center_y',     document.getElementById('upload-cy').value);
        fd.append('center_z',     document.getElementById('upload-cz').value);

        try {
            const res = await this._api('/api/meshes', { method: 'POST', body: fd });
            const data = await res.json();
            if (data.success) {
                this._toast('Mesh uploaded');
                this._loadMeshes();
                fileInput.value = '';
            } else {
                this._toast(data.error, 'error');
            }
        } catch {
            this._toast('Upload failed', 'error');
        }
    }

    async _createCode() {
        const locationId = document.getElementById('new-code-location').value.trim();
        const role = document.getElementById('new-code-role').value;
        if (!locationId) { this._toast('Enter a location ID', 'error'); return; }

        try {
            const res = await this._api('/api/auth/codes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ location_id: locationId, role }),
            });
            const data = await res.json();
            if (data.success) {
                const el = document.getElementById('generated-code');
                el.style.display = 'block';
                el.innerHTML = `<strong>New Code:</strong><br><code>${this._esc(data.data.code)}</code><br><small>Copy and share this code</small>`;
            }
        } catch {
            this._toast('Failed to create code', 'error');
        }
    }

    async _saveCorrections() {
        if (!this.currentMeshId || !this._corValues) return;

        const updates = {
            offset_x:   this._corValues.ox,
            offset_y:   this._corValues.oy,
            offset_z:   this._corValues.oz,
            rotation_y:  this._corValues.ry,
        };

        try {
            const res = await this._api(`/api/meshes/${this.currentMeshId}/metadata`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates),
            });
            const data = await res.json();
            if (data.success) {
                this._toast('Corrections saved');
                const idx = this.meshes.findIndex(m => m.id === this.currentMeshId);
                if (idx !== -1) Object.assign(this.meshes[idx], updates);
            }
        } catch {
            this._toast('Save failed', 'error');
        }
    }

    async _saveMeshColor() {
        if (!this.currentMeshId) return;
        const color = document.getElementById('mesh-color-input')?.value;
        if (!color) return;

        try {
            const res = await this._api(`/api/meshes/${this.currentMeshId}/color`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ color }),
            });
            const data = await res.json();
            if (data.success) {
                this._toast('Colour saved');
                const idx = this.meshes.findIndex(m => m.id === this.currentMeshId);
                if (idx !== -1) this.meshes[idx].color = color;
            }
        } catch {
            this._toast('Save colour failed', 'error');
        }
    }

    // ── Mesh processing (maintainer) ─────────────────────────────────

    async _processMesh() {
        if (!this.currentMeshId) {
            this._toast('Select a mesh first', 'error');
            return;
        }

        const fillHoles = document.getElementById('proc-fill')?.checked ?? true;
        const smooth = document.getElementById('proc-smooth')?.checked ?? true;
        const iterations = parseInt(document.getElementById('proc-iterations')?.value || '5', 10);
        const method = document.getElementById('proc-method')?.value || 'laplacian';

        this._toast('Processing mesh…');

        try {
            const res = await this._api(`/api/meshes/${this.currentMeshId}/process`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    fill_holes: fillHoles,
                    smooth,
                    smooth_iterations: iterations,
                    smooth_method: method,
                }),
            });
            const data = await res.json();
            if (data.success) {
                this._toast('Processing complete — reloading mesh');
                // Re-select to reload the processed file
                await this._selectMesh(this.currentMeshId);
            } else {
                this._toast(data.error || 'Processing failed', 'error');
            }
        } catch {
            this._toast('Processing request failed', 'error');
        }
    }

    _enableHoleFillMode() {
        if (!this.currentMeshId) {
            this._toast('Select a mesh first', 'error');
            return;
        }

        const btn = document.getElementById('enable-hole-fill-btn');
        btn?.classList.add('active-mode');
        this.viewer.enableHoleFillMode(true, async (point) => {
            btn?.classList.remove('active-mode');
            const holeSize = parseFloat(document.getElementById('manual-hole-size')?.value || '100');
            this._toast('Filling hole…');
            try {
                const res = await this._api(`/api/meshes/${this.currentMeshId}/fill-hole`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ point, hole_size: holeSize }),
                });
                const data = await res.json();
                if (data.success) {
                    this._toast('Hole fill applied — reloading mesh');
                    await this._selectMesh(this.currentMeshId);
                } else {
                    this._toast(data.error || 'Hole fill failed', 'error');
                }
            } catch {
                this._toast('Hole fill request failed', 'error');
            }
        });
        this._toast('Click a mesh area to fill holes there.');
    }

    _togglePaintMode() {
        if (!this.currentMeshId) {
            this._toast('Select a mesh first', 'error');
            return;
        }

        const btn = document.getElementById('enable-paint-btn');
        const enable = !this.viewer.paintMode;
        if (enable) {
            const color = document.getElementById('paint-color-input')?.value || '#ff7f50';
            const radius = parseFloat(document.getElementById('paint-radius-input')?.value || '2.5');
            this.viewer.enablePaintMode(true, {
                color,
                radius,
                onStroke: (stroke) => this._pendingPaintStrokes.push(stroke),
            });
            btn?.classList.add('active-mode');
            btn.textContent = 'Disable Paint Mode';
            this._toast('Paint mode enabled. Click the mesh to paint.', 'success');
        } else {
            this.viewer.enablePaintMode(false);
            btn?.classList.remove('active-mode');
            btn.textContent = 'Enable Paint Mode';
        }
    }

    _clearPaint() {
        this.viewer.clearPaint();
        this._pendingPaintStrokes = [];
        this._toast('Paint cleared');
    }

    async _savePaint() {
        if (!this.currentMeshId) return;
        const paintStrokes = this.viewer.getPaintStrokes();
        try {
            const res = await this._api(`/api/meshes/${this.currentMeshId}/metadata`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paint_strokes: paintStrokes }),
            });
            const data = await res.json();
            if (data.success) {
                this._toast('Paint saved and visible to users');
                const idx = this.meshes.findIndex(m => m.id === this.currentMeshId);
                if (idx !== -1) this.meshes[idx].paint_strokes = paintStrokes;
            } else {
                this._toast(data.error || 'Paint save failed', 'error');
            }
        } catch {
            this._toast('Paint save failed', 'error');
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // Satellite overlay
    // ══════════════════════════════════════════════════════════════════

    _toggleSatellite() {
        if (!this.currentMeshId || !this.viewer) {
            this._toast('Select a mesh first', 'error');
            return;
        }
        const btn = document.getElementById('satellite-toggle-btn');
        if (this._satelliteOn) {
            this.viewer.removeSatelliteTexture();
            this._satelliteOn = false;
            btn.textContent = '🛰️ RGB Overlay';
            this._toast('Vertex colour overlay removed');
        } else {
            this.viewer.applyVertexColorOverlay();
            this._satelliteOn = true;
            btn.textContent = '🗺️ Remove RGB';
            this._toast('Vertex RGB colours applied');
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // Activity Log (maintainer)
    // ══════════════════════════════════════════════════════════════════

    async _loadActivityLog() {
        const filter = document.getElementById('log-filter')?.value || '';
        const qs = filter ? `?action=${encodeURIComponent(filter)}` : '';
        try {
            const res = await this._api(`/api/activity-log${qs}`);
            const data = await res.json();
            if (data.success) {
                this._renderLog(data.data);
            }
        } catch (err) {
            console.error('Failed to load log', err);
        }
    }

    _renderLog(entries) {
        const c = document.getElementById('log-entries');
        if (!entries.length) {
            c.innerHTML = '<p class="hint">No log entries</p>';
            return;
        }
        c.innerHTML = entries.map(e => {
            const ts = new Date(e.timestamp).toLocaleString();
            const details = Object.entries(e.details || {})
                .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
                .join(', ');
            return `<div class="log-entry">
                <span class="log-time">${ts}</span>
                <span class="log-action">${this._esc(e.action)}</span>
                <span class="log-user">${this._esc(e.user || '—')}</span>
                ${details ? `<div class="log-details">${this._esc(details)}</div>` : ''}
            </div>`;
        }).join('');
    }

    // ══════════════════════════════════════════════════════════════════
    // Helpers
    // ══════════════════════════════════════════════════════════════════

    _esc(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    _toast(msg, type = 'success') {
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }
}

// ── Bootstrap ────────────────────────────────────────────────────────
new App();
