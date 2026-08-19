const endpoint = document.getElementById("endpoint");
const secret = document.getElementById("secret");
const msg = document.getElementById("msg");

(async () => {
  const data = await chrome.storage.local.get(["endpoint", "secret"]);
  if (data.endpoint) endpoint.value = data.endpoint;
  if (data.secret) secret.value = data.secret;
})();

async function save() {
  const ep = endpoint.value.trim().replace(/\/$/, "");
  const sec = secret.value.trim();
  await chrome.storage.local.set({ endpoint: ep, secret: sec });
  return { ep, sec };
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    const { ep, sec } = await save();
    if (!sec) throw new Error("Falta el secreto.");
    const r = await fetch(`${ep}/bridge/v1/status`, { headers: { "X-SieRoom-Bridge-Secret": sec } });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    msg.textContent = `Conexión correcta. Servidor ${data.version} · extensión ${chrome.runtime.getManifest().version}.`;
  } catch (e) {
    msg.textContent = `Error: ${String(e?.message || e)}`;
  }
});

document.getElementById("start").addEventListener("click", async () => {
  await save();
  await chrome.tabs.create({ url: chrome.runtime.getURL("bridge.html"), active: true });
  window.close();
});


async function resetQueueFromPopup() {
  const { ep, sec } = await save();
  if (!sec) throw new Error("Falta el secreto.");
  msg.textContent = "Desatascando cola…";

  const r = await fetch(`${ep}/bridge/v1/reset`, {
    method: "POST",
    headers: {
      "X-SieRoom-Bridge-Secret": sec,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ retry_failed: false })
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);

  // Recargar las pestañas del puente reinicia cualquier estado local `busy`
  // que hubiera quedado bloqueado. No cerramos las pestañas normales del usuario.
  const bridgeUrl = chrome.runtime.getURL("bridge.html");
  const tabs = await chrome.tabs.query({ url: bridgeUrl + "*" });
  for (const tab of tabs) {
    try { await chrome.tabs.reload(tab.id); } catch (_) {}
  }

  const q = data.queue || {};
  msg.textContent = `RESET correcto. Liberados: ${data.released_count || 0}. Pendientes reales: ${q.work_remaining ?? ((q.queued || 0) + (q.claimed || 0))}. El puente continuará procesando.`;
}

document.getElementById("reset").addEventListener("click", async () => {
  try {
    await resetQueueFromPopup();
  } catch (e) {
    msg.textContent = `Error al resetear: ${String(e?.message || e)}`;
  }
});
