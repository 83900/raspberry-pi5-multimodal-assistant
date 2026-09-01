const $ = (selector) => document.querySelector(selector);
const displayMode = new URLSearchParams(location.search).get("display") === "1";
const state = {
  token: displayMode ? "" : (localStorage.getItem("edgeToken") || ""),
  recording: false,
  audioUrls: [],
  socket: null,
  reconnectTimer: null,
  wakeLock: null,
  assistantState: "IDLE",
};

if (displayMode) document.body.classList.add("display-mode");

function headers() {
  return { "Content-Type": "application/json", "X-Access-Token": state.token };
}

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

function updateInteractionControls(status) {
  const isRecording = status.state === "RECORDING";
  const isIdle = status.state === "IDLE" || status.state === "ERROR";
  state.recording = isRecording;
  $("#record").disabled = !isIdle && !isRecording;
  $("#record").textContent = isRecording ? "停止并识别" : "开始说话";
  $("#record").classList.toggle("active", isRecording);
  $("#include-image").disabled = !isIdle;
  $("#compare-model").disabled = !isIdle;
  $("#text").disabled = !isIdle;
  $("#send-text").disabled = !isIdle;
}

function renderStatus(status) {
  state.assistantState = status.state;
  const badge = $("#state");
  badge.textContent = status.state;
  badge.className = `state ${status.state.toLowerCase()}`;
  $("#transcript").textContent = status.transcript || "—";
  $("#response").textContent = status.response || "—";
  $("#model").textContent = status.model || "—";
  $("#header-model").textContent = status.model || "—";
  if (status.error) setNotice(status.error, true);
  const metrics = status.metrics || {};
  const temperature = metrics.temperature_c;
  $("#header-temp").textContent = temperature == null ? "— °C" : `${temperature} °C`;
  $("#header-temp").classList.toggle("warning", temperature != null && temperature >= 75);
  const metricRows = {
    "CPU": `${metrics.cpu_percent ?? "—"}%`,
    "内存": `${metrics.memory_used_mb ?? "—"} MB (${metrics.memory_percent ?? "—"}%)`,
    "Swap": `${metrics.swap_used_mb ?? "—"} MB`,
    "温度": temperature == null ? "—" : `${temperature} °C`,
    "磁盘可用": `${metrics.disk_free_gb ?? "—"} GB`,
  };
  $("#metrics").innerHTML = Object.entries(metricRows).map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("");
  $("#timings").textContent = Object.entries(status.timings || {}).map(([key, value]) => `${key}: ${value}`).join(" · ") || "尚无耗时数据";
  state.audioUrls = status.audio_urls || state.audioUrls;
  $("#browser-playback").disabled = state.audioUrls.length === 0;
  updateInteractionControls(status);
}

async function acquireDisplaySession() {
  const response = await fetch("/api/display/session", { method: "POST" });
  if (!response.ok) throw new Error("本机显示会话不可用");
  state.token = (await response.json()).token;
}

async function connect(event) {
  if (event) event.preventDefault();
  if (!displayMode) state.token = $("#token").value.trim();
  try {
    if (displayMode) await acquireDisplaySession();
    const status = await api("/api/status");
    if (!displayMode) localStorage.setItem("edgeToken", state.token);
    $("#login").classList.add("hidden");
    $("#workspace").classList.remove("hidden");
    renderStatus(status);
    setNotice("");
    connectEvents();
    await loadHistory();
  } catch (error) {
    if (displayMode) {
      $("#login").classList.add("hidden");
      $("#workspace").classList.remove("hidden");
      setNotice("正在连接本机服务…", true);
      scheduleReconnect(true);
    } else {
      $("#login-error").textContent = error.message;
    }
  }
}

function scheduleReconnect(rebootstrap = false) {
  if (state.reconnectTimer) return;
  state.reconnectTimer = setTimeout(async () => {
    state.reconnectTimer = null;
    if (displayMode || rebootstrap) await connect();
    else connectEvents();
  }, 2500);
}

function connectEvents() {
  if (state.socket && state.socket.readyState < WebSocket.CLOSING) return;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/events`);
  state.socket = socket;
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
  socket.onclose = () => {
    if (state.socket === socket) state.socket = null;
    if (displayMode) setNotice("正在连接本机服务…", true);
    scheduleReconnect(displayMode);
  };
  socket.onerror = () => socket.close();
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
  } catch (error) {
    setNotice(error.message, true);
  }
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
    $("#chat-form").classList.remove("open");
    $("#toggle-text").setAttribute("aria-expanded", "false");
    setNotice("");
  } catch (error) {
    setNotice(error.message, true);
  }
}

async function browserPlayback() {
  for (const url of state.audioUrls) {
    const response = await fetch(url, { headers: { "X-Access-Token": state.token } });
    if (!response.ok) continue;
    const audio = new Audio(URL.createObjectURL(await response.blob()));
    await new Promise((resolve) => {
      audio.onended = resolve;
      audio.onerror = resolve;
      audio.play().catch(resolve);
    });
  }
}

async function loadHistory() {
  try {
    const items = await api("/api/history?limit=30");
    $("#history").innerHTML = items.length ? items.map((item) => `
      <div class="history-item">
        <small>${new Date(item.created_at).toLocaleString()} · ${escapeHtml(item.model)} · ${escapeHtml(item.error_code || "ok")}</small>
        <p>${escapeHtml(item.transcript)}</p>
        <p class="muted">${escapeHtml(item.response)}</p>
      </div>`).join("") : '<p class="muted">暂无记录</p>';
  } catch (error) {
    if (!displayMode) setNotice(error.message, true);
  }
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value || "";
  return node.innerHTML;
}

function selectTab(name) {
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.tabPanel === name));
  document.querySelectorAll("[data-tab]").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  if (name === "history") loadHistory();
}

async function requestWakeLock() {
  if (!displayMode || !navigator.wakeLock || document.visibilityState !== "visible") return;
  try {
    state.wakeLock = await navigator.wakeLock.request("screen");
    state.wakeLock.addEventListener("release", () => {
      state.wakeLock = null;
      if (document.visibilityState === "visible") setTimeout(requestWakeLock, 1000);
    }, { once: true });
  } catch (_) {
    state.wakeLock = null;
  }
}

async function exitDisplay() {
  const busy = !["IDLE", "ERROR"].includes(state.assistantState);
  if (busy && !confirm("当前任务尚未完成，确认退出界面？任务会继续在后台运行。")) return;
  try {
    await api("/api/display/exit", {
      method: "POST",
      body: JSON.stringify({ confirm: busy }),
    });
    setNotice("正在退出…");
  } catch (error) {
    if (error.message === "interaction is still running") {
      if (confirm("任务状态刚刚发生变化，仍然确认退出界面？")) {
        await api("/api/display/exit", { method: "POST", body: JSON.stringify({ confirm: true }) });
      }
      return;
    }
    setNotice(error.message, true);
  }
}

$("#login-form").addEventListener("submit", connect);
$("#record").addEventListener("click", toggleRecording);
$("#chat-form").addEventListener("submit", sendChat);
$("#stop-playback").addEventListener("click", () => api("/api/playback/stop", { method: "POST" }).catch((error) => setNotice(error.message, true)));
$("#browser-playback").addEventListener("click", browserPlayback);
$("#exit-display").addEventListener("click", exitDisplay);
$("#toggle-text").addEventListener("click", () => {
  const open = $("#chat-form").classList.toggle("open");
  $("#toggle-text").setAttribute("aria-expanded", String(open));
  if (open) $("#text").focus();
});
$("#clear-history").addEventListener("click", async () => {
  if (confirm("清空全部文本与指标历史？")) {
    await api("/api/history", { method: "DELETE" });
    await loadHistory();
  }
});
document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tab)));
document.addEventListener("visibilitychange", requestWakeLock);

$("#token").value = state.token;
if (displayMode) {
  requestWakeLock();
  connect();
} else if (state.token) {
  connect();
}
