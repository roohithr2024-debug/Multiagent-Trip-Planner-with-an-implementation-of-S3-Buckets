let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";

function setPrompt(text) {
    document.getElementById("userInput").value = text;
}

function setLoading(isLoading) {
    const sendBtn = document.getElementById("sendBtn");
    const btnText = document.getElementById("btnText");
    const btnLoader = document.getElementById("btnLoader");

    sendBtn.disabled = isLoading;

    if (isLoading) {
        btnText.classList.add("hidden");
        btnLoader.classList.remove("hidden");
    } else {
        btnText.classList.remove("hidden");
        btnLoader.classList.add("hidden");
    }
}

function showError(message) {
    const errorBox = document.getElementById("errorBox");
    errorBox.textContent = message;
    errorBox.classList.remove("hidden");
}

function hideError() {
    const errorBox = document.getElementById("errorBox");
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
}

function showResult(answer, threadId, tripId = null) {
    latestAnswerMarkdown = answer;
    const resultSection = document.getElementById("resultSection");
    const resultBox = document.getElementById("resultBox");
    const threadInfo = document.getElementById("threadInfo");

    if (typeof marked !== "undefined") {
        resultBox.innerHTML = marked.parse(answer);
    } else {
        resultBox.innerText = answer;
    }

    const label = tripId ? `Trip ID: ${tripId} • Thread ID: ${threadId}` : `Thread ID: ${threadId}`;
    threadInfo.textContent = label;
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatDate(dateString) {
    if (!dateString) return "Unknown date";
    try {
        return new Date(dateString).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    } catch {
        return dateString;
    }
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

async function loadSavedTrips() {
    const searchInput = document.getElementById("savedSearch");
    const dateInput = document.getElementById("savedDateFilter");
    const destinationInput = document.getElementById("savedDestinationFilter");
    const versionInput = document.getElementById("savedVersionFilter");

    const params = new URLSearchParams();
    if (searchInput.value.trim()) params.set("q", searchInput.value.trim());
    if (destinationInput.value) params.set("destination", destinationInput.value);
    if (dateInput.value) params.set("date", dateInput.value);
    if (versionInput.value) params.set("version", versionInput.value);

    const response = await fetch(`/api/trips?${params.toString()}`);
    const data = await response.json();
    const trips = data.trips || [];

    const destinations = [...new Set(trips.map((trip) => trip.destination).filter(Boolean))].sort();
    const currentDestination = destinationInput.value;
    destinationInput.innerHTML = '<option value="">All destinations</option>' + destinations.map((destination) => `<option value="${destination}">${destination}</option>`).join("");
    if (currentDestination) {
        destinationInput.value = currentDestination;
    }

    const container = document.getElementById("savedTripsList");
    if (!trips.length) {
        container.innerHTML = '<div class="empty-state">No saved trips found. Generate a trip to create the first S3-backed entry.</div>';
        return;
    }

    container.innerHTML = trips.map((trip) => {
        const versionBadges = Array.isArray(trip.summary?.version_history) && trip.summary.version_history.length
            ? trip.summary.version_history.map((entry) => `<button class="mini-btn" data-action="open-version" data-trip-id="${trip.trip_id}" data-version="${entry.version || trip.current_version}">${entry.version ? `v${entry.version}` : "Version"}</button>`).join("")
            : `<span class="muted">v${trip.current_version}</span>`;

        return `
            <div class="trip-card">
                <div class="trip-header">
                    <div>
                        <h3>${trip.destination || "Unspecified destination"}</h3>
                        <p>${trip.trip_id} • ${trip.current_version || 1} version(s) • ${formatDate(trip.created_at)}</p>
                    </div>
                    <span class="trip-badge">v${trip.current_version || 1}</span>
                </div>
                <div class="trip-actions">
                    <button class="small-btn" data-action="view" data-trip-id="${trip.trip_id}">View</button>
                    <button class="small-btn success" data-action="download" data-trip-id="${trip.trip_id}">Download</button>
                    <button class="small-btn" data-action="versions" data-trip-id="${trip.trip_id}">Versions</button>
                    <button class="small-btn danger" data-action="delete" data-trip-id="${trip.trip_id}">Delete</button>
                </div>
                <div class="version-row">${versionBadges}</div>
            </div>
        `;
    }).join("");
}

async function loadAnalytics() {
    const response = await fetch("/api/storage/analytics");
    const data = await response.json();
    const analytics = data.analytics || {};
    const grid = document.getElementById("analyticsGrid");
    grid.innerHTML = `
        <div class="metric-box"><span>Saved Trips</span><strong>${analytics.saved_trips ?? 0}</strong></div>
        <div class="metric-box"><span>Objects</span><strong>${analytics.total_objects ?? 0}</strong></div>
        <div class="metric-box"><span>Versions</span><strong>${analytics.total_versions ?? 0}</strong></div>
        <div class="metric-box"><span>Storage</span><strong>${analytics.storage_used ?? "0 B"}</strong></div>
        <div class="metric-box"><span>Most Recent Trip</span><strong title="${escapeHtml(analytics.most_recent_trip || "-")}">${escapeHtml(analytics.most_recent_trip || "-")}</strong></div>
        <div class="metric-box"><span>Largest Stored Trip</span><strong title="${escapeHtml(analytics.largest_trip || "-")}">${escapeHtml(analytics.largest_trip || "-")}</strong></div>
    `;

    renderBreakdown("destinationBreakdown", analytics.destination_breakdown || [], analytics.saved_trips);
    renderBreakdown("versionBreakdown", analytics.version_breakdown || [], analytics.saved_trips);

    const recentTrips = document.getElementById("recentTrips");
    const trips = analytics.recent_trips || [];
    recentTrips.innerHTML = trips.length
        ? trips.map((trip) => `
            <button class="recent-trip" data-action="view" data-trip-id="${escapeHtml(trip.trip_id)}">
                <span>
                    <strong>${escapeHtml(trip.destination)}</strong>
                    <small>${escapeHtml(trip.trip_id)} · ${formatDate(trip.created_at)}</small>
                </span>
                <span class="recent-trip-size">${escapeHtml(trip.storage_used)}</span>
            </button>
        `).join("")
        : '<div class="empty-state">No trip activity yet.</div>';
}

function renderBreakdown(elementId, entries, total) {
    const container = document.getElementById(elementId);
    if (!entries.length) {
        container.innerHTML = '<div class="empty-state">No analytics data yet.</div>';
        return;
    }

    const denominator = Number(total) || entries.reduce((sum, entry) => sum + Number(entry.count || 0), 0) || 1;
    container.innerHTML = entries.map((entry) => {
        const count = Number(entry.count || 0);
        const percentage = Math.max(0, Math.min(100, (count / denominator) * 100));
        return `
            <div class="breakdown-row">
                <div class="breakdown-label">
                    <span>${escapeHtml(entry.label)}</span>
                    <strong>${count}</strong>
                </div>
                <div class="progress-track" aria-label="${escapeHtml(entry.label)}: ${count}">
                    <span class="progress-fill" style="width: ${percentage.toFixed(1)}%"></span>
                </div>
            </div>
        `;
    }).join("");
}

async function refreshAnalyticsDashboard() {
    const button = document.getElementById("refreshAnalyticsBtn");
    const oldText = button.textContent;
    button.disabled = true;
    button.textContent = "Refreshing...";
    try {
        await Promise.all([loadAnalytics(), loadSavedTrips(), loadBucketConsole()]);
    } catch (error) {
        showError(`Could not refresh analytics: ${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = oldText;
    }
}

async function loadBucketConsole() {
    const response = await fetch("/api/storage/console");
    const data = await response.json();
    const consoleData = data.bucket || { objects: [] };
    const list = consoleData.objects || [];
    const container = document.getElementById("bucketConsole");

    if (!list.length) {
        container.innerHTML = '<div class="empty-state">No stored objects yet. Plans are saved to the simulated trip-planner-results bucket after generation.</div>';
        return;
    }

    const grouped = {};
    list.forEach((entry) => {
        grouped[entry.trip_id] = grouped[entry.trip_id] || [];
        grouped[entry.trip_id].push(entry.key);
    });

    container.innerHTML = Object.entries(grouped).map(([tripId, keys]) => `
        <div class="bucket-section">
            <div class="bucket-header">${tripId}</div>
            <ul>
                ${keys.map((key) => `<li>${key}</li>`).join("")}
            </ul>
        </div>
    `).join("");
}

async function refreshStorageDashboard() {
    await Promise.all([loadSavedTrips(), loadAnalytics(), loadBucketConsole()]);
}

async function searchSavedTrips() {
    await loadSavedTrips();
}

async function openTrip(tripId, version = null) {
    const params = new URLSearchParams();
    if (version) params.set("version", String(version));
    const response = await fetch(`/api/trips/${tripId}?${params.toString()}`);
    const data = await response.json();
    const trip = data.trip || {};
    const answer = trip.summary?.answer || trip.raw_data?.trip_summary?.answer || trip.raw_data?.final_itinerary || "Stored trip details are available.";
    showResult(String(answer), currentThreadId || tripId, tripId);
}

async function downloadStoredTrip(tripId, output = "json", version = null) {
    const params = new URLSearchParams({ output });
    if (version) params.set("version", String(version));
    const response = await fetch(`/api/trips/${tripId}/download?${params.toString()}`);
    const data = await response.json();
    const payload = data.content || {};
    const fileName = output === "itinerary" ? `${tripId}-itinerary.json` : `${tripId}-${output}.json`;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

async function deleteStoredTrip(tripId) {
    const confirmed = window.confirm(`Delete trip ${tripId}? This removes all stored objects and versions.`);
    if (!confirmed) return;

    const response = await fetch(`/api/trips/${tripId}`, { method: "DELETE" });
    const data = await response.json();
    if (data.success) {
        await refreshStorageDashboard();
        showError(`Trip ${tripId} was deleted.`);
    }
}

async function restoreTripVersion(tripId, version) {
    const response = await fetch(`/api/trips/${tripId}/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version }),
    });
    const data = await response.json();
    if (data.success) {
        await refreshStorageDashboard();
        showError(`Version ${version} restored for ${tripId}.`);
    }
}

async function sendMessage() {
    hideError();
    const input = document.getElementById("userInput");
    const message = input.value.trim();

    if (!message) {
        showError("Please enter your travel request first.");
        return;
    }

    setLoading(true);

    try {
        const response = await fetch("/api/travel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, thread_id: currentThreadId }),
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || "Something went wrong.");
        }

        currentThreadId = data.thread_id;
        localStorage.setItem("travel_thread_id", currentThreadId);
        showResult(data.answer, data.thread_id, data.trip_id);
        await refreshStorageDashboard();
    } catch (error) {
        showError(error.message);
    } finally {
        setLoading(false);
    }
}

function copyResult() {
    const resultBox = document.getElementById("resultBox");
    const text = resultBox.innerText;
    if (!text) return;

    navigator.clipboard.writeText(text)
        .then(() => {
            const copyBtn = document.querySelector(".copy-btn");
            const oldText = copyBtn.textContent;
            copyBtn.textContent = "Copied!";
            setTimeout(() => {
                copyBtn.textContent = oldText;
            }, 1400);
        })
        .catch(() => {
            showError("Could not copy result.");
        });
}

function downloadPDF() {
    const pdfContent = document.getElementById("pdfContent");
    if (!latestAnswerMarkdown || !pdfContent) {
        showError("No travel plan available to download.");
        return;
    }

    const downloadBtn = document.querySelector(".download-btn");
    const oldText = downloadBtn.textContent;
    downloadBtn.textContent = "Preparing PDF...";
    downloadBtn.disabled = true;

    const options = {
        margin: 0.5,
        filename: "ai-travel-plan.pdf",
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
        jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
        pagebreak: { mode: ["avoid-all", "css", "legacy"] },
    };

    html2pdf().set(options).from(pdfContent).save().then(() => {
        downloadBtn.textContent = oldText;
        downloadBtn.disabled = false;
    }).catch(() => {
        downloadBtn.textContent = oldText;
        downloadBtn.disabled = false;
        showError("Could not download PDF.");
    });
}

document.addEventListener("click", async (event) => {
    const target = event.target.closest("button[data-action]");
    if (!target) return;

    const action = target.dataset.action;
    const tripId = target.dataset.tripId;
    const version = target.dataset.version ? Number(target.dataset.version) : null;

    if (action === "view") {
        await openTrip(tripId);
    }

    if (action === "download") {
        await downloadStoredTrip(tripId, "json");
    }

    if (action === "versions") {
        await openTrip(tripId);
    }

    if (action === "delete") {
        await deleteStoredTrip(tripId);
    }

    if (action === "open-version") {
        await openTrip(tripId, version);
    }
});

document.addEventListener("keydown", function (event) {
    if (event.ctrlKey && event.key === "Enter") {
        sendMessage();
    }
});

window.addEventListener("DOMContentLoaded", async () => {
    await refreshStorageDashboard();
});