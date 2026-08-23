const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let classroomTabId = null;
let busy = false;
let resetGeneration = 0;
let lastJobStartedAt = 0;

class BridgeResetError extends Error {}

async function getActiveTabId() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs?.[0]?.id ?? null;
  } catch (_) {
    return null;
  }
}

async function activateTab(tabId) {
  if (!tabId) return;
  try { await chrome.tabs.update(tabId, { active: true }); } catch (_) {}
}

function log(msg) {
  const stamp = new Date().toLocaleTimeString();
  logEl.textContent = `[${stamp}] ${msg}\n` + logEl.textContent.slice(0, 10000);
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
  const r = await fetch(`${c.endpoint}${path}`, { ...options, headers, cache: "no-store" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok && r.status !== 207) throw new Error(data.error || `HTTP ${r.status}`);
  return { status: r.status, data };
}

function workRemaining(queue = {}) {
  if (Number.isFinite(Number(queue.work_remaining))) return Number(queue.work_remaining);
  return Number(queue.queued || 0) + Number(queue.claimed || 0);
}

function friendlyQueue(queue = {}) {
  return `pendientes ${Number(queue.queued || 0)} · en proceso ${Number(queue.claimed || 0)} · restantes ${workRemaining(queue)}`;
}

function assertGeneration(generation) {
  if (generation !== resetGeneration) throw new BridgeResetError("Trabajo interrumpido por RESET.");
}

async function waitTabComplete(tabId, timeoutMs = 45000, generation = resetGeneration) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    assertGeneration(generation);
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return tab;
    await sleep(400);
  }
  throw new Error("Classroom tardó demasiado en cargar la entrega.");
}

async function ensureClassroomTab(url, generation) {
  if (classroomTabId) {
    try {
      await chrome.tabs.get(classroomTabId);
      await chrome.tabs.update(classroomTabId, { url, active: true });
      const tab = await waitTabComplete(classroomTabId, 45000, generation);
      assertGeneration(generation);
      await activateTab(classroomTabId);
      await sleep(2200);
      assertGeneration(generation);
      return tab;
    } catch (e) {
      if (e instanceof BridgeResetError) throw e;
      classroomTabId = null;
    }
  }
  const tab = await chrome.tabs.create({ url, active: true });
  classroomTabId = tab.id;
  const complete = await waitTabComplete(classroomTabId, 45000, generation);
  assertGeneration(generation);
  await activateTab(classroomTabId);
  await sleep(2200);
  assertGeneration(generation);
  return complete;
}

function promiseTimeout(promise, ms, message) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(message)), ms))
  ]);
}

async function sendToContent(tabId, payload, attempts = 12, generation = resetGeneration) {
  let lastErr = null;
  for (let i = 0; i < attempts; i++) {
    assertGeneration(generation);
    try {
      const response = await promiseTimeout(
        chrome.tabs.sendMessage(tabId, payload),
        65000,
        "Classroom tardó demasiado en procesar el panel de comentarios privados."
      );
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

async function processJob(job, generation) {
  log(`Trabajo ${job.id}: abriendo entrega…`);
  const previousActiveTabId = await getActiveTabId();
  lastJobStartedAt = Date.now();
  try {
    assertGeneration(generation);
    const tab = await ensureClassroomTab(job.submission_url, generation);
    log(`Trabajo ${job.id}: Classroom activo; esperando panel lateral…`);
    await sleep(2600);
    assertGeneration(generation);

    const isRead = job.operation === "read_private_comments";
    const result = await sendToContent(tab.id, isRead ? {
      type: "SIEROOM_READ_PRIVATE_COMMENTS"
    } : {
      type: "SIEROOM_POST_PRIVATE_COMMENT",
      comment: job.comment
    }, 12, generation);
    assertGeneration(generation);

    if (!result?.ok) {
      throw new Error(result?.error || (isRead
        ? "Classroom no devolvió los comentarios privados."
        : "Classroom no confirmó el comentario privado."));
    }
    if (isRead) {
      log(`Comentarios leídos para ${job.submission_id}: ${Number(result.count || 0)}.`);
    } else {
      log(`Comentario publicado para ${job.submission_id}${result.alreadyPresent ? " (ya existía)" : ""}.`);
    }
    const done = await complete(job, result);
    assertGeneration(generation);

    if (!isRead && (done.status === 207 || done.data?.partial)) {
      log(`Comentario publicado, pero falló nota/devolución: ${done.data?.job?.error || "error de seguimiento"}`);
    } else {
      log(`Trabajo ${job.id} completado.`);
    }
  } catch (e) {
    if (e instanceof BridgeResetError) {
      log(`Trabajo ${job.id}: liberado por RESET; volverá a la cola.`);
      return;
    }
    const message = String(e?.message || e);
    log(`ERROR ${job.id}: ${message}`);
    try { await fail(job, message); } catch (_) {}
  } finally {
    lastJobStartedAt = 0;
    if (previousActiveTabId && previousActiveTabId !== classroomTabId) {
      await sleep(350);
      await activateTab(previousActiveTabId);
    }
  }
}

async function resetQueue({ retryFailed = false, fromButton = true } = {}) {
  resetGeneration += 1;
  const myGeneration = resetGeneration;
  busy = false;
  statusEl.textContent = "Reiniciando y desatascando cola…";
  statusEl.className = "bad";
  log("RESET solicitado: liberando trabajos en proceso y reiniciando el ciclo local.");

  const r = await bridgeFetch("/bridge/v1/reset", {
    method: "POST",
    body: JSON.stringify({ retry_failed: Boolean(retryFailed) })
  });

  // Forzamos una pestaña limpia para el siguiente trabajo sin tocar las pestañas
  // normales del usuario. La pestaña controlada por el bridge se reutilizará.
  if (classroomTabId) {
    try { await chrome.tabs.reload(classroomTabId); } catch (_) {}
  }

  const q = r.data?.queue || {};
  statusEl.textContent = `RESET correcto · ${friendlyQueue(q)} · procesando de nuevo…`;
  statusEl.className = "ok";
  log(`RESET terminado. Liberados ${r.data?.released_count || 0}; ${friendlyQueue(q)}.`);

  // El siguiente tick no espera 3 s: empieza a drenar inmediatamente.
  setTimeout(() => poll(true), 80);
  return { generation: myGeneration, response: r.data };
}

async function drainQueue(generation, maxJobs = 50) {
  let processed = 0;
  while (processed < maxJobs) {
    assertGeneration(generation);
    const nxt = await bridgeFetch("/bridge/v1/next");
    const job = nxt.data?.job;
    if (!job) break;
    await processJob(job, generation);
    assertGeneration(generation);
    processed += 1;
    // Pequeñísima pausa para que la UI y Chrome respiren, sin meter 3 s por trabajo.
    await sleep(180);
  }
  return processed;
}

async function poll(force = false) {
  if (busy && !force) return;
  if (busy && force) resetGeneration += 1;
  busy = true;
  const generation = resetGeneration;
  try {
    const c = await cfg();
    if (!c.secret) {
      statusEl.textContent = "Falta configurar el secreto del puente.";
      statusEl.className = "bad";
      return;
    }

    const st = await bridgeFetch("/bridge/v1/status");
    const q = st.data.queue || {};
    statusEl.textContent = `Conectado a SieRoom · extensión ${chrome.runtime.getManifest().version} · ${friendlyQueue(q)}`;
    statusEl.className = "ok";

    const processed = await drainQueue(generation, 50);
    if (processed > 0) {
      const after = await bridgeFetch("/bridge/v1/status");
      statusEl.textContent = `Conectado a SieRoom · extensión ${chrome.runtime.getManifest().version} · ${friendlyQueue(after.data.queue || {})}`;
      log(`Ciclo terminado: ${processed} trabajo(s) procesado(s) sin pausa artificial entre trabajos.`);
    }
  } catch (e) {
    if (e instanceof BridgeResetError) return;
    statusEl.textContent = `Sin conexión: ${String(e?.message || e)}`;
    statusEl.className = "bad";
  } finally {
    if (generation === resetGeneration) busy = false;
  }
}

document.getElementById("pollNow").addEventListener("click", () => poll(true));
document.getElementById("resetQueue").addEventListener("click", async () => {
  try { await resetQueue({ retryFailed: false, fromButton: true }); }
  catch (e) {
    statusEl.textContent = `RESET falló: ${String(e?.message || e)}`;
    statusEl.className = "bad";
    log(`RESET ERROR: ${String(e?.message || e)}`);
  }
});

// Watchdog: si una operación local lleva demasiado tiempo, la liberamos en el
// servidor y reiniciamos el ciclo. Esto evita tener que pulsar RESET en la mayoría
// de atascos temporales.
setInterval(async () => {
  if (!busy || !lastJobStartedAt) return;
  if (Date.now() - lastJobStartedAt < 120000) return;
  try {
    log("WATCHDOG: trabajo local >120 s. Ejecutando RESET automático.");
    await resetQueue({ retryFailed: false, fromButton: false });
  } catch (e) {
    log(`WATCHDOG RESET ERROR: ${String(e?.message || e)}`);
  }
}, 5000);

setInterval(() => poll(false), 2500);
poll(false);
