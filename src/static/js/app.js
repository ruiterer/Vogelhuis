/* Birdcam UI — vanilla JavaScript */

document.addEventListener("DOMContentLoaded", () => {
    initClock();

    if (document.getElementById("video-player")) initPlayer();
    if (document.getElementById("settings-form")) initSettings();
    if (document.getElementById("health-dashboard")) initHealth();
    if (document.getElementById("graphs-page")) initGraphs();
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

    // GPIO toggle buttons
    initGpioToggles();

    // Sensor readings
    initSensorReadings();

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

/* --- GPIO Toggle Buttons --- */

function initGpioToggles() {
    const buttons = document.querySelectorAll(".gpio-toggle");
    buttons.forEach(btn => {
        btn.addEventListener("click", async () => {
            const target = btn.dataset.target;
            const isOn = btn.classList.contains("on");
            const newState = !isOn;

            btn.disabled = true;
            try {
                const resp = await fetch(`/api/gpio/${target}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ state: newState }),
                });
                if (resp.ok) {
                    btn.classList.toggle("on", newState);
                    // Complementary: turning one light on turns the other off
                    if (newState) {
                        if (target === "light") updateGpioButton("btn-ir-light", false);
                        if (target === "ir-light") updateGpioButton("btn-light", false);
                    }
                } else {
                    const data = await resp.json();
                    showToast(data.error || "GPIO command failed", true);
                }
            } catch (e) {
                showToast("GPIO request failed", true);
            }
            btn.disabled = false;
        });
    });
}

/* --- Sensor Readings --- */

function initSensorReadings() {
    async function poll() {
        try {
            const resp = await fetch("/api/gpio/status");
            const d = await resp.json();

            setText("sr-temp", d.temperature !== null ? `Temp: ${d.temperature}°C` : "Temp: --");
            setText("sr-humidity", d.humidity !== null ? `Humidity: ${d.humidity}%` : "Humidity: --");
            setText("sr-cpu", d.cpu_temp !== null ? `CPU: ${d.cpu_temp}°C` : "CPU: --");

            const motionEl = document.getElementById("sr-motion");
            if (motionEl) {
                motionEl.textContent = d.motion ? "Motion: Active" : "Motion: --";
                motionEl.className = "sensor-item" + (d.motion ? " motion-active" : "");
            }

            // Update GPIO button states
            updateGpioButton("btn-light", d.light);
            updateGpioButton("btn-ir-light", d.ir_light);
            updateGpioButton("btn-fan", d.fan);
        } catch (e) { /* ignore */ }
    }

    poll();
    setInterval(poll, 5000);
}

function updateGpioButton(id, state) {
    const btn = document.getElementById(id);
    if (btn) {
        btn.classList.toggle("on", !!state);
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
            const lastKey = parts[parts.length - 1];
            // Fields that should remain as strings
            const stringFields = ["title", "timezone", "path", "night_start", "day_start",
                                  "broker", "topic", "location", "object_name"];
            const num = Number(value);
            obj[lastKey] = (value !== "" && !isNaN(num) && !stringFields.includes(lastKey)) ? num : value;
        }

        // Handle unchecked checkboxes
        const rotationCheckbox = form.querySelector('[name="stream.rotation"]');
        if (rotationCheckbox && !rotationCheckbox.checked) {
            config.stream = config.stream || {};
            config.stream.rotation = 0;
        }

        // Handle GPIO enabled checkbox
        const gpioCheckbox = form.querySelector('[name="gpio.enabled"]');
        if (gpioCheckbox && !gpioCheckbox.checked) {
            config.gpio = config.gpio || {};
            config.gpio.enabled = false;
        } else if (gpioCheckbox && gpioCheckbox.checked) {
            config.gpio = config.gpio || {};
            config.gpio.enabled = true;
        }

        // Handle MQTT enabled checkbox
        const mqttCheckbox = form.querySelector('[name="mqtt.enabled"]');
        if (mqttCheckbox && !mqttCheckbox.checked) {
            config.mqtt = config.mqtt || {};
            config.mqtt.enabled = false;
        } else if (mqttCheckbox && mqttCheckbox.checked) {
            config.mqtt = config.mqtt || {};
            config.mqtt.enabled = true;
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
                if (data.restart_required && data.gpio_restart_required) {
                    status.textContent = "Saved! Restart camera stream and GPIO service to apply changes.";
                } else if (data.restart_required) {
                    status.textContent = "Saved! Restart the camera stream to apply changes.";
                } else if (data.gpio_restart_required) {
                    status.textContent = "Saved! Restart the GPIO service to apply changes.";
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

    // Restart GPIO button
    const btnRestartGpio = document.getElementById("btn-restart-gpio");
    if (btnRestartGpio) {
        btnRestartGpio.addEventListener("click", async () => {
            if (!confirm("Restart the GPIO service? Sensor readings will be interrupted briefly.")) return;
            btnRestartGpio.disabled = true;
            btnRestartGpio.textContent = "Restarting...";
            try {
                const resp = await fetch("/api/restart-gpio", { method: "POST" });
                const data = await resp.json();
                if (resp.ok) {
                    btnRestartGpio.textContent = "Restarted!";
                    setTimeout(() => {
                        btnRestartGpio.textContent = "Restart GPIO Service";
                        btnRestartGpio.disabled = false;
                    }, 5000);
                } else {
                    alert("Restart failed: " + (data.error || "Unknown error"));
                    btnRestartGpio.textContent = "Restart GPIO Service";
                    btnRestartGpio.disabled = false;
                }
            } catch (e) {
                alert("Restart request failed");
                btnRestartGpio.textContent = "Restart GPIO Service";
                btnRestartGpio.disabled = false;
            }
        });
    }
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
    const verboseCheck = document.getElementById("log-verbose");
    const downloadBtn = document.getElementById("btn-download-logs");

    let currentLogs = [];

    function buildUrl() {
        const params = new URLSearchParams();
        if (sourceSelect.value) params.set("source", sourceSelect.value);
        if (levelSelect.value) params.set("level", levelSelect.value);
        if (periodSelect.value) params.set("minutes", periodSelect.value);
        if (verboseCheck.checked) params.set("verbose", "1");
        return "/api/logs?" + params.toString();
    }

    function renderLogs(entries) {
        if (entries.length === 0) {
            container.innerHTML = '<div class="log-line" style="color:#888;">No log entries match the current filters.</div>';
            statusEl.textContent = "0 entries";
            return;
        }

        container.innerHTML = entries.map(e => {
            const cls = e.unstructured ? "log-line log-unstructured" : "log-line";
            const ts = `<span class="log-ts">${e.timestamp}</span> `;
            const lvl = `<span class="log-lvl-${e.level}">[${e.level}]</span>`;
            const src = `<span class="log-src">[${e.source}]</span>`;
            const msg = `<span class="log-msg">${escapeHtml(e.message)}</span>`;
            return `<div class="${cls}">${ts}${lvl} ${src} ${msg}</div>`;
        }).join("");

        // Auto-scroll to bottom (newest entries)
        container.scrollTop = container.scrollHeight;

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
    verboseCheck.addEventListener("change", pollLogs);

    // Download filtered logs as text file
    downloadBtn.addEventListener("click", () => {
        if (currentLogs.length === 0) return;
        const text = currentLogs.map(e => {
            return `${e.timestamp} [${e.level}] [${e.source}] ${e.message}`;
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

/* --- Graphs --- */

function initGraphs() {
    let currentMinutes = 1440;
    let charts = {};

    // Time range buttons
    document.querySelectorAll(".time-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".time-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentMinutes = parseInt(btn.dataset.minutes);
            loadGraphData();
        });
    });

    function createChart(canvasId, config) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        return new Chart(ctx, config);
    }

    function formatTime(ts) {
        // Handle both ISO and space-separated timestamps
        const d = new Date(ts.replace(" ", "T"));
        if (currentMinutes <= 720) {
            return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        }
        return d.toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    }

    function destroyCharts() {
        Object.values(charts).forEach(c => { if (c) c.destroy(); });
        charts = {};
    }

    async function loadGraphData() {
        try {
            const [sensorResp, motionResp] = await Promise.all([
                fetch(`/api/sensor-data?minutes=${currentMinutes}`),
                fetch(`/api/motion-events?minutes=${currentMinutes}`),
            ]);
            const sensorData = await sensorResp.json();
            const motionEvents = await motionResp.json();

            destroyCharts();

            const labels = sensorData.map(d => formatTime(d.timestamp));
            const commonOptions = {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: "index" },
                plugins: { legend: { position: "top" } },
                scales: {
                    x: {
                        ticks: {
                            maxTicksLimit: 12,
                            maxRotation: 0,
                        },
                    },
                },
            };

            // Temperature chart
            charts.temperature = createChart("chart-temperature", {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: "Birdhouse (°C)",
                            data: sensorData.map(d => d.temperature),
                            borderColor: "#e0af68",
                            backgroundColor: "rgba(224,175,104,0.1)",
                            fill: true,
                            tension: 0.3,
                            pointRadius: 0,
                        },
                        {
                            label: "CPU (°C)",
                            data: sensorData.map(d => d.cpu_temp),
                            borderColor: "#f7768e",
                            backgroundColor: "rgba(247,118,142,0.1)",
                            fill: true,
                            tension: 0.3,
                            pointRadius: 0,
                        },
                    ],
                },
                options: commonOptions,
            });

            // Humidity chart
            charts.humidity = createChart("chart-humidity", {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{
                        label: "Humidity (%)",
                        data: sensorData.map(d => d.humidity),
                        borderColor: "#7aa2f7",
                        backgroundColor: "rgba(122,162,247,0.1)",
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                    }],
                },
                options: commonOptions,
            });

            // Motion chart — bar chart counting events per time bucket
            const motionLabels = motionEvents.map(e => formatTime(e.timestamp));
            charts.motion = createChart("chart-motion", {
                type: "bar",
                data: {
                    labels: motionLabels,
                    datasets: [{
                        label: "Motion Events",
                        data: motionEvents.map(() => 1),
                        backgroundColor: "rgba(158,206,106,0.6)",
                        borderColor: "#9ece6a",
                        borderWidth: 1,
                    }],
                },
                options: {
                    ...commonOptions,
                    scales: {
                        ...commonOptions.scales,
                        y: { beginAtZero: true, ticks: { stepSize: 1 } },
                    },
                },
            });

        } catch (e) {
            console.error("Failed to load graph data:", e);
        }
    }

    // Check if Chart.js is available
    if (typeof Chart === "undefined") {
        document.querySelector(".graphs-container").innerHTML =
            '<h1>Sensor Graphs</h1><p style="color:var(--danger)">Chart.js not loaded. Run install.sh or update.sh to install it.</p>';
        return;
    }

    loadGraphData();
    setInterval(loadGraphData, 60000);
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
