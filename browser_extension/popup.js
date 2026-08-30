const DEFAULT_TEACHER_EMAIL = "jbringas@santaritadecasia.edu.pe";
const endpoint = document.getElementById("endpoint");
const teacherEmail = document.getElementById("teacherEmail");
const secret = document.getElementById("secret");
const msg = document.getElementById("msg");

(async () => {
  const data = await chrome.storage.local.get(["endpoint", "teacherEmail", "secret"]);
  if (data.endpoint) endpoint.value = data.endpoint;
  teacherEmail.value = data.teacherEmail || DEFAULT_TEACHER_EMAIL;
  if (data.secret) secret.value = data.secret;
})();

function validEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || "").trim());
}

async function save() {
  const ep = endpoint.value.trim().replace(/\/$/, "");
  const email = teacherEmail.value.trim().toLowerCase();
  const sec = secret.value.trim();

  if (!validEmail(email)) throw new Error("Falta un correo docente válido.");
  await chrome.storage.local.set({ endpoint: ep, teacherEmail: email, secret: sec });
  return { ep, email, sec };
}

async function checkClassroomAccount(email) {
  const tabs = await chrome.tabs.query({ url: "https://classroom.google.com/*" });
  if (!tabs.length) {
    return {
      state: "missing",
      message: `No hay una pestaña de Classroom abierta. Abre Classroom con ${email}.`
    };
  }

  // Preferimos una pestaña activa de Classroom.
  const tab = tabs.find(t => t.active) || tabs[0];
  try {
    const r = await chrome.tabs.sendMessage(tab.id, {
      type: "SIEROOM_CHECK_ACCOUNT",
      expectedEmail: email
    });
    if (!r) return { state: "unknown", message: "No pude verificar todavía la cuenta de Classroom." };
    if (r.ok === true) {
      return { state: "ok", message: `Cuenta de Classroom confirmada: ${email}` };
    }
    if (r.ok === false) {
      const detected = (r.detectedEmails || []).join(", ") || "otra cuenta";
      return {
        state: "mismatch",
        message: `CUENTA INCORRECTA. Se esperaba ${email}; Classroom muestra ${detected}.`
      };
    }
    return {
      state: "unknown",
      message: `Servidor correcto, pero no pude confirmar la cuenta activa. El Bridge no procesará nada hasta verla de forma explícita en Classroom.`
    };
  } catch (_) {
    return {
      state: "unknown",
      message: `Classroom está abierto, pero el verificador aún no respondió. Recarga la pestaña de Classroom.`
    };
  }
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    const { ep, email, sec } = await save();
    if (!sec) throw new Error("Falta el secreto.");

    const r = await fetch(`${ep}/bridge/v1/status`, {
      headers: { "X-SieRoom-Bridge-Secret": sec },
      cache: "no-store"
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    const extensionVersion = chrome.runtime.getManifest().version;
    if (String(data.version || "") !== extensionVersion) {
      throw new Error(
        `Versiones distintas: servidor ${data.version || "desconocida"} · ` +
        `extensión ${extensionVersion}. Espera el despliegue antes de procesar.`
      );
    }

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
