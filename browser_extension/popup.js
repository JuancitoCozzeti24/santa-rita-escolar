const endpoint = document.getElementById("endpoint");
const teacherEmail = document.getElementById("teacherEmail");
const secret = document.getElementById("secret");
const msg = document.getElementById("msg");
const DEFAULT_TEACHER_EMAIL = "jbringas@santaritadecasia.edu.pe";

(async () => {
  const data = await SieRoomConnection.config();
  if (data.endpoint) endpoint.value = data.endpoint;
  if (data.teacherEmail) {
    teacherEmail.value = data.teacherEmail;
  } else {
    teacherEmail.value = DEFAULT_TEACHER_EMAIL;
    await chrome.storage.local.set({ teacherEmail: DEFAULT_TEACHER_EMAIL });
  }
  if (data.secret) secret.value = data.secret;
})();

function validEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || "").trim());
}

async function save() {
  const ep = SieRoomConnection.normalizeEndpoint(endpoint.value);
  const email = teacherEmail.value.trim().toLowerCase();
  const sec = secret.value.trim();

  if (!validEmail(email)) throw new Error("Falta un correo docente válido.");
  await chrome.storage.local.set({ endpoint: ep, teacherEmail: email, secret: sec });
  return { ep, email, sec };
}

async function checkClassroomAccount(email) {
  const tabs = await chrome.tabs.query({url: "https://classroom.google.com/*"});
  if (!tabs.length) {
    return {
      state: "missing",
      message: `No hay una pestaña de Classroom abierta. Abre Classroom con ${email}.`
    };
  }

  // Verification does not depend on an injected or stale content script.
  // Check all visible Classroom tabs, not only the first/active one.
  const ordered = [...tabs]
    .filter(tab => Number.isInteger(tab.id))
    .sort((a,b) => Number(Boolean(b.active)) - Number(Boolean(a.active)));
  const mismatches = new Set();
  let unableToInspect = false;
  let loading = false;
  for (const tab of ordered.slice(0, 12)) {
    for (let retry = 0; retry < 3; retry++) {
      try {
        const execution = await chrome.scripting.executeScript({
          target: {tabId: tab.id},
          func: probeClassroomActiveAccount,
          args: [email]
        });
        const result = execution?.[0]?.result;
        if (result?.ok === true) {
          return {
            state: "ok",
            message: `Cuenta de Classroom verificada automáticamente: ${email}.`
          };
        }
        if (result?.ok === false) {
          for (const found of result.detectedEmails || []) mismatches.add(found);
          break;
        }
        if (result?.reason === "classroom_loading" && retry < 2) {
          loading = true;
          await new Promise(resolve => setTimeout(resolve, 180));
          continue;
        }
        break;
      } catch (_) {
        // Missing host access or a tab that navigated. Never claim success.
        unableToInspect = true;
        break;
      }
    }
  }

  if (mismatches.size) {
    return {
      state: "mismatch",
      message: `No se encontró la cuenta docente ${email} en las pestañas verificables. Cuentas activas detectadas: ${[...mismatches].join(", ")}.`
    };
  }
  return {
    state: "unknown",
    message: unableToInspect
      ? "No se pudo inspeccionar el control de cuenta de Classroom. Comprueba que la extensión tenga permiso para classroom.google.com."
      : loading
        ? "Classroom todavía está cargando el control de cuenta; vuelve a pulsar Guardar y probar cuando termine."
        : "No se ve el correo de la cuenta activa en el encabezado de Classroom. No se asumirá otra cuenta ni se publicarán notas sin verificarla."
  };
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    const { ep, email, sec } = await save();
    if (!sec) throw new Error("Falta el secreto.");

    const data = await SieRoomConnection.check(ep, sec);
    const extensionVersion = chrome.runtime.getManifest().version;

    const account = await checkClassroomAccount(email);
    msg.textContent =
      `Conexión correcta. Servidor ${data.version} · extensión ${extensionVersion}.\n` +
      account.message;
  } catch (e) {
    msg.textContent = `Error: ${String(e?.message || e)}`;
  }
});

document.getElementById("start").addEventListener("click", async () => {
  try {
    await save();
    const bridgeUrl = chrome.runtime.getURL("bridge.html");
    const existing = await chrome.tabs.query({ url: bridgeUrl + "*" });
    if (existing.length && existing[0].id) {
      await chrome.tabs.update(existing[0].id, { active: true });
    } else {
      await chrome.tabs.create({ url: bridgeUrl, active: true });
    }
    window.close();
  } catch (e) {
    msg.textContent = `Error: ${String(e?.message || e)}`;
  }
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
    body: JSON.stringify({ retry_failed: true }),
    cache: "no-store"
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);

  const bridgeUrl = chrome.runtime.getURL("bridge.html");
  const tabs = await chrome.tabs.query({ url: bridgeUrl + "*" });
  for (const tab of tabs) {
    try { await chrome.tabs.reload(tab.id); } catch (_) {}
  }

  const q = data.queue || {};
  msg.textContent =
    `RESET correcto. Liberados: ${data.released_count || 0}. ` +
    `Reintentados: ${data.retried_failed_count || 0}. ` +
    `Pendientes reales: ${q.work_remaining ?? ((q.queued || 0) + (q.claimed || 0))}. ` +
    `El puente retomará comentario, calificación y devolución desde Classroom.`;
}

document.getElementById("reset").addEventListener("click", async () => {
  try {
    await resetQueueFromPopup();
  } catch (e) {
    msg.textContent = `Error al resetear: ${String(e?.message || e)}`;
  }
});
