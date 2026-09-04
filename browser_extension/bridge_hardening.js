(() => {
  if (window.__SIEROOM_BRIDGE_HARDENING_R62__) return;
  window.__SIEROOM_BRIDGE_HARDENING_R62__ = true;

  const REQUIRED_BUILD = "0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2";
  const nativeFetch = window.fetch.bind(window);

  function isBridgeRequest(url) {
    try {
      const u = new URL(String(url || ""), location.href);
      return u.pathname.startsWith("/bridge/v1/");
    } catch (_) {
      return false;
    }
  }

  function responseWithJson(response, data) {
    const headers = new Headers(response.headers);
    headers.set("Content-Type", "application/json");
    return new Response(JSON.stringify(data), {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  }

  async function failClaimedJob(baseUrl, job, requestHeaders, reason) {
    if (!job?.id) return;
    try {
      const failHeaders = new Headers(requestHeaders || {});
      failHeaders.set("X-SieRoom-Bridge-Build", REQUIRED_BUILD);
      failHeaders.set("Content-Type", "application/json");
      const u = new URL(String(baseUrl || ""), location.href);
      const failUrl = `${u.origin}/bridge/v1/jobs/${encodeURIComponent(job.id)}/fail`;
      await nativeFetch(failUrl, {
        method: "POST",
        headers: failHeaders,
        body: JSON.stringify({
          error: reason,
          bridge_contract: "quantitative_grade_requires_private_comment_and_return_r62",
        }),
        cache: "no-store",
      });
    } catch (err) {
      console.error("[SieRoom R6.2 hardening] No pude marcar el trabajo incompatible como fallido.", err);
    }
  }

  window.fetch = async function sieroomHardenedFetch(input, init = {}) {
    const requestUrl = typeof input === "string" || input instanceof URL
      ? String(input)
      : String(input?.url || "");

    if (!isBridgeRequest(requestUrl)) {
      return nativeFetch(input, init);
    }

    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined) || {});
    headers.set("X-SieRoom-Bridge-Build", REQUIRED_BUILD);

    const response = await nativeFetch(input, { ...init, headers });

    let pathname = "";
    try { pathname = new URL(requestUrl, location.href).pathname; } catch (_) {}
    if (pathname !== "/bridge/v1/next" || !response.ok) return response;

    let data = null;
    try { data = await response.clone().json(); } catch (_) { return response; }
    const job = data?.job;
    if (!job || job.operation !== "post_private_comment") return responseWithJson(response, data);

    const hasGrade = job.grade !== null && job.grade !== undefined && job.grade !== "";
    if (!hasGrade) return responseWithJson(response, data);

    const comment = String(job.comment || "").trim();
    if (!comment) {
      const reason = "bridge_contract_violation: toda nota cuantitativa requiere comentario privado y devolución; trabajo detenido sin modificar Classroom.";
      await failClaimedJob(requestUrl, job, headers, reason);
      data.job = null;
      data.hardening_rejected_job = job.id;
      data.hardening_error = reason;
      console.error(`[SieRoom R6.2 hardening] ${reason}`, { job_id: job.id });
      return responseWithJson(response, data);
    }

    // Contrato docente: una nota cuantitativa nunca sale sola.
    // El content script ya procesa en orden comentario -> nota -> devolución.
    job.return_after_comment = true;
    job.bridge_contract = "quantitative_grade_private_comment_return_r62";
    console.info("[SieRoom R6.2 hardening] Contrato triple activado", {
      job_id: job.id,
      submission_id: job.submission_id,
      grade: job.grade,
      has_comment: true,
      return_after_comment: true,
      build: REQUIRED_BUILD,
    });

    return responseWithJson(response, data);
  };

  console.info("[SieRoom R6.2 hardening] Activo", {
    build: REQUIRED_BUILD,
    contract: "comentario privado -> nota cuantitativa -> devolución",
  });
})();
