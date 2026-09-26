(() => {
  "use strict";

  const CAPABILITY = "johnny_whatsapp_bridge_v1";
  const BUILD = "0.1.1";
  let running = false;

  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function setStatus(text, bad = false) {
    const el = $("status");
    if (!el) return;
    el.textContent = text;
    el.dataset.bad = bad ? "1" : "0";
  }

  async function config() {
    return chrome.storage.local.get({ endpoint: "", secret: "" });
  }

  async function api(path, options = {}) {
    const { endpoint, secret } = await config();
    if (!endpoint || !secret) throw new Error("Configura endpoint y secreto en el popup.");
    const base = endpoint.replace(/\/+$/, "");
    const headers = {
      "X-WhatsApp-Bridge-Secret": secret,
      "X-WhatsApp-Bridge-Capability": CAPABILITY,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    const res = await fetch(base + path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function whatsappTab() {
    const tabs = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
    if (!tabs.length) throw new Error("Abre WhatsApp Web en una pestaña.");
    return tabs.find((t) => t.active) || tabs[0];
  }

  async function executeInTab(tabId, job) {
    try {
      return await chrome.tabs.sendMessage(tabId, { type: "JOHNNY_WA_EXECUTE", job });
    } catch (_err) {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
      await sleep(200);
      return chrome.tabs.sendMessage(tabId, { type: "JOHNNY_WA_EXECUTE", job });
    }
  }

  async function processOnce() {
    const next = await api("/wa/v1/next");
    const job = next.job;
    if (!job) return false;
    setStatus(`Procesando ${job.operation}…`);
    try {
      const tab = await whatsappTab();
      const response = await executeInTab(tab.id, job);
      if (!response?.ok) throw new Error(response?.error || "La pestaña no devolvió resultado.");
      await api(`/wa/v1/jobs/${encodeURIComponent(job.id)}/complete`, {
        method: "POST",
        body: JSON.stringify(response.result || {}),
      });
      setStatus(`Activo · ${job.operation} completado`);
    } catch (err) {
      await api(`/wa/v1/jobs/${encodeURIComponent(job.id)}/fail`, {
        method: "POST",
        body: JSON.stringify({
          ok: false,
          operation: job.operation,
          error: String(err?.message || err),
          build: BUILD,
        }),
      }).catch(() => {});
      setStatus(String(err?.message || err), true);
    }
    return true;
  }

  async function loop() {
    if (running) return;
    running = true;
    while (running) {
      try {
        const didWork = await processOnce();
        if (!didWork) setStatus("Activo · esperando órdenes");
      } catch (err) {
        setStatus(String(err?.message || err), true);
      }
      await sleep(1200);
    }
  }

  $("openWhatsApp")?.addEventListener("click", () => chrome.tabs.create({ url: "https://web.whatsapp.com/" }));
  $("stop")?.addEventListener("click", () => { running = false; setStatus("Puente detenido"); });
  $("start")?.addEventListener("click", loop);
  loop();
})();
