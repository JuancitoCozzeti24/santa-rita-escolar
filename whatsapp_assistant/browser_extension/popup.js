(async () => {
  const endpoint = document.getElementById("endpoint");
  const secret = document.getElementById("secret");
  const status = document.getElementById("status");
  const cfg = await chrome.storage.local.get({ endpoint: "", secret: "" });
  endpoint.value = cfg.endpoint;
  secret.value = cfg.secret;

  document.getElementById("save").addEventListener("click", async () => {
    await chrome.storage.local.set({
      endpoint: endpoint.value.trim().replace(/\/+$/, ""),
      secret: secret.value,
    });
    status.textContent = "Configuración guardada.";
  });

  document.getElementById("bridge").addEventListener("click", () => {
    chrome.tabs.create({ url: chrome.runtime.getURL("bridge.html") });
  });
})();
