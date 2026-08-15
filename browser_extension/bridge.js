const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let classroomTabId = null;
let busy = false;

function log(msg) {
  const stamp = new Date().toLocaleTimeString();
  logEl.textContent = `[${stamp}] ${msg}\n` + logEl.textContent.slice(0, 8000);
}

async function cfg() {
  const data = await chrome.storage.local.get(["endpoint", "secret"]);
  return {
    endpoint: String(data.endpoint || "https://santa-rita-escolar-tcpb.onrender.com").replace(/\/$/, ""),
    secret: String(data.secret || "")
  };
}

async function bridgeFetch(path, options = {}) {
  const c = await cfg();
  if (!c.secret) throw new Error("Falta configurar CLASSROOM_BRIDGE_SECRET en la extensión.");
  const headers = new Headers(options.headers || {});
  headers.set("X-SieRoom-Bridge-Secret", c.secret);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const r = await fetch(`${c.endpoint}${path}`, { ...options, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok && r.status !== 207) throw new Error(data.error || `HTTP ${r.status}`);
  return { status: r.status, data };
}

async function waitTabComplete(tabId, timeoutMs = 45000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return tab;
    await sleep(400);
  }
  throw new Error("Classroom tardó demasiado en cargar la entrega.");
}

async function ensureClassroomTab(url) {
  if (classroomTabId) {
    try {
      await chrome.tabs.get(classroomTabId);
      await chrome.tabs.update(classroomTabId, { url, active: false });
      return waitTabComplete(classroomTabId);
    } catch (_) {
      classroomTabId = null;
    }
  }
  const tab = await chrome.tabs.create({ url, active: false });
  classroomTabId = tab.id;
  return waitTabComplete(classroomTabId);
}

async function sendToContent(tabId, payload, attempts = 20) {
  let lastErr = null;
  for (let i = 0; i < attempts; i++) {
    try {
      const response = await chrome.tabs.sendMessage(tabId, payload);
      if (response) return response;
    } catch (e) {
      lastErr = e;
    }
    await sleep(500);
  }
  throw lastErr || new Error("No pude contactar el content script de Classroom.");
}

async function complete(job, result) {
  return bridgeFetch(`/bridge/v1/jobs/${encodeURIComponent(job.id)}/complete`, {
    method: "POST", body: JSON.stringify(result || {})
  });
}

async function fail(job, error, detail = {}) {
  return bridgeFetch(`/bridge/v1/jobs/${encodeURIComponent(job.id)}/fail`, {
    method: "POST", body: JSON.stringify({ error: String(error), ...detail })
  });
}

async function processJob(job) {
  log(`Trabajo ${job.id}: abriendo entrega…`);
  try {
    const tab = await ensureClassroomTab(job.submission_url);
    // Da margen a los componentes dinámicos de Classroom.
    await sleep(1600);
    const result = await sendToContent(tab.id, {
      type: "SIEROOM_POST_PRIVATE_COMMENT",
      comment: job.comment
    });
    if (!result?.ok) throw new Error(result?.error || "Classroom no confirmó el comentario privado.");
    log(`Comentario publicado para ${job.submission_id}${result.alreadyPresent ? " (ya existía)" : ""}.`);
    const done = await complete(job, result);
    if (done.status === 207 || done.data?.partial) {
      log(`Comentario publicado, pero falló nota/devolución: ${done.data?.job?.error || "error de seguimiento"}`);
    } else {
      log(`Trabajo ${job.id} completado.`);
    }
  } catch (e) {
    const message = String(e?.message || e);
    log(`ERROR ${job.id}: ${message}`);
    try { await fail(job, message); } catch (_) {}
  }
}

async function poll() {
  if (busy) return;
  busy = true;
  try {
    const c = await cfg();
    if (!c.secret) {
      statusEl.textContent = "Falta configurar el secreto del puente.";
      statusEl.className = "bad";
      return;
    }
    const st = await bridgeFetch("/bridge/v1/status");
    statusEl.textContent = `Conectado a SieRoom · cola ${JSON.stringify(st.data.queue || {})}`;
    statusEl.className = "ok";
    const nxt = await bridgeFetch("/bridge/v1/next");
    if (nxt.data?.job) await processJob(nxt.data.job);
  } catch (e) {
    statusEl.textContent = `Sin conexión: ${String(e?.message || e)}`;
    statusEl.className = "bad";
  } finally {
    busy = false;
  }
}

document.getElementById("pollNow").addEventListener("click", poll);
setInterval(poll, 3000);
poll();
