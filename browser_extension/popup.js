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
    msg.textContent = `Conexión correcta. Versión ${data.version}.`;
  } catch (e) {
    msg.textContent = `Error: ${String(e?.message || e)}`;
  }
});

document.getElementById("start").addEventListener("click", async () => {
  await save();
  await chrome.tabs.create({ url: chrome.runtime.getURL("bridge.html"), active: true });
  window.close();
});
