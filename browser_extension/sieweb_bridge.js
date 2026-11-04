/* SieRoom ↔ SIEweb: only uses a session already verified on the official website.
   Password, emailed code, cookies and Sie-Token stay in the user's browser.
   Requires open SIEweb intranet tab; no automated OTP submission. */
(() => {
  const OFFICIAL_ORIGIN = "https://santaritadecasia.sieweb.com.pe";
  const statusEl = document.getElementById("siewebStatus");
  let busy = false;
  let lastError = "";

  // This function runs in the SIEweb page MAIN world. No Bridge secret is passed.
  async function browserAction(args) {
    const origin = "https://santaritadecasia.sieweb.com.pe";
    if (location.origin !== origin || !location.pathname.startsWith("/sistema/intranet")) {
      return {session_verified: false, reason: "wrong_site_or_login_screen"};
    }
    const pageText = String(document.body?.innerText || "").toUpperCase();
    if (!pageText.includes("BRINGAS BENITES")) {
      return {session_verified: false, reason: "teacher_account_not_verified"};
    }
    if (args.action === "ping") return {session_verified: true};

    const path = String(args.path || "");
    if (
      !path.startsWith("/lms/api/") || path.startsWith("/lms/api/login/") ||
      path.includes("..") || path.includes("//") || path.includes("?") ||
      path.includes("#") || path.includes("\\")
    ) return {status_code: 400, error: "path_not_allowed"};

    const method = String(args.method || "GET").toUpperCase();
    if (!["GET", "POST", "PUT"].includes(method)) {
      return {status_code: 400, error: "method_not_allowed"};
    }

    const makeCandidate = (raw) => {
      if (typeof raw !== "string") return "";
      const s = raw.trim();
      if (/^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(s)) return s;
      if (s.length > 25000 || !s.startsWith("{")) return "";
      try {
        const data = JSON.parse(s);
        const candidates = [data.token, data.accessToken, data.sieToken, data.data?.token, data.json?.token];
        return candidates.find(t => typeof t === "string" && /^eyJ/.test(t)) || "";
      } catch (_) {return "";}
    };
    let token = "";
    let userCode = "";
    try {
      for (const store of [localStorage, sessionStorage]) {
        for (let i = 0; i < store.length; i++) {
          const key = store.key(i) || "";
          if (!/token|sesion|session|auth|login|usucod|usuario|sieweb|user/i.test(key)) continue;
          const value = store.getItem(key) || "";
          if (!token) token = makeCandidate(value);
          if (!userCode) {
            if (/^(usucod|usercode|codigo_usuario)$/i.test(key) && /^[A-Za-z0-9_-]{3,32}$/.test(value)) {
              userCode = value;
            } else if (value.startsWith("{") && value.length < 25000) {
              try {
                const obj = JSON.parse(value);
                const code = obj.usucod || obj.USUCOD || obj.infoColegio?.usucod || obj.json?.infoColegio?.usucod;
                if (typeof code === "string" && /^[A-Za-z0-9_-]{3,32}$/.test(code)) userCode = code;
              } catch (_) {}
            }
          }
        }
      }
    } catch (_) { /* Storage blocked: try the authenticated cookie route. */ }

    if (!token) {
      // Official cookie refresh endpoint already used by the old SieRoom client.
      // The returned JWT is used only inside the page; it never goes to Render.
      try {
        const refresh = await fetch("/lms/api/login/getTokenConCookie", {
          method: "GET", credentials: "include", cache: "no-store",
          headers: {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"},
        });
        if (refresh.ok) {
          const raw = await refresh.text();
          token = makeCandidate(raw.replace(/^"|"$/g, "")) || makeCandidate(raw);
        }
      } catch (_) {}
    }

    const uri = new URL(path, origin);
    if (uri.origin !== origin || !uri.pathname.startsWith("/lms/api/")) {
      return {status_code: 400, error: "origin_changed"};
    }
    const params = args.params || {};
    if (params && typeof params === "object" && !Array.isArray(params)) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined) uri.searchParams.append(key, String(value));
      }
    }
    const headers = new Headers({
      "Accept": "application/json, text/plain, */*",
      "X-Requested-With": "XMLHttpRequest",
      "Cache-Control": "no-cache",
      "Pragma": "no-cache",
      "X-Tab-Refresh": "1",
      "X-Tab-Id": crypto.randomUUID(),
    });
    if (token) headers.set("Sie-Token", token);
    if (userCode) headers.set("X-Usucod", userCode);
    const options = {method, credentials:"include", cache:"no-store", headers};
    if (method !== "GET") {
      headers.set("Content-Type", "application/json");
      options.body = JSON.stringify(args.payload ?? {});
    }
    try {
      const response = await fetch(uri.toString(), options);
      const ct = (response.headers.get("content-type") || "").toLowerCase();
      if (!ct.includes("json")) return {status_code: 502, error: "unexpected_content_type"};
      const data = await response.json();
      // Never return auth endpoints or raw tokens to the Bridge.
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        return {status_code: 502, error: "non_object_response"};
      }
      if (data.token || data.accessToken || data.refreshToken) {
        return {status_code: 502, error: "auth_material_in_response"};
      }
      return {status_code: response.status, data};
    } catch (_) {
      return {status_code: 503, error: "site_request_failed"};
    }
  }

  async function getVerifiedTab() {
    const tabs = await chrome.tabs.query({url: OFFICIAL_ORIGIN + "/sistema/intranet*"});
    for (const tab of tabs.slice(0, 5)) {
      if (!Number.isInteger(tab.id)) continue;
      try {
        const a = await chrome.scripting.executeScript({
          target: {tabId: tab.id},
          world: "MAIN",
          func: browserAction,
          args: [{action: "ping"}],
        });
        if (a?.[0]?.result?.session_verified === true) return tab.id;
      } catch (_) {}
    }
    return null;
  }

  async function isLeader() {
    try {
      const self = await chrome.tabs.getCurrent();
      const pages = (await chrome.tabs.query({url: chrome.runtime.getURL("bridge.html") + "*"}))
        .filter(t => Number.isInteger(t.id)).sort((a,b) => a.id-b.id);
      return Boolean(self?.id && pages[0]?.id === self.id);
    } catch (_) {return false;}
  }

  async function request(path, options = {}) {
    const c = await SieRoomConnection.config();
    if (!c.secret) throw Error("bridge_secret_not_configured");
    const headers = SieRoomConnection.headers(c.secret, options.headers || {});
    const opts = {...options, headers};
    if (options.body) headers.set("Content-Type", "application/json");
    const result = await SieRoomConnection.request(c.endpoint, path, opts);
    return result.data;
  }

  let lastRequestWasVerified = false;

  async function poll() {
    if (busy) return false;
    busy = true;
    lastRequestWasVerified = false;
    try {
      if (!await isLeader()) return false;
      const tabId = await getVerifiedTab();
      const verified = Number.isInteger(tabId);
      await request("/bridge/v1/sieweb/pulse", {
        method: "POST",
        body: JSON.stringify({
          session_verified: verified,
          reason: verified ? "" : "missing_verified_sieweb_tab"
        }),
      });
      if (!verified) {
        statusEl.textContent = "SIEweb: abre tu sesión oficial e ingresa el código recibido por correo.";
        return false;
      }
      lastRequestWasVerified = true;
      statusEl.textContent = "SIEweb: sesión docente verificada en el navegador.";
      // HTTP long polling, not setInterval: Chrome throttles background tab
      // timers to approximately 60 seconds, longer than an MCP tool timeout.
      const next = await request("/bridge/v1/sieweb/wait");
      if (!next.job) return true;
      const job = next.job;
      let result;
      try {
        const executed = await chrome.scripting.executeScript({
          target: {tabId},
          world: "MAIN",
          func: browserAction,
          args: [{action: "api", method:job.method, path:job.path, params:job.params, payload:job.payload}],
        });
        result = executed?.[0]?.result || {status_code: 503, error: "browser_result_missing"};
      } catch (_) {
        result = {status_code: 503, error: "browser_execution_failed"};
      }
      // A claimed job is never replayed; report even failed calls once.
      await request("/bridge/v1/sieweb/result", {
        method: "POST",
        body: JSON.stringify({job_id:job.id, ...result}),
      });
      if (result.status_code >= 400) {
        statusEl.textContent = "SIEweb: sesión visible; la API respondió " +
          (result.error || ("HTTP " + result.status_code)) +
          ". Comprueba que la pestaña oficial continúe autenticada.";
      }
      return true;
    } catch (e) {
      lastError = String(e?.message || "Error de conexión");
      statusEl.textContent = "SIEweb: puente no disponible. " + lastError.slice(0,130);
      return false;
    } finally {
      busy = false;
    }
  }

  async function runLongPoll() {
    for (;;) {
      const healthy = await poll();
      if (!healthy) {
        // No authenticated tab or temporary offline: throttle retries.
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
      // When healthy, each 18s long poll refreshes the authenticated pulse.
      // Avoid setInterval here: timers in hidden tabs are heavily throttled.
    }
  }

  runLongPoll();
})();
