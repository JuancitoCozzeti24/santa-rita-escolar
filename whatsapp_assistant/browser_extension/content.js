(() => {
  "use strict";

  const BUILD = "0.1.0";
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (v) => String(v || "").replace(/\s+/g, " ").trim().toLocaleLowerCase();

  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  }

  function currentChatTitle() {
    const header = document.querySelector("#main header") || document.querySelector("main header");
    if (!header) return "";
    const titled = [...header.querySelectorAll("[title]")]
      .filter(visible)
      .map((el) => String(el.getAttribute("title") || "").trim())
      .filter(Boolean);
    if (titled.length) return titled[0];
    const spans = [...header.querySelectorAll("span")]
      .filter(visible)
      .map((el) => String(el.textContent || "").replace(/\s+/g, " ").trim())
      .filter((t) => t && t.length < 180);
    return spans[0] || "";
  }

  function readMessages(limit) {
    const root = document.querySelector("#main");
    if (!root) throw new Error("No hay un chat abierto en WhatsApp Web.");

    const candidates = [...root.querySelectorAll("[data-id]")].filter(visible);
    const seen = new Set();
    const messages = [];

    for (const row of candidates) {
      const id = String(row.getAttribute("data-id") || "").trim();
      if (!id || seen.has(id)) continue;
      const bubble = row.closest(".message-in, .message-out") || row;
      const textNode = bubble.querySelector("[data-pre-plain-text]") || bubble;
      const rawText = String(textNode.innerText || textNode.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
      if (!rawText) continue;
      const metaNode = bubble.querySelector("[data-pre-plain-text]");
      const meta = metaNode ? String(metaNode.getAttribute("data-pre-plain-text") || "") : "";
      seen.add(id);
      messages.push({
        id,
        from_me: bubble.classList.contains("message-out") || /true_/.test(id),
        meta,
        text: rawText.slice(0, 5000),
      });
    }
    return messages.slice(-Math.max(1, Math.min(Number(limit) || 40, 200)));
  }

  function listVisibleChats(limit) {
    const pane = document.querySelector("#pane-side") || document.querySelector('[aria-label*="lista" i]');
    if (!pane) throw new Error("No se encontró la lista lateral de chats.");
    const rows = [...pane.querySelectorAll('[role="listitem"], [role="row"], [data-testid="cell-frame-container"]')]
      .filter(visible);
    const out = [];
    const seen = new Set();
    for (const row of rows) {
      const titleEl = row.querySelector("[title]");
      const title = String(titleEl?.getAttribute("title") || "").trim();
      if (!title || seen.has(norm(title))) continue;
      seen.add(norm(title));
      const text = String(row.innerText || "").replace(/\s+/g, " ").trim();
      out.push({ title, preview: text.slice(0, 500) });
      if (out.length >= Math.max(1, Math.min(Number(limit) || 50, 100))) break;
    }
    return out;
  }

  function composer() {
    const footer = document.querySelector("#main footer") || document.querySelector("footer");
    if (!footer) return null;
    const boxes = [...footer.querySelectorAll('[contenteditable="true"][role="textbox"], [contenteditable="true"]')]
      .filter(visible);
    return boxes[boxes.length - 1] || null;
  }

  function setComposerText(box, text) {
    box.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(box);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("selectAll", false, null);
    document.execCommand("insertText", false, text);
    box.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  }

  function sendButton() {
    const footer = document.querySelector("#main footer") || document.querySelector("footer");
    if (!footer) return null;
    const icon = footer.querySelector('[data-icon="send"]');
    if (icon) return icon.closest("button") || icon.parentElement;
    return [...footer.querySelectorAll("button")].find((b) => {
      const aria = String(b.getAttribute("aria-label") || "").toLocaleLowerCase();
      return visible(b) && (aria.includes("enviar") || aria.includes("send"));
    }) || null;
  }

  async function execute(job) {
    if (!job || !job.operation) throw new Error("Trabajo inválido.");
    if (job.operation === "read_current_chat") {
      return {
        ok: true,
        operation: job.operation,
        build: BUILD,
        url: location.href,
        chat_title: currentChatTitle(),
        messages: readMessages(job.payload?.limit),
      };
    }
    if (job.operation === "list_visible_chats") {
      return {
        ok: true,
        operation: job.operation,
        build: BUILD,
        url: location.href,
        chats: listVisibleChats(job.payload?.limit),
      };
    }
    if (job.operation === "send_message") {
      const expected = String(job.payload?.chat_title || "").trim();
      const message = String(job.payload?.message || "");
      const actual = currentChatTitle();
      if (!expected || norm(actual) !== norm(expected)) {
        throw new Error(`Chat abierto distinto. Esperado: "${expected}". Actual: "${actual || "desconocido"}".`);
      }
      if (!message.trim()) throw new Error("El mensaje está vacío.");
      const box = composer();
      if (!box) throw new Error("No se encontró el cuadro de escritura.");
      setComposerText(box, message);
      await sleep(150);
      const button = sendButton();
      if (!button || !visible(button)) throw new Error("No se encontró el botón Enviar.");
      button.click();
      await sleep(450);
      const currentComposer = composer();
      const remaining = String(currentComposer?.innerText || currentComposer?.textContent || "").trim();
      if (remaining) throw new Error("WhatsApp no confirmó el envío: el cuadro de escritura no quedó vacío.");
      return {
        ok: true,
        operation: job.operation,
        build: BUILD,
        url: location.href,
        sent: true,
        chat_title: actual,
        message,
      };
    }
    throw new Error(`Operación no soportada: ${job.operation}`);
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "JOHNNY_WA_EXECUTE") return undefined;
    execute(msg.job)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err) }));
    return true;
  });
})();
