/* Network/configuration only. No queue or Classroom mutations. */
(() => {
  const DEFAULT_ENDPOINT = "https://sieroom-src.onrender.com";
  const LEGACY_ENDPOINT = "https://santa-rita-escolar-tcpb.onrender.com";
  const BUILD = "0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6.2";
  const CAPABILITIES = "post_private_comment,read_private_comments,verified_private_comment_read_v4,student_scoped_private_comment_read,browser_grade_return,teacher_account_guard,target_submission_guard,grade_target_guard_v1";

  function normalizeEndpoint(value) {
    const raw = String(value || DEFAULT_ENDPOINT).trim().replace(/\/+$/, "");
    const url = new URL(raw);
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
      throw new Error("Usa la URL HTTPS base del servidor, sin rutas ni credenciales.");
    }
    // This build must never send its secret back to the retired server.
    if (url.origin !== DEFAULT_ENDPOINT && url.origin !== LEGACY_ENDPOINT) {
      throw new Error("Servidor no autorizado por esta versión institucional.");
    }
    return DEFAULT_ENDPOINT;
  }

  async function config() {
    const data = await chrome.storage.local.get(["endpoint", "teacherEmail", "secret"]);
    const endpoint = normalizeEndpoint(data.endpoint);
    if (data.endpoint !== endpoint) await chrome.storage.local.set({endpoint});
    return {...data, endpoint}; // Preserve the existing email and secret unchanged.
  }

  function headers(secret, extra = {}) {
    const result = new Headers(extra);
    result.set("X-SieRoom-Bridge-Secret", secret);
    result.set("X-SieRoom-Bridge-Version", chrome.runtime.getManifest().version);
    result.set("X-SieRoom-Bridge-Build", BUILD);
    result.set("X-SieRoom-Bridge-Capabilities", CAPABILITIES);
    return result;
  }

  async function request(endpoint, path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 65000);
    try {
      const response = await fetch(normalizeEndpoint(endpoint) + path, {...options, signal: controller.signal, redirect: "error", cache: "no-store"});
      const type = response.headers.get("Content-Type") || "";
      const data = type.includes("application/json") ? await response.json() : null;
      if (!response.ok && response.status !== 207) {
        if (response.status === 401) throw new Error("No autorizado (401). Comprueba el secreto guardado en la extensión.");
        if (response.status === 404) throw new Error("Ruta Bridge no disponible (404). Comprueba el despliegue institucional.");
        throw new Error(`HTTP ${response.status}: ${data?.error || "solicitud rechazada"}`);
      }
      if (!data || typeof data !== "object" || (data.ok !== true && !(response.status === 207 && data.partial === true))) throw new Error("Respuesta Bridge inválida: se esperaba JSON con ok=true.");
      return {status: response.status, data};
    } catch (error) {
      if (error.name === "AbortError") throw new Error("El servidor no respondió en 65 s. Puede estar iniciándose; vuelve a Guardar y probar.");
      if (error instanceof TypeError) throw new Error("No se pudo conectar. Comprueba Internet y recarga la extensión para aplicar los permisos del nuevo servidor.");
      throw error;
    } finally { clearTimeout(timer); }
  }

  async function check(endpoint, secret) {
    const options = {headers: headers(secret)};
    const result = await request(endpoint, "/bridge/v1/status", options);
    if (result.data.bridge !== "SieRoom Classroom Bridge" || !result.data.queue || typeof result.data.queue !== "object") throw new Error("El servidor no devolvió un estado Bridge válido.");
    if (result.data.version !== chrome.runtime.getManifest().version) throw new Error("Versiones distintas entre servidor y extensión. No se procesará la cola.");
    const contract = await request(endpoint, "/bridge/v1/compatibility", options);
    if (contract.data.compatible !== true || contract.data.triple_contract !== true) throw new Error("Contrato Bridge incompatible o protección triple no disponible.");
    return result.data;
  }
  window.SieRoomConnection = {DEFAULT_ENDPOINT, BUILD, CAPABILITIES, normalizeEndpoint, config, headers, request, check};
})();
