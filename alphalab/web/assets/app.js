"use strict";

const state = {
  selectedExperimentId: null,
  jobsPollingHandle: null,
};

function byId(id) {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing DOM element: ${id}`);
  }
  return element;
}

function appendLog(message) {
  const log = byId("actionLog");
  const now = new Date().toISOString();
  const next = `[${now}] ${message}`;
  if (log.textContent && log.textContent.length > 0) {
    log.textContent = `${next}\n${log.textContent}`.slice(0, 8000);
  } else {
    log.textContent = next;
  }
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "succeeded") {
    return "status-succeeded";
  }
  if (normalized === "failed") {
    return "status-failed";
  }
  if (normalized === "running") {
    return "status-running";
  }
  return "status-queued";
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = payload?.message || payload?.detail || response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return payload;
}

function renderJobs(jobs) {
  const container = byId("jobsList");
  if (!Array.isArray(jobs) || jobs.length === 0) {
    container.innerHTML = '<div class="empty">No jobs yet.</div>';
    return;
  }

  container.innerHTML = jobs
    .map((job) => {
      const chipClass = statusClass(job.status);
      const errorText =
        job.error && job.error.message
          ? `<div class="meta"><strong>Error:</strong> ${job.error.message}</div>`
          : "";
      return `
        <div class="item">
          <div class="item-head">
            <span class="mono">${job.job_id}</span>
            <span class="status-chip ${chipClass}">${job.status}</span>
          </div>
          <div class="meta">type=${job.job_type}</div>
          <div class="meta">submitted=${job.submitted_at}</div>
          ${errorText}
        </div>
      `;
    })
    .join("");
}

function renderExperiments(experiments) {
  const container = byId("experimentsList");
  if (!Array.isArray(experiments) || experiments.length === 0) {
    container.innerHTML = '<div class="empty">No experiments found.</div>';
    return;
  }

  container.innerHTML = experiments
    .map(
      (experiment) => `
      <div class="item">
        <button data-experiment-id="${experiment.experiment_id}">
          <div class="item-head">
            <span class="mono">${experiment.experiment_id}</span>
            <span class="meta">sharpe=${Number(experiment.sharpe_ratio).toFixed(3)}</span>
          </div>
          <div class="meta">${experiment.strategy_name}</div>
          <div class="meta">${experiment.timestamp}</div>
        </button>
      </div>
    `
    )
    .join("");

  container.querySelectorAll("button[data-experiment-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const experimentId = button.getAttribute("data-experiment-id");
      if (!experimentId) {
        return;
      }
      await loadExperimentDetail(experimentId);
    });
  });
}

function renderMetricGrid(metrics) {
  const entries = Object.entries(metrics || {}).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) {
    return '<div class="empty">No metrics available.</div>';
  }

  const cells = entries
    .map(([name, value]) => {
      const numeric = Number(value);
      const display = Number.isFinite(numeric) ? numeric.toFixed(6) : String(value);
      return `
        <div class="metric-cell">
          <div class="metric-name">${name}</div>
          <div class="metric-value mono">${display}</div>
        </div>
      `;
    })
    .join("");
  return `<div class="metric-grid">${cells}</div>`;
}

function renderArtifacts(paths) {
  const list = byId("artifactsList");
  if (!Array.isArray(paths) || paths.length === 0) {
    list.innerHTML = "<li class='empty'>No artifacts.</li>";
    return;
  }

  list.innerHTML = paths
    .map((path) => `<li><a href="${path}" target="_blank" rel="noreferrer noopener">${path}</a></li>`)
    .join("");
}

async function loadHealth() {
  const badge = byId("healthBadge");
  try {
    const payload = await fetchJson("/health");
    badge.textContent = `API: ${payload.status}`;
    badge.className = "health-badge status-succeeded";
  } catch (error) {
    badge.textContent = `API error`;
    badge.className = "health-badge status-failed";
    appendLog(`Health check failed: ${error.message}`);
  }
}

function currentDbPath() {
  return byId("dbPath").value.trim();
}

async function refreshJobs() {
  try {
    const jobs = await fetchJson("/jobs?limit=50");
    renderJobs(jobs);
  } catch (error) {
    appendLog(`Failed to refresh jobs: ${error.message}`);
  }
}

async function refreshExperiments() {
  const dbPath = encodeURIComponent(currentDbPath());
  try {
    const experiments = await fetchJson(`/experiments?db_path=${dbPath}&limit=50`);
    renderExperiments(experiments);
  } catch (error) {
    appendLog(`Failed to refresh experiments: ${error.message}`);
  }
}

async function loadExperimentDetail(experimentId) {
  const dbPath = encodeURIComponent(currentDbPath());
  const payload = await fetchJson(`/experiments/${encodeURIComponent(experimentId)}?db_path=${dbPath}`);

  state.selectedExperimentId = payload.experiment_id;
  byId("enqueueRobustnessBtn").disabled = false;
  byId("detailEmpty").classList.add("hidden");
  byId("detailContent").classList.remove("hidden");
  byId("detailId").textContent = payload.experiment_id;
  byId("detailStrategy").textContent = payload.strategy_name;
  byId("detailTimestamp").textContent = payload.timestamp;
  byId("metricsTable").innerHTML = renderMetricGrid(payload.metrics);
  byId("configYaml").textContent = payload.config_yaml;
  renderArtifacts(payload.artifact_paths);
}

async function enqueueRun() {
  const payload = {
    config_path: byId("configPath").value.trim(),
    db_path: currentDbPath(),
  };
  try {
    const response = await fetchJson("/jobs/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    appendLog(`Queued run ${response.job_id}`);
    await Promise.all([refreshJobs(), refreshExperiments()]);
  } catch (error) {
    appendLog(`Queue run failed: ${error.message}`);
  }
}

async function enqueueRobustness() {
  if (!state.selectedExperimentId) {
    appendLog("Select an experiment first.");
    return;
  }
  const payload = {
    experiment_id: state.selectedExperimentId,
    db_path: currentDbPath(),
  };
  try {
    const response = await fetchJson("/jobs/robustness", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    appendLog(`Queued robustness ${response.job_id} for ${state.selectedExperimentId}`);
    await refreshJobs();
  } catch (error) {
    appendLog(`Queue robustness failed: ${error.message}`);
  }
}

async function refreshAll() {
  await Promise.all([loadHealth(), refreshJobs(), refreshExperiments()]);
}

function installHandlers() {
  byId("enqueueRunBtn").addEventListener("click", enqueueRun);
  byId("refreshAllBtn").addEventListener("click", refreshAll);
  byId("refreshJobsBtn").addEventListener("click", refreshJobs);
  byId("refreshExperimentsBtn").addEventListener("click", refreshExperiments);
  byId("enqueueRobustnessBtn").addEventListener("click", enqueueRobustness);
}

async function boot() {
  installHandlers();
  await refreshAll();

  state.jobsPollingHandle = window.setInterval(async () => {
    await refreshJobs();
  }, 2000);
}

void boot();
