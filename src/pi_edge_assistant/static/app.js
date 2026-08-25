const $ = (selector) => document.querySelector(selector);
const state = { token: localStorage.getItem("edgeToken") || "", recording: false, audioUrls: [] };

function headers() { return { "Content-Type": "application/json", "X-Access-Token": state.token }; }

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || response.statusText);
  }
  if (response.status === 204) return null;
  return response.json();
}

function setNotice(message, error = false) {
  const target = $("#notice");
  target.textContent = message || "";
  target.style.color = error ? "var(--danger)" : "var(--warning)";
}

function renderStatus(status) {
  const badge = $("#state");
  badge.textContent = status.state;
  badge.className = `state ${status.state.toLowerCase()}`;
  $("#transcript").textContent = status.transcript || "—";
  $("#response").textContent = status.response || "—";
  $("#model").textContent = status.model || "—";
  if (status.error) setNotice(status.error, true);
  const metrics = status.metrics || {};
  const metricRows = {
    "CPU": `${metrics.cpu_percent ?? "—"}%`,
    "内存": `${metrics.memory_used_mb ?? "—"} MB (${metrics.memory_percent ?? "—"}%)`,
    "Swap": `${metrics.swap_used_mb ?? "—"} MB`,
    "温度": metrics.temperature_c == null ? "—" : `${metrics.temperature_c} °C`,
    "磁盘可用": `${metrics.disk_free_gb ?? "—"} GB`,
  };
  $("#metrics").innerHTML = Object.entries(metricRows).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  $("#timings").textContent = Object.entries(status.timings || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "尚无耗时数据";
  state.audioUrls = status.audio_urls || state.audioUrls;
  $("#browser-playback").disabled = state.audioUrls.length === 0;
}

async function connect(event) {
  if (event) event.preventDefault();
  state.token = $("#token").value.trim();
  try {
    const status = await api("/api/status");
    localStorage.setItem("edgeToken", state.token);
    $("#login").classList.add("hidden");
    $("#workspace").classList.remove("hidden");
    renderStatus(status);
    connectEvents();
    await loadHistory();
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
}

function connectEvents() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/events`);
  socket.onopen = () => socket.send(JSON.stringify({ token: state.token }));
  socket.onmessage = async ({ data }) => {
    const event = JSON.parse(data);
    if (event.type === "status") renderStatus(event.status);
    if (event.type === "image") {
      $("#image").src = event.data_url;
      $("#image").style.display = "block";
      $("#image-placeholder").style.display = "none";
    }
    if (event.type === "audio") {
      state.audioUrls = event.urls;
      $("#browser-playback").disabled = false;
    }
    if (event.type === "warning") setNotice(event.message);
    if (event.type === "failed") setNotice(event.message, true);
    if (event.type === "complete" || event.type === "failed") await loadHistory();
  };
  socket.onclose = () => setTimeout(connectEvents, 2500);
}

async function toggleRecording() {
  try {
    if (!state.recording) {
      await api("/api/recording/start", { method: "POST", body: JSON.stringify({ include_image: $("#include-image").checked }) });
      state.recording = true;
      $("#record").textContent = "停止并识别";
      $("#record").classList.add("active");
    } else {
      await api("/api/recording/stop", { method: "POST" });
      state.recording = false;
      $("#record").textContent = "开始说话";
      $("#record").classList.remove("active");
    }
  } catch (error) { setNotice(error.message, true); }
}

async function sendChat(event) {
  event.preventDefault();
  const text = $("#text").value.trim();
  if (!text) return;
  try {
    await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ text, include_image: $("#include-image").checked, compare_model: $("#compare-model").checked }),
    });
    $("#text").value = "";
    setNotice("");
  } catch (error) { setNotice(error.message, true); }
}

async function browserPlayback() {
  for (const url of state.audioUrls) {
    const response = await fetch(url, { headers: { "X-Access-Token": state.token } });
    if (!response.ok) continue;
    const audio = new Audio(URL.createObjectURL(await response.blob()));
    await new Promise((resolve) => { audio.onended = resolve; audio.onerror = resolve; audio.play().catch(resolve); });
  }
}

async function loadHistory() {
  const items = await api("/api/history?limit=30");
  $("#history").innerHTML = items.length ? items.map((item) => `
    <div class="history-item">
      <small>${new Date(item.created_at).toLocaleString()} · ${item.model} · ${item.error_code || "ok"}</small>
      <p>${escapeHtml(item.transcript)}</p>
      <p class="muted">${escapeHtml(item.response)}</p>
    </div>`).join("") : '<p class="muted">暂无记录</p>';
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value || "";
  return node.innerHTML;
}

$("#login-form").addEventListener("submit", connect);
$("#record").addEventListener("click", toggleRecording);
$("#chat-form").addEventListener("submit", sendChat);
$("#stop-playback").addEventListener("click", () => api("/api/playback/stop", { method: "POST" }).catch((e) => setNotice(e.message, true)));
$("#browser-playback").addEventListener("click", browserPlayback);
$("#clear-history").addEventListener("click", async () => { if (confirm("清空全部文本与指标历史？")) { await api("/api/history", { method: "DELETE" }); await loadHistory(); } });
$("#token").value = state.token;
if (state.token) connect();
