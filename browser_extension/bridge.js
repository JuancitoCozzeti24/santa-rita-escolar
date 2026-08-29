const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SIEROOM_CONTENT_BUILD = "0.8.7-HF4-GRADE-TARGET";
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

async function isLeaderBridgeTab() {
  try {
    const current = await chrome.tabs.getCurrent();
    const bridgeUrl = chrome.runtime.getURL("bridge.html");
    const tabs = await chrome.tabs.query({ url: bridgeUrl + "*" });
    const leader = tabs
      .filter((tab) => Number.isInteger(tab.id))
      .sort((a, b) => a.id - b.id)[0];
    return Boolean(current?.id && leader?.id === current.id);
  } catch (_) {
    return true;
  }
}

function log(msg) {
  const stamp = new Date().toLocaleTimeString();
  logEl.textContent = `[${stamp}] ${msg}\n` + logEl.textContent.slice(0, 10000);
}

async function cfg() {
  const data = await chrome.storage.local.get(["endpoint", "teacherEmail", "secret"]);
  return {
    endpoint: String(data.endpoint || "https://santa-rita-escolar-tcpb.onrender.com").replace(/\/$/, ""),
    teacherEmail: String(data.teacherEmail || "").trim().toLowerCase(),
    secret: String(data.secret || "")
  };
}

class AccountMismatchError extends Error {
  constructor(message, detail = {}) {
    super(message);
    this.detail = detail;
  }
}

function addExpectedAccount(url, email) {
  try {
    const u = new URL(url);
    if (email) u.searchParams.set("authuser", email);
    return u.toString();
  } catch (_) {
    return url;
  }
}

async function checkAccountOnTab(tabId, expectedEmail, generation = resetGeneration) {
  if (!expectedEmail) throw new Error("Falta configurar el correo docente de Classroom.");
  assertGeneration(generation);

  let result = null;
  try {
    result = await sendToContent(tabId, {
      type: "SIEROOM_CHECK_ACCOUNT",
      expectedEmail
    }, 4, generation);
  } catch (_) {
    return { ok: null, reason: "content_script_not_ready", detectedEmails: [] };
  }

  if (result?.ok === false) {
    const detected = (result.detectedEmails || []).join(", ") || "otra cuenta";
    throw new AccountMismatchError(
      `Cuenta incorrecta en Classroom. Esperada: ${expectedEmail}. Detectada: ${detected}.`,
      result
    );
  }
  return result || { ok: null, detectedEmails: [] };
}

async function preflightAccount(expectedEmail, generation = resetGeneration) {
  if (!expectedEmail) throw new Error("Falta configurar el correo docente de Classroom.");

  const tabs = await chrome.tabs.query({ url: "https://classroom.google.com/*" });
  if (!tabs.length) {
    return {
      ok: false,
      missing: true,
      message: `Abre Google Classroom con ${expectedEmail} antes de iniciar la cola.`
    };
  }

  // Puede haber varias cuentas/ventanas de Classroom abiertas. No se bloquea
  // solo porque la primera pestaña pertenezca a otra cuenta: se exige encontrar
  // al menos una pestaña cuya cuenta ACTIVA coincida de forma positiva.
  const ordered = [...tabs].sort((a, b) => Number(Boolean(b.active)) - Number(Boolean(a.active)));
  const checked = [];
  for (const tab of ordered.slice(0, 8)) {
    try {
      const r = await checkAccountOnTab(tab.id, expectedEmail, generation);
      checked.push({ tabId: tab.id, result: r });
      if (r?.ok === true) return { ok: true, result: r, tabId: tab.id };
    } catch (e) {
      if (e instanceof AccountMismatchError) {
        checked.push({ tabId: tab.id, result: e.detail, mismatch: true });
        continue;
      }
      throw e;
    }
  }
  const detected = [...new Set(checked.flatMap((item) => item.result?.detectedEmails || []))];
  return {
    ok: false,
    mismatch: detected.length > 0,
    unverified: detected.length === 0,
    message: detected.length
      ? `Ninguna pestaña usa la cuenta docente ${expectedEmail}. Cuentas activas detectadas: ${detected.join(", ")}.`
      : `No pude confirmar de forma positiva la cuenta activa ${expectedEmail} en Classroom.`,
    detail: { checked, detectedEmails: detected },
  };
}

async function bridgeFetch(path, options = {}) {
  const c = await cfg();
  if (!c.secret) throw new Error("Falta configurar CLASSROOM_BRIDGE_SECRET en la extensión.");
  const headers = new Headers(options.headers || {});
  headers.set("X-SieRoom-Bridge-Secret", c.secret);
  headers.set("X-SieRoom-Bridge-Version", chrome.runtime.getManifest().version);
  headers.set(
    "X-SieRoom-Bridge-Capabilities",
    "post_private_comment,read_private_comments,verified_private_comment_read_v4,student_scoped_private_comment_read,browser_grade_return,teacher_account_guard,target_submission_guard,grade_target_guard_v1"
  );
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

function normalizedClassroomPath(value) {
  try {
    const u = new URL(String(value || ""));
    if (u.hostname !== "classroom.google.com") return null;
    return u.pathname
      .replace(/^\/u\/\d+(?=\/)/, "")
      .replace(/\/+$/, "") || "/";
  } catch (_) {
    return null;
  }
}

function classroomTargetMatches(actualUrl, expectedUrl) {
  const actual = normalizedClassroomPath(actualUrl);
  const expected = normalizedClassroomPath(expectedUrl);
  return Boolean(actual && expected && actual === expected);
}

function studentIdFromClassroomUrl(value) {
  const path = normalizedClassroomPath(value);
  const match = path?.match(/\/student\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function waitTabTargetComplete(tabId, expectedUrl, timeoutMs = 45000, generation = resetGeneration) {
  const start = Date.now();
  let lastUrl = "";
  while (Date.now() - start < timeoutMs) {
    assertGeneration(generation);
    const tab = await chrome.tabs.get(tabId);
    lastUrl = String(tab.url || "");
    if (tab.status === "complete" && classroomTargetMatches(lastUrl, expectedUrl)) return tab;
    await sleep(400);
  }
  throw new Error(
    `Classroom no llegó a la entrega solicitada. Esperada: ${normalizedClassroomPath(expectedUrl)}. ` +
    `Actual: ${normalizedClassroomPath(lastUrl) || lastUrl || "desconocida"}.`
  );
}

async function assertTabTarget(tabId, expectedUrl, generation = resetGeneration) {
  assertGeneration(generation);
  const tab = await chrome.tabs.get(tabId);
  if (!classroomTargetMatches(tab.url, expectedUrl)) {
    throw new Error(
      `PAUSA DE SEGURIDAD: Classroom abrió otra entrega. Esperada: ${normalizedClassroomPath(expectedUrl)}. ` +
      `Actual: ${normalizedClassroomPath(tab.url) || tab.url || "desconocida"}.`
    );
  }
  return tab;
}

async function ensureClassroomTab(url, generation) {
  if (classroomTabId) {
    try {
      const existing = await chrome.tabs.get(classroomTabId);
      const sameCompletedTarget = existing.status === "complete" &&
        classroomTargetMatches(existing.url, url);

      if (sameCompletedTarget) {
        // Leer y luego escribir al mismo alumno no debe desmontar la vista que
        // Classroom ya confirmó. Recargar esa misma ruta hacía desaparecer de
        // forma intermitente el panel privado aunque acabara de ser leído.
        await activateTab(classroomTabId);
        await sleep(900);
        assertGeneration(generation);
        return await assertTabTarget(classroomTabId, url, generation);
      }

      await chrome.tabs.update(classroomTabId, { url, active: true });
      let tab = await waitTabTargetComplete(classroomTabId, url, 45000, generation);
      assertGeneration(generation);
      await activateTab(classroomTabId);
      await sleep(2200);
      assertGeneration(generation);
      tab = await assertTabTarget(classroomTabId, url, generation);
      return tab;
    } catch (e) {
      if (e instanceof BridgeResetError) throw e;
      classroomTabId = null;
    }
  }
  const tab = await chrome.tabs.create({ url, active: true });
  classroomTabId = tab.id;
  let complete = await waitTabTargetComplete(classroomTabId, url, 45000, generation);
  assertGeneration(generation);
  await activateTab(classroomTabId);
  await sleep(2200);
  assertGeneration(generation);
  complete = await assertTabTarget(classroomTabId, url, generation);
  return complete;
}

function promiseTimeout(promise, ms, message) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(message)), ms))
  ]);
}

async function ensureContentScript(tabId, generation = resetGeneration) {
  assertGeneration(generation);
  const expectedVersion = chrome.runtime.getManifest().version;

  const ping = async () => {
    try { return await chrome.tabs.sendMessage(tabId, { type: "SIEROOM_PING" }); }
    catch (_) { return null; }
  };
  const compatible = (pong) => Boolean(
    pong?.ok && pong?.version === expectedVersion && pong?.build === SIEROOM_CONTENT_BUILD
  );

  let pong = await ping();
  if (compatible(pong)) return true;

  if (pong?.ok && pong?.version === expectedVersion && pong?.build !== SIEROOM_CONTENT_BUILD) {
    await chrome.tabs.reload(tabId);
    await sleep(2200);
    assertGeneration(generation);
    pong = await ping();
    if (compatible(pong)) return true;
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"]
    });
    await sleep(400);
    pong = await ping();
    return compatible(pong);
  } catch (_) {
    return false;
  }
}

async function sendToContent(tabId, payload, attempts = 12, generation = resetGeneration) {
  let lastErr = null;
  for (let i = 0; i < attempts; i++) {
    assertGeneration(generation);
    try {
      if (i === 0 || i === 3 || i === 7) {
        const ready = await ensureContentScript(tabId, generation);
        if (!ready) {
          throw new Error(`Bridge incompatible: se requiere content build ${SIEROOM_CONTENT_BUILD}; no se enviará ninguna acción.`);
        }
      }
      const response = await promiseTimeout(
        chrome.tabs.sendMessage(tabId, payload),
        70000,
        "Classroom tardó demasiado en responder."
      );
      if (response) return response;
    } catch (e) {
      lastErr = e;
    }
    await sleep(650);
  }
  throw lastErr || new Error("No pude contactar el content script de Classroom.");
}

function isMissingPrivateEditorResult(result) {
  return result?.ok === false &&
    String(result?.error || "").includes("No encontré el editor de Comentarios privados");
}

async function reloadClassroomTarget(tabId, expectedUrl, expectedEmail, generation = resetGeneration) {
  log("Classroom no mostró el panel privado; recargando una sola vez antes de detener el trabajo…");
  await chrome.tabs.reload(tabId);
  await waitTabTargetComplete(tabId, expectedUrl, 45000, generation);
  assertGeneration(generation);
  await sleep(3200);
  await assertTabTarget(tabId, expectedUrl, generation);
  const account = await checkAccountOnTab(tabId, expectedEmail, generation);
  if (account?.ok !== true) {
    throw new AccountMismatchError(
      `No pude volver a verificar la cuenta docente ${expectedEmail} después de recargar Classroom.`,
      account || {}
    );
  }
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
    const c = await cfg();
    const forcedUrl = addExpectedAccount(job.submission_url, c.teacherEmail);
    const tab = await ensureClassroomTab(forcedUrl, generation);

    // Verificación de seguridad: si Google muestra explícitamente otra cuenta,
    // NO publicamos y devolvemos el trabajo a la cola mediante RESET.
    const account = await checkAccountOnTab(tab.id, c.teacherEmail, generation);
    if (account?.ok !== true) {
      throw new AccountMismatchError(
        `No pude verificar de forma positiva la cuenta docente ${c.teacherEmail}; no se leerá ni escribirá nada.`,
        account || {}
      );
    }
    log(`Cuenta docente confirmada: ${c.teacherEmail}.`);

    log(`Trabajo ${job.id}: Classroom activo; esperando panel lateral…`);
    await sleep(1700);
    assertGeneration(generation);

    const isRead = job.operation === "read_private_comments";
    // HF4 conserva comentario + calificación + devolución en la MISMA sesión,
    // pero la caja de nota queda acotada al student_id exacto de submission_url.
    await assertTabTarget(tab.id, forcedUrl, generation);
    const targetStudentId = studentIdFromClassroomUrl(forcedUrl);
    if (!isRead && !targetStudentId) {
      throw new Error("PAUSA DE SEGURIDAD HF4: submission_url no contiene student_id.");
    }
    if (!isRead) log(`target_student_id=${targetStudentId}`);
    const contentPayload = isRead ? {
      type: "SIEROOM_READ_PRIVATE_COMMENTS"
    } : {
      type: "SIEROOM_PROCESS_SUBMISSION",
      comment: job.comment,
      grade: job.grade,
      returnAfterComment: Boolean(job.return_after_comment),
      targetStudentId,
      expectedSubmissionUrl: forcedUrl
    };
    let result = await sendToContent(tab.id, contentPayload, 10, generation);
    if (isMissingPrivateEditorResult(result)) {
      // Esta excepción ocurre antes de escribir. Un único reload es seguro y
      // evita fallos transitorios sin repetir un comentario potencialmente enviado.
      await reloadClassroomTarget(tab.id, forcedUrl, c.teacherEmail, generation);
      result = await sendToContent(tab.id, contentPayload, 10, generation);
    }
    assertGeneration(generation);

    if (!classroomTargetMatches(result?.url, forcedUrl)) {
      throw new Error(
        `PAUSA DE SEGURIDAD: la respuesta pertenece a otra entrega. Esperada: ` +
        `${normalizedClassroomPath(forcedUrl)}. Actual: ${normalizedClassroomPath(result?.url) || result?.url || "desconocida"}.`
      );
    }

    if (!result?.ok) {
      throw new Error(result?.error || (isRead
        ? "Classroom no devolvió los comentarios privados."
        : "Classroom no confirmó el procesamiento de la entrega."));
    }

    if (!isRead) {
      const currentStudentId = result?.current_student_id || studentIdFromClassroomUrl(result?.url);
      log(`current_student_id=${currentStudentId || "desconocido"}`);
      if (currentStudentId !== targetStudentId || result?.target_student_id !== targetStudentId) {
        throw new Error(
          `PAUSA DE SEGURIDAD HF4: el resultado no conserva el alumno objetivo. Esperado: ${targetStudentId}. Actual: ${currentStudentId || "desconocido"}.`
        );
      }
      if (result?.grade_field_candidates) {
        log(`grade_field_candidates=${JSON.stringify(result.grade_field_candidates).slice(0, 1600)}`);
      }
      if (result?.matched_grade_field) {
        log(`matched_grade_field=${JSON.stringify(result.matched_grade_field)}`);
      }
      if (result?.grade_before !== undefined) log(`grade_before=${String(result.grade_before)}`);
      if (result?.grade_after !== undefined) log(`grade_after=${String(result.grade_after)}`);
      log(`browser_grade_applied=${Boolean(result?.browser_grade_applied)}`);
    }

    if (isRead) {
      if (result.operation !== "read_private_comments" || !Array.isArray(result.comments) ||
          Number(result.count) !== result.comments.length) {
        throw new Error("Classroom devolvió un resultado de lectura incompleto o incompatible.");
      }
      log(`Comentarios leídos para ${job.submission_id}: ${result.comments.length}.`);
      await complete(job, { ...result, teacher_account_verified: true });
      assertGeneration(generation);
      log(`Lectura ${job.id} completada bajo la cuenta ${c.teacherEmail}.`);
      return { readCompleted: true, count: result.comments.length };
    }

    const commentInfo = result.comment || {};
    if (job.comment) {
      log(`Comentario privado listo para ${job.submission_id}${commentInfo.alreadyPresent ? " (ya existía)" : ""}.`);
    }
    if (job.grade !== null && job.grade !== undefined) {
      if (!result.browser_grade_applied) throw new Error("Classroom no confirmó la calificación en el navegador.");
      log(`Calificación ${job.grade} registrada en Classroom.`);
    }
    if (job.return_after_comment) {
      if (!result.browser_returned) throw new Error("Classroom no confirmó la devolución al estudiante.");
      log("Entrega devuelta al estudiante.");
    }

    const done = await complete(job, {
      ...result,
      teacher_account_verified: true,
      browser_followup_done: true,
      browser_grade_applied: Boolean(result.browser_grade_applied),
      browser_grade: result.browser_grade,
      browser_returned: Boolean(result.browser_returned)
    });
    assertGeneration(generation);

    if (done.status === 207 || done.data?.partial) {
      // Compatibilidad temporal con servidor 0.7.x: ese servidor intenta repetir
      // nota/devolución por API y puede recibir 403. Si el navegador YA confirmó
      // ambas acciones, no convertimos un éxito real en un fallo local.
      log(`Trabajo ${job.id} completado en Classroom. El servidor antiguo reportó seguimiento API parcial; actualiza Render a v0.8.7 para limpiar ese estado.`);
      return { completedInBrowser: true, legacyServerPartial: true };
    }
    log(`Trabajo ${job.id} completado: comentario/nota/devolución confirmados.`);
  } catch (e) {
    if (e instanceof BridgeResetError) {
      log(`Trabajo ${job.id}: liberado por RESET; volverá a la cola.`);
      return { reset: true };
    }

    if (e instanceof AccountMismatchError) {
      const message = String(e?.message || e);
      log(`PAUSA DE SEGURIDAD ${job.id}: ${message}`);
      statusEl.textContent = message + " Cambia de cuenta en Classroom; el trabajo volverá a pendientes.";
      statusEl.className = "bad";
      try {
        await bridgeFetch("/bridge/v1/reset", {
          method: "POST",
          body: JSON.stringify({ retry_failed: false })
        });
      } catch (_) {}
      return { pausedForAccount: true };
    }

    const message = String(e?.message || e);
    log(`ERROR ${job.id}: ${message}`);
    try { await fail(job, message); } catch (_) {}
    return { failed: true };
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
    const result = await processJob(job, generation);
    if (result?.pausedForAccount) break;
    assertGeneration(generation);
    processed += 1;
    // Pequeñísima pausa para que la UI y Chrome respiren, sin meter 3 s por trabajo.
    await sleep(180);
  }
  return processed;
}

async function poll(force = false) {
  // "Procesar ahora" nunca invalida un trabajo en curso. Solo RESET puede
  // cancelar una generación y liberar el claim del servidor.
  if (busy) {
    if (force) log("Ya existe un trabajo en curso; no se inició un segundo proceso.");
    return;
  }
  busy = true;
  const generation = resetGeneration;
  try {
    if (!await isLeaderBridgeTab()) {
      statusEl.textContent = "Otra pestaña de SieRoom Bridge está procesando la cola. Esta queda en espera.";
      statusEl.className = "bad";
      return;
    }
    const c = await cfg();
    if (!c.secret) {
      statusEl.textContent = "Falta configurar el secreto del puente.";
      statusEl.className = "bad";
      return;
    }
    if (!c.teacherEmail) {
      statusEl.textContent = "Falta configurar el correo docente de Classroom.";
      statusEl.className = "bad";
      return;
    }

    const account = await preflightAccount(c.teacherEmail, generation);
    if (!account.ok) {
      statusEl.textContent = account.message || `Abre Classroom con ${c.teacherEmail}.`;
      statusEl.className = "bad";
      return;
    }

    const st = await bridgeFetch("/bridge/v1/status");
    const extensionVersion = chrome.runtime.getManifest().version;
    if (String(st.data?.version || "") !== extensionVersion) {
      throw new Error(
        `Versión incompatible: servidor ${st.data?.version || "desconocida"} · ` +
        `extensión ${extensionVersion}. No se procesará la cola.`
      );
    }
    const q = st.data.queue || {};
    statusEl.textContent = `Conectado a SieRoom · extensión ${extensionVersion} · ${friendlyQueue(q)}`;
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
  try { await resetQueue({ retryFailed: true, fromButton: true }); }
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
