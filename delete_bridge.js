(() => {
  const DEFAULT_TEACHER_EMAIL = "jbringas@santaritadecasia.edu.pe";
  if (window.__SIEROOM_DELETE_BRIDGE_087_V1__) return;
  window.__SIEROOM_DELETE_BRIDGE_087_V1__ = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let busy = false;
  let deleteTabId = null;

  const norm = (s) => String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  function log(msg) {
    const el = document.getElementById("log");
    if (!el) return;
    const stamp = new Date().toLocaleTimeString();
    el.textContent = `[${stamp}] DELETE: ${msg}\n` + el.textContent.slice(0, 10000);
  }

  async function cfg() {
    const data = await chrome.storage.local.get(["endpoint", "teacherEmail", "secret"]);
    return {
      endpoint: String(data.endpoint || "https://santa-rita-escolar-tcpb.onrender.com").replace(/\/$/, ""),
      teacherEmail: String(data.teacherEmail || DEFAULT_TEACHER_EMAIL).trim().toLowerCase(),
      secret: String(data.secret || "")
    };
  }

  async function deleteFetch(path, options = {}) {
    const c = await cfg();
    if (!c.secret) throw new Error("Falta configurar CLASSROOM_BRIDGE_SECRET.");
    const headers = new Headers(options.headers || {});
    headers.set("X-SieRoom-Bridge-Secret", c.secret);
    headers.set("X-SieRoom-Bridge-Version", "0.8.7");
    headers.set("X-SieRoom-Delete-Capability", "delete_private_comment_v1");
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const r = await fetch(`${c.endpoint}${path}`, { ...options, headers, cache: "no-store" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  async function normalQueueIsIdle() {
    try {
      const c = await cfg();
      const headers = new Headers();
      headers.set("X-SieRoom-Bridge-Secret", c.secret);
      const r = await fetch(`${c.endpoint}/bridge/v1/status`, { headers, cache: "no-store" });
      if (!r.ok) return false;
      const data = await r.json();
      return Number(data?.queue?.work_remaining || 0) === 0;
    } catch (_) {
      return false;
    }
  }

  async function isLeader() {
    try {
      const current = await chrome.tabs.getCurrent();
      const bridgeUrl = chrome.runtime.getURL("bridge.html");
      const tabs = await chrome.tabs.query({ url: bridgeUrl + "*" });
      const leader = tabs.filter((t) => Number.isInteger(t.id)).sort((a, b) => a.id - b.id)[0];
      return Boolean(current?.id && leader?.id === current.id);
    } catch (_) {
      return true;
    }
  }

  function normalizedPath(value) {
    try {
      const u = new URL(String(value || ""));
      if (u.hostname !== "classroom.google.com") return null;
      return u.pathname.replace(/^\/u\/\d+(?=\/)/, "").replace(/\/+$/, "") || "/";
    } catch (_) {
      return null;
    }
  }

  function targetMatches(actual, expected) {
    const a = normalizedPath(actual);
    const e = normalizedPath(expected);
    return Boolean(a && e && a === e);
  }

  function withAccount(url, email) {
    try {
      const u = new URL(url);
      if (email) u.searchParams.set("authuser", email);
      return u.toString();
    } catch (_) {
      return url;
    }
  }

  async function waitComplete(tabId, expectedUrl, timeoutMs = 45000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status === "complete" && targetMatches(tab.url, expectedUrl)) return tab;
      await sleep(350);
    }
    throw new Error("Classroom no llegó a la entrega exacta solicitada para borrar el comentario.");
  }

  async function ensureDeleteTab(url) {
    if (deleteTabId) {
      try {
        const tab = await chrome.tabs.get(deleteTabId);
        if (tab.status === "complete" && targetMatches(tab.url, url)) return tab;
        await chrome.tabs.update(deleteTabId, { url, active: true });
        return await waitComplete(deleteTabId, url);
      } catch (_) {
        deleteTabId = null;
      }
    }
    const tab = await chrome.tabs.create({ url, active: true });
    deleteTabId = tab.id;
    return await waitComplete(deleteTabId, url);
  }

  async function ensureScripts(tabId) {
    try {
      const pong = await chrome.tabs.sendMessage(tabId, { type: "SIEROOM_PING" });
      if (pong?.ok) {
        await chrome.scripting.executeScript({ target: { tabId }, files: ["delete_private_comment.js"] });
        await sleep(180);
        return;
      }
    } catch (_) {}

    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js", "delete_private_comment.js"] });
    await sleep(450);
  }

  async function send(tabId, payload, timeoutMs = 70000) {
    return await Promise.race([
      chrome.tabs.sendMessage(tabId, payload),
      new Promise((_, reject) => setTimeout(() => reject(new Error("Classroom tardó demasiado en responder.")), timeoutMs))
    ]);
  }

  async function processDelete(job) {
    const previous = (await chrome.tabs.query({ active: true, currentWindow: true }))?.[0]?.id || null;
    try {
      const c = await cfg();
      if (!c.teacherEmail) throw new Error("Falta configurar el correo docente de Classroom.");
      const forcedUrl = withAccount(job.submission_url, c.teacherEmail);
      const tab = await ensureDeleteTab(forcedUrl);
      await chrome.tabs.update(tab.id, { active: true });
      await sleep(1400);
      await ensureScripts(tab.id);

      const account = await send(tab.id, { type: "SIEROOM_CHECK_ACCOUNT", expectedEmail: c.teacherEmail }, 15000);
      if (account?.ok !== true) throw new Error(`No pude verificar la cuenta docente ${c.teacherEmail}; no se borró nada.`);

      const read = await send(tab.id, { type: "SIEROOM_READ_PRIVATE_COMMENTS" }, 70000);
      if (!read?.ok || read.operation !== "read_private_comments" || !Array.isArray(read.comments)) {
        throw new Error(read?.error || "No pude verificar los comentarios privados antes del borrado.");
      }
      if (!targetMatches(read.url, forcedUrl)) throw new Error("La lectura previa pertenece a otra entrega; no se borró nada.");

      const wanted = norm(job.comment_text);
      let selected = null;
      if (job.dom_order !== null && job.dom_order !== undefined) {
        selected = read.comments.find((cmt) => Number(cmt.domOrder) === Number(job.dom_order));
        if (!selected || norm(selected.text) !== wanted) {
          throw new Error("El comentario de la posición solicitada cambió o ya no coincide exactamente; no se borró nada.");
        }
      } else {
        const exact = read.comments.filter((cmt) => norm(cmt.text) === wanted);
        if (exact.length === 0) throw new Error("El comentario exacto ya no existe; no se borró nada.");
        if (exact.length > 1) throw new Error("Hay comentarios idénticos; se requiere domOrder para borrar sin ambigüedad.");
        selected = exact[0];
      }

      const requestedDomOrder =
        job.dom_order !== null && job.dom_order !== undefined
          ? selected.domOrder
          : null;

      const result = await send(tab.id, {
        type: "SIEROOM_DELETE_PRIVATE_COMMENT",
        commentText: job.comment_text,
        // Si el servidor no fijó posición, conservamos el borrado por texto
        // exacto y único. Classroom puede reordenar el DOM entre esta lectura
        // y el clic destructivo, por lo que no convertimos artificialmente la
        // coincidencia única en un índice rígido.
        domOrder: requestedDomOrder,
      }, 70000);
      if (!result?.ok || result.operation !== "delete_private_comment" || result.deleted !== true) {
        throw new Error(result?.error || "Classroom no confirmó el borrado del comentario privado.");
      }
      if (!targetMatches(result.url, forcedUrl)) throw new Error("La confirmación de borrado pertenece a otra entrega.");

      await deleteFetch(`/bridge/v1/delete/jobs/${encodeURIComponent(job.id)}/complete`, {
        method: "POST",
        body: JSON.stringify({ ...result, teacher_account_verified: true }),
      });
      log(`Comentario privado eliminado de ${job.submission_id} y verificado visualmente.`);
    } catch (e) {
      const message = String(e?.message || e);
      log(`ERROR ${job.id}: ${message}`);
      try {
        await deleteFetch(`/bridge/v1/delete/jobs/${encodeURIComponent(job.id)}/fail`, {
          method: "POST",
          body: JSON.stringify({ error: message }),
        });
      } catch (_) {}
    } finally {
      if (previous && previous !== deleteTabId) {
        try { await chrome.tabs.update(previous, { active: true }); } catch (_) {}
      }
    }
  }

  async function poll() {
    if (busy) return;
    busy = true;
    try {
      if (!await isLeader()) return;
      const c = await cfg();
      if (!c.secret || !c.teacherEmail) return;
      if (!await normalQueueIsIdle()) return;
      const next = await deleteFetch("/bridge/v1/delete/next");
      if (next?.job) await processDelete(next.job);
    } catch (e) {
      log(`Conexión: ${String(e?.message || e)}`);
    } finally {
      busy = false;
    }
  }

  setInterval(poll, 2500);
  setTimeout(poll, 700);
})();
