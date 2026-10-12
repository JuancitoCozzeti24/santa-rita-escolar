(() => {
  if (window.__SIEROOM_QUEUE_STOP_R63__) return;
  window.__SIEROOM_QUEUE_STOP_R63__ = true;

  const STOP_REASON = "teacher_stop_queue: cola detenida manualmente por el docente";
  const previousFetch = window.fetch.bind(window);
  let stopMode = false;
  let draining = false;

  function requestPath(input) {
    try {
      const raw = typeof input === "string" || input instanceof URL
        ? String(input)
        : String(input?.url || "");
      return new URL(raw, location.href).pathname;
    } catch (_) {
      return "";
    }
  }

  function stoppedResponse(kind = "normal") {
    return new Response(JSON.stringify({
      ok: true,
      job: null,
      stopped_by_teacher: true,
      queue_kind: kind,
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Mientras el docente haya pulsado DETENER COLA, ningún poller puede reclamar
  // un trabajo nuevo. Las peticiones de estado/fallo/reset siguen permitidas.
  window.fetch = async function sieroomStopAwareFetch(input, init = {}) {
    const path = requestPath(input);
    if (stopMode && !draining) {
      if (path === "/bridge/v1/next") return stoppedResponse("normal");
      if (path === "/bridge/v1/delete/next") return stoppedResponse("delete");
    }
    return previousFetch(input, init);
  };

  async function failNormalJob(job) {
    if (!job?.id) return false;
    try {
      await bridgeFetch(`/bridge/v1/jobs/${encodeURIComponent(job.id)}/fail`, {
        method: "POST",
        body: JSON.stringify({
          error: STOP_REASON,
          stopped_by_teacher: true,
          stop_contract: "manual_stop_zero_r63",
        }),
      });
      return true;
    } catch (e) {
      log(`DETENER COLA: no pude cancelar ${job.id}: ${String(e?.message || e)}`);
      return false;
    }
  }

  async function drainNormalQueue(maxJobs = 500) {
    let cancelled = 0;
    for (let i = 0; i < maxJobs; i += 1) {
      const nxt = await bridgeFetch("/bridge/v1/next");
      const job = nxt.data?.job;
      if (!job) {
        if (nxt.data?.hardening_rejected_job) {
          cancelled += 1;
          continue;
        }
        break;
      }
      if (await failNormalJob(job)) cancelled += 1;
    }
    return cancelled;
  }

  async function deleteApi(path, options = {}) {
    const c = await cfg();
    if (!c.secret) throw new Error("Falta configurar CLASSROOM_BRIDGE_SECRET.");
    const headers = new Headers(options.headers || {});
    headers.set("X-SieRoom-Bridge-Secret", c.secret);
    headers.set("X-SieRoom-Bridge-Version", "0.8.7");
    headers.set("X-SieRoom-Delete-Capability", "delete_private_comment_v1");
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await previousFetch(`${c.endpoint}${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async function drainDeleteQueue(maxJobs = 200) {
    let cancelled = 0;
    for (let i = 0; i < maxJobs; i += 1) {
      const next = await deleteApi("/bridge/v1/delete/next");
      const job = next?.job;
      if (!job) break;
      try {
        await deleteApi(`/bridge/v1/delete/jobs/${encodeURIComponent(job.id)}/fail`, {
          method: "POST",
          body: JSON.stringify({
            error: STOP_REASON,
            stopped_by_teacher: true,
            stop_contract: "manual_stop_zero_r63",
          }),
        });
        cancelled += 1;
      } catch (e) {
        log(`DETENER COLA: no pude cancelar borrado ${job.id}: ${String(e?.message || e)}`);
      }
    }
    return cancelled;
  }

  async function stopAndZeroQueue() {
    if (draining) return;
    draining = true;
    stopMode = true;

    // Invalida la generación que pudiera estar trabajando y bloquea el poll normal.
    resetGeneration += 1;
    queueHalted = true;
    queueHaltReason = "detenida manualmente por el docente; pendientes puestos en cero";
    busy = false;
    lastJobStartedAt = 0;

    statusEl.textContent = "DETENIENDO COLA… cancelando todos los envíos pendientes.";
    statusEl.className = "bad";
    log("DETENER COLA solicitado: se bloquean nuevos trabajos y se vacían los pendientes.");

    let normalCancelled = 0;
    let deleteCancelled = 0;
    let finalRemaining = null;

    try {
      // Libera cualquier claim vigente para que pueda ser recogido y marcado como
      // fallido/cancelado por esta operación. No reintenta trabajos fallidos antiguos.
      await bridgeFetch("/bridge/v1/reset", {
        method: "POST",
        body: JSON.stringify({ retry_failed: false }),
      });

      normalCancelled = await drainNormalQueue();
      deleteCancelled = await drainDeleteQueue();

      const st = await bridgeFetch("/bridge/v1/status");
      finalRemaining = Number(st.data?.queue?.work_remaining || 0);

      statusEl.textContent = `COLA DETENIDA · pendientes: ${finalRemaining} · cancelados ahora: ${normalCancelled + deleteCancelled}.`;
      statusEl.className = finalRemaining === 0 ? "ok" : "bad";
      log(`DETENER COLA terminado. Normales cancelados: ${normalCancelled}; borrados cancelados: ${deleteCancelled}; pendientes: ${finalRemaining}.`);
      log("La cola permanecerá detenida. Para volver a procesar trabajos usa RESET / REINTENTAR TODO.");
    } catch (e) {
      const message = String(e?.message || e);
      statusEl.textContent = `COLA DETENIDA, pero no pude confirmar cero pendientes: ${message}`;
      statusEl.className = "bad";
      log(`DETENER COLA ERROR: ${message}`);
    } finally {
      draining = false;
    }
  }

  const stopButton = document.getElementById("stopQueue");
  if (stopButton) {
    stopButton.addEventListener("click", () => stopAndZeroQueue());
  }

  // RESET es la acción explícita para salir del modo detenido.
  const resetButton = document.getElementById("resetQueue");
  if (resetButton) {
    resetButton.addEventListener("click", () => {
      stopMode = false;
    }, true);
  }
})();