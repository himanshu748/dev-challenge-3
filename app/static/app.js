const pipelineRoot = document.getElementById("pipeline");
const activityLog = document.getElementById("activityLog");

const stageOrder = ["Applied", "Screening", "Interview", "Offer"];
const stageMeta = {
  Applied: { code: "Intake", note: "Fresh inbound candidates" },
  Screening: { code: "Review", note: "AI fit evaluation in motion" },
  Interview: { code: "Loop", note: "Team conversation underway" },
  Offer: { code: "Close", note: "Offer package prepared" },
};

const state = {
  logs: [],
  pipelineCounts: {
    Applied: 0,
    Screening: 0,
    Interview: 0,
    Offer: 0,
  },
};

function parsePipelineFromLogs(logs) {
  for (let index = logs.length - 1; index >= 0; index -= 1) {
    const message = logs[index]?.message ?? "";
    const match = message.match(/\[PIPELINE\]\s*(\{.*\})/);
    if (!match) continue;
    try {
      return { ...state.pipelineCounts, ...JSON.parse(match[1]) };
    } catch {
      return state.pipelineCounts;
    }
  }
  return state.pipelineCounts;
}

function renderPipeline() {
  pipelineRoot.innerHTML = "";
  stageOrder.forEach((stage) => {
    const card = document.createElement("article");
    card.className = "pipeline-stage";
    const count = state.pipelineCounts[stage] ?? 0;
    const meta = stageMeta[stage];
    card.innerHTML = `
      <span class="stage-code">${meta.code}</span>
      <p class="eyebrow muted">${stage}</p>
      <strong>${count}</strong>
      <span class="stage-volume">${count === 1 ? "candidate in stage" : "candidates in stage"}</span>
      <small class="stage-note">${meta.note}</small>
    `;
    pipelineRoot.appendChild(card);
  });
}

function renderActivity() {
  activityLog.innerHTML = "";
  if (!state.logs.length) {
    activityLog.innerHTML = '<div class="activity-item"><time>Waiting</time><p>No activity recorded yet.</p></div>';
    return;
  }
  [...state.logs].reverse().forEach((entry) => {
    const row = document.createElement("div");
    row.className = "activity-item";
    row.dataset.operation = entry.operation || "system";
    const timestamp = new Date(entry.timestamp).toLocaleString();
    row.innerHTML = `<time>${timestamp}</time><p>${entry.message}</p>`;
    activityLog.appendChild(row);
  });
}

async function refreshLogs() {
  try {
    const response = await fetch("/api/logs");
    const payload = await response.json();
    state.logs = payload.logs ?? [];
    state.pipelineCounts = parsePipelineFromLogs(state.logs);
    renderPipeline();
    renderActivity();
  } catch (error) {
    console.error("Failed to refresh logs", error);
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

refreshLogs();
