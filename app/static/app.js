const pipelineRoot = document.getElementById("pipeline");
const activityLog = document.getElementById("activityLog");
const candidateBoard = document.getElementById("candidateBoard");
const heroStages = document.getElementById("heroStages");
const heroCandidates = document.getElementById("heroCandidates");

const REFRESH_INTERVAL_MS = 15000;

const stageOrder = ["Applied", "Screening", "Interview", "Offer"];

const state = {
  logs: [],
  candidates: [],
  pipelineCounts: {
    Applied: 0,
    Screening: 0,
    Interview: 0,
    Offer: 0,
  },
};

function renderStages(root, compact) {
  if (!root) return;
  root.innerHTML = "";
  stageOrder.forEach((stage) => {
    const cell = document.createElement("article");
    cell.className = compact ? "hero-stage" : "pipeline-stage";
    const count = state.pipelineCounts[stage] ?? 0;
    const value = document.createElement("strong");
    value.textContent = count;
    const name = document.createElement("span");
    name.className = "stage-name";
    name.textContent = stage;
    cell.append(value, name);
    root.appendChild(cell);
  });
}

function candidateRow(candidate) {
  const row = document.createElement("div");
  row.className = "candidate-row";
  row.dataset.stage = candidate.stage;
  const name = document.createElement("strong");
  name.textContent = candidate.name;
  const role = document.createElement("span");
  role.className = "candidate-role";
  role.textContent = candidate.job_title;
  const badge = document.createElement("span");
  badge.className = "candidate-badge";
  badge.textContent =
    candidate.score != null
      ? `${candidate.stage} ${candidate.score}/10`
      : candidate.stage;
  row.append(name, role, badge);
  return row;
}

function renderCandidates(root, limit, emptyMessage) {
  if (!root) return;
  root.innerHTML = "";
  if (!state.candidates.length) {
    const empty = document.createElement("p");
    empty.className = "candidate-empty";
    empty.textContent = emptyMessage;
    root.appendChild(empty);
    return;
  }
  state.candidates.slice(0, limit).forEach((candidate) => {
    root.appendChild(candidateRow(candidate));
  });
}

function renderActivity() {
  activityLog.innerHTML = "";
  if (!state.logs.length) {
    const row = document.createElement("div");
    row.className = "activity-item";
    const time = document.createElement("time");
    time.textContent = "Waiting";
    const message = document.createElement("p");
    message.textContent = "No activity recorded yet. Run the demo above.";
    row.append(time, message);
    activityLog.appendChild(row);
    return;
  }
  [...state.logs].reverse().forEach((entry) => {
    const row = document.createElement("div");
    row.className = "activity-item";
    row.dataset.operation = entry.operation || "system";
    const timestamp = document.createElement("time");
    timestamp.textContent = new Date(entry.timestamp).toLocaleString();
    const message = document.createElement("p");
    message.textContent = entry.message || "";
    row.append(timestamp, message);
    activityLog.appendChild(row);
  });
}

function renderAll() {
  renderStages(pipelineRoot, false);
  renderStages(heroStages, true);
  renderCandidates(candidateBoard, 8, "No candidates screened yet.");
  renderCandidates(heroCandidates, 3, "Nothing yet. Run the demo below.");
  renderActivity();
}

async function refreshLogs() {
  try {
    const [logsResponse, candidatesResponse] = await Promise.all([
      fetch("/api/logs"),
      fetch("/api/candidates"),
    ]);
    const payload = await logsResponse.json();
    state.logs = payload.logs ?? [];
    if (candidatesResponse.ok) {
      const candidatesPayload = await candidatesResponse.json();
      state.candidates = candidatesPayload.candidates ?? [];
      state.pipelineCounts = {
        ...state.pipelineCounts,
        ...(candidatesPayload.pipeline_counts ?? {}),
      };
    }
    renderAll();
  } catch (error) {
    console.error("Failed to refresh pipeline data", error);
  }
}

function prettyResult(payload) {
  return JSON.stringify(payload, null, 2);
}

async function submitJson({ url, data, outputId, button }) {
  const output = document.getElementById(outputId);
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Working...";
  output.classList.remove("is-error");
  output.textContent = "Running request...";

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Request failed");
    }
    output.textContent = prettyResult(payload);
    await refreshLogs();
  } catch (error) {
    output.classList.add("is-error");
    output.textContent = `Error: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

document.getElementById("setupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const data = Object.fromEntries(new FormData(form).entries());
  await submitJson({ url: "/api/setup", data, outputId: "setupResult", button });
});

document.getElementById("jobForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const raw = Object.fromEntries(new FormData(form).entries());
  const data = {
    ...raw,
    headcount: Number(raw.headcount),
  };
  await submitJson({ url: "/api/add-job", data, outputId: "jobResult", button });
});

document.getElementById("candidateForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const data = Object.fromEntries(new FormData(form).entries());
  await submitJson({ url: "/api/screen-candidate", data, outputId: "candidateResult", button });
});

document.getElementById("offerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  const data = Object.fromEntries(new FormData(form).entries());
  await submitJson({ url: "/api/generate-offer", data, outputId: "offerResult", button });
});

document.getElementById("refreshLogsButton").addEventListener("click", refreshLogs);

// Scroll reveals, skipped entirely under reduced motion.
if (window.matchMedia("(prefers-reduced-motion: no-preference)").matches) {
  const revealables = document.querySelectorAll(".how, .demo, .activity");
  revealables.forEach((el) => el.classList.add("reveal"));
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  revealables.forEach((el) => observer.observe(el));
}

renderAll();
refreshLogs();
setInterval(refreshLogs, REFRESH_INTERVAL_MS);
