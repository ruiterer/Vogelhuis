/* Birdcam UI — vanilla JavaScript */

document.addEventListener("DOMContentLoaded", () => {
    initClock();

    if (document.getElementById("video-player")) initPlayer();
    if (document.getElementById("settings-form")) initSettings();
    if (document.getElementById("health-dashboard")) initHealth();
});

/* --- Clock --- */

function initClock() {
    const el = document.getElementById("clock");
    if (!el) return;
    function update() {
        el.textContent = new Date().toLocaleString();
    }
    update();
    setInterval(update, 1000);
}

/* --- HLS Player --- */

function initPlayer() {
    const video = document.getElementById("video-player");
    const statusBadge = document.getElementById("camera-status");
    const hlsUrl = "/hls/stream.m3u8";

    let hls;
    let cameraOnline = false;

    function setStatus(status, text) {
        statusBadge.textContent = text;
        statusBadge.className = "status-badge " + status;
        cameraOnline = status === "online";
    }

    function startHls() {
        if (video.canPlayType("application/vnd.apple.mpegurl")) {
            // Safari: native HLS
            video.src = hlsUrl;
            video.addEventListener("loadedmetadata", () => {
                video.play().catch(() => {});
                setStatus("online", "Live");
            });
            video.addEventListener("error", () => setStatus("offline", "Offline"));
        } else if (typeof Hls !== "undefined" && Hls.isSupported()) {
            hls = new Hls({
                liveSyncDurationCount: 2,
                liveMaxLatencyDurationCount: 5,
                enableWorker: true,
                lowLatencyMode: false,
            });
            hls.loadSource(hlsUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                video.play().catch(() => {});
                setStatus("online", "Live");
            });
            hls.on(Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    setStatus("offline", "Offline");
                    // Retry after 5 seconds
                    setTimeout(() => {
                        hls.destroy();
                        startHls();
                    }, 5000);
                }
            });
        } else {
            setStatus("offline", "HLS not supported");
        }
    }

    startHls();

    // Poll camera status
    setInterval(async () => {
        try {
            const resp = await fetch("/api/health");
            const data = await resp.json();
            const cam = data.camera || {};
            if (cam.status === "online" && !cameraOnline) {
                // Camera came back, reload player
                if (hls) { hls.destroy(); }
                startHls();
            } else if (cam.status !== "online") {
                setStatus(cam.status || "offline", cam.status === "stale" ? "Stale" : "Offline");
            }
        } catch (e) { /* ignore poll errors */ }
    }, 10000);

    // Snapshot button
    const btnSnapshot = document.getElementById("btn-snapshot");
    btnSnapshot.addEventListener("click", async () => {
        btnSnapshot.disabled = true;
        btnSnapshot.textContent = "Capturing...";
        try {
            const resp = await fetch("/api/snapshot", { method: "POST" });
            const data = await resp.json();
            if (resp.ok) {
                showToast(`Snapshot saved: ${data.filename}`);
                loadSnapshots();
            } else {
                showToast(data.error || "Snapshot failed", true);
            }
        } catch (e) {
            showToast("Snapshot request failed", true);
        }
        btnSnapshot.disabled = false;
        btnSnapshot.textContent = "Snapshot";
    });

    // Fullscreen button
    const btnFullscreen = document.getElementById("btn-fullscreen");
    btnFullscreen.addEventListener("click", () => {
        const wrapper = document.querySelector(".video-wrapper");
        if (wrapper.requestFullscreen) wrapper.requestFullscreen();
        else if (wrapper.webkitRequestFullscreen) wrapper.webkitRequestFullscreen();
    });

    // Load snapshots
    loadSnapshots();
}

function showToast(msg, isError) {
    const toast = document.getElementById("snapshot-toast");
    toast.textContent = msg;
    toast.className = "toast" + (isError ? " error" : "");
    setTimeout(() => { toast.className = "toast hidden"; }, 4000);
}

async function loadSnapshots() {
    const container = document.getElementById("snapshots-list");
    if (!container) return;
    try {
        const resp = await fetch("/api/snapshots");
        const snapshots = await resp.json();
        if (snapshots.length === 0) {
            container.innerHTML = '<p style="color:#666;font-size:14px;">No snapshots yet.</p>';
            return;
        }
        container.innerHTML = snapshots.slice(0, 12).map(s => `
            <div class="snapshot-card">
                <a href="/snapshots/${s.filename}" download>${s.filename}</a>
                <div class="meta">${s.size_kb} KB</div>
            </div>
        `).join("");
    } catch (e) {
        container.innerHTML = '<p style="color:#666;font-size:14px;">Could not load snapshots.</p>';
    }
}

/* --- Settings --- */

function initSettings() {
    const form = document.getElementById("settings-form");
    const status = document.getElementById("save-status");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        status.textContent = "Saving...";
        status.className = "save-status";

        // Build config object from form fields
        const config = {};
        const formData = new FormData(form);
        for (const [key, value] of formData.entries()) {
            const parts = key.split(".");
            let obj = config;
            for (let i = 0; i < parts.length - 1; i++) {
                obj[parts[i]] = obj[parts[i]] || {};
                obj = obj[parts[i]];
            }
            // Try to parse numbers
            const num = Number(value);
            obj[parts[parts.length - 1]] = (value !== "" && !isNaN(num) && parts[parts.length - 1] !== "title" && parts[parts.length - 1] !== "timezone" && parts[parts.length - 1] !== "path") ? num : value;
        }

        // Handle unchecked checkboxes (rotation: 0 when unchecked)
        const rotationCheckbox = form.querySelector('[name="stream.rotation"]');
        if (rotationCheckbox && !rotationCheckbox.checked) {
            config.stream = config.stream || {};
            config.stream.rotation = 0;
        }

        try {
            const resp = await fetch("/api/config", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(config),
            });
            const data = await resp.json();
            if (resp.ok) {
                status.textContent = "Saved!";
                status.className = "save-status ok";
                if (data.restart_required) {
                    status.textContent = "Saved! Restart the camera stream to apply changes.";
                }
            } else {
                status.textContent = (data.error || "Save failed");
                status.className = "save-status err";
            }
        } catch (e) {
            status.textContent = "Request failed";
            status.className = "save-status err";
        }
    });

    // Restart stream button
    const btnRestart = document.getElementById("btn-restart-stream");
    btnRestart.addEventListener("click", async () => {
        if (!confirm("Restart the camera stream? The live view will be interrupted briefly.")) return;
        btnRestart.disabled = true;
        btnRestart.textContent = "Restarting...";
        try {
            const resp = await fetch("/api/restart-stream", { method: "POST" });
            const data = await resp.json();
            if (resp.ok) {
                btnRestart.textContent = "Restarted!";
                setTimeout(() => {
                    btnRestart.textContent = "Restart Camera Stream";
                    btnRestart.disabled = false;
                }, 5000);
            } else {
                alert("Restart failed: " + (data.error || "Unknown error"));
                btnRestart.textContent = "Restart Camera Stream";
                btnRestart.disabled = false;
            }
        } catch (e) {
            alert("Restart request failed");
            btnRestart.textContent = "Restart Camera Stream";
            btnRestart.disabled = false;
        }
    });
}

/* --- Health --- */

function initHealth() {
    // --- Health metrics polling ---
    async function pollHealth() {
        try {
            const resp = await fetch("/api/health");
            const d = await resp.json();

            setText("h-cpu", d.cpu_percent + "%");
            setText("h-memory", d.memory.percent + "%");
            setText("h-memory-detail", d.memory.used_mb + " / " + d.memory.total_mb + " MB");
            setText("h-temp", d.cpu_temperature !== null ? d.cpu_temperature + " °C" : "N/A");
            setText("h-disk", d.disk.percent + "%");
            setText("h-disk-detail", d.disk.free_gb + " GB free of " + d.disk.total_gb + " GB");
            setText("h-uptime", d.uptime);
            setText("h-camera", d.camera.status);
            setText("h-camera-detail", d.camera.detail);

            const camEl = document.getElementById("h-camera");
            camEl.style.color = d.camera.status === "online" ? "var(--success)" : "var(--danger)";

            for (const [name, state] of Object.entries(d.services)) {
                const el = document.getElementById("s-" + name.replace("birdcam-", ""));
                if (el) {
                    el.textContent = state;
                    el.className = "service-status " + (state === "active" ? "active" : state === "inactive" ? "inactive" : "unknown");
                }
            }
        } catch (e) { /* ignore */ }
    }

    pollHealth();
    setInterval(pollHealth, 5000);

    // --- Log viewer ---
    if (document.getElementById("log-viewer")) initLogViewer();
}

function initLogViewer() {
    const container = document.getElementById("log-entries");
    const statusEl = document.getElementById("log-status");
    const sourceSelect = document.getElementById("log-source");
    const levelSelect = document.getElementById("log-level");
    const periodSelect = document.getElementById("log-period");
    const downloadBtn = document.getElementById("btn-download-logs");

    let currentLogs = [];

    function buildUrl() {
        const params = new URLSearchParams();
        if (sourceSelect.value) params.set("source", sourceSelect.value);
        if (levelSelect.value) params.set("level", levelSelect.value);
        if (periodSelect.value) params.set("minutes", periodSelect.value);
        return "/api/logs?" + params.toString();
    }

    function renderLogs(entries) {
        if (entries.length === 0) {
            container.innerHTML = '<div class="log-line" style="color:#888;">No log entries match the current filters.</div>';
            statusEl.textContent = "0 entries";
            return;
        }

        container.innerHTML = entries.map(e => {
            const ts = e.timestamp ? `<span class="log-ts">${e.timestamp}</span> ` : "";
            const lvl = `<span class="log-lvl-${e.level}">[${e.level}]</span>`;
            const src = `<span class="log-src">[${e.source}]</span>`;
            const msg = `<span class="log-msg">${escapeHtml(e.message)}</span>`;
            return `<div class="log-line">${ts}${lvl} ${src} ${msg}</div>`;
        }).join("");

        statusEl.textContent = `${entries.length} entries`;
    }

    async function pollLogs() {
        try {
            const resp = await fetch(buildUrl());
            currentLogs = await resp.json();
            renderLogs(currentLogs);
        } catch (e) {
            statusEl.textContent = "Failed to load logs";
        }
    }

    // Poll on filter change
    sourceSelect.addEventListener("change", pollLogs);
    levelSelect.addEventListener("change", pollLogs);
    periodSelect.addEventListener("change", pollLogs);

    // Download filtered logs as text file
    downloadBtn.addEventListener("click", () => {
        if (currentLogs.length === 0) return;
        const text = currentLogs.map(e => {
            const ts = e.timestamp || "                   ";
            return `${ts} [${e.level}] [${e.source}] ${e.message}`;
        }).join("\n");

        const blob = new Blob([text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const now = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        a.download = `birdcam-logs-${now}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    });

    // Initial load + auto-refresh
    pollLogs();
    setInterval(pollLogs, 5000);
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}
