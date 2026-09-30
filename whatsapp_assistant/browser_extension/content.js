(() => {
  "use strict";

  const BUILD = "0.2.1";
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (v) => String(v || "").replace(/\s+/g, " ").trim().toLocaleLowerCase();

  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  }

  function cleanTitle(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function currentChatTitle() {
    const header = document.querySelector("#main header") || document.querySelector("main header");
    if (!header) return "";

    const reject = /^(informaci[oó]n del perfil|profile info)$/i;
    const selectors = [
      '[data-testid="conversation-info-header-chat-title"]',
      '[data-testid="conversation-info-header"] span[dir="auto"]',
      '[role="button"] span[dir="auto"]',
      'span[dir="auto"]'
    ];

    for (const selector of selectors) {
      const candidates = [...header.querySelectorAll(selector)]
        .filter(visible)
        .map((el) => cleanTitle(el.textContent))
        .filter((t) => t && t.length < 180 && !reject.test(t));
      if (candidates.length) return candidates[0];
    }

    const titled = [...header.querySelectorAll("[title]")]
      .filter(visible)
      .map((el) => cleanTitle(el.getAttribute("title")))
      .filter((t) => t && t.length < 180 && !reject.test(t));
    if (titled.length) return titled[0];

    return "";
  }

  function chatRows() {
    const pane = document.querySelector("#pane-side") || document.querySelector('[aria-label*="lista" i]');
    if (!pane) return [];
    return [...pane.querySelectorAll('[role="listitem"], [role="row"], [data-testid="cell-frame-container"]')]
      .filter(visible);
  }

  function rowTitle(row) {
    const titled = [...row.querySelectorAll("[title]")]
      .filter(visible)
      .map((el) => cleanTitle(el.getAttribute("title")))
      .find(Boolean);
    if (titled) return titled;
    const auto = [...row.querySelectorAll('span[dir="auto"]')]
      .filter(visible)
      .map((el) => cleanTitle(el.textContent))
      .find(Boolean);
    return auto || "";
  }

  function matchingRows(expected) {
    const target = norm(expected);
    if (!target) return [];
    const rows = chatRows().map((row) => ({ row, title: rowTitle(row) })).filter((x) => x.title);
    const exact = rows.filter((x) => norm(x.title) === target);
    if (exact.length) return exact;
    return rows.filter((x) => norm(x.title).includes(target) || target.includes(norm(x.title)));
  }

  function sidebarSearchBox() {
    const side = document.querySelector("#side");
    if (!side) return null;
    const boxes = [...side.querySelectorAll('[contenteditable="true"][role="textbox"], [contenteditable="true"], input[type="text"]')]
      .filter(visible);
    const preferred = boxes.find((el) => {
      const hint = [
        el.getAttribute("aria-label"),
        el.getAttribute("placeholder"),
        el.getAttribute("data-tab"),
      ].filter(Boolean).join(" ").toLocaleLowerCase();
      return /buscar|search/.test(hint);
    });
    return preferred || boxes[0] || null;
  }

  function replaceEditableText(el, text) {
    el.focus();
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("selectAll", false, null);
    document.execCommand("insertText", false, text);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  }

  async function waitForChat(expected, timeoutMs = 6000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const actual = currentChatTitle();
      if (norm(actual) === norm(expected)) return actual;
      await sleep(150);
    }
    return currentChatTitle();
  }

  async function openChatByTitle(expected) {
    const wanted = cleanTitle(expected);
    if (!wanted) throw new Error("Debes indicar el nombre del chat.");

    const already = currentChatTitle();
    if (norm(already) === norm(wanted)) return already;

    let matches = matchingRows(wanted);
    if (!matches.length) {
      const search = sidebarSearchBox();
      if (!search) throw new Error("No se encontró el buscador lateral de WhatsApp Web.");
      replaceEditableText(search, wanted);
      await sleep(900);
      matches = matchingRows(wanted);
    }

    if (!matches.length) throw new Error(`No se encontró el chat "${wanted}" en WhatsApp Web.`);
    if (matches.length > 1) {
      const exact = matches.filter((x) => norm(x.title) === norm(wanted));
      if (exact.length === 1) matches = exact;
      else throw new Error(`Hay más de un chat que coincide con "${wanted}". Usa el título exacto.`);
    }

    const chosen = matches[0];
    chosen.row.scrollIntoView({ block: "center" });
    (chosen.row.querySelector("[title]") || chosen.row).click();

    const actual = await waitForChat(chosen.title, 7000);
    if (norm(actual) !== norm(chosen.title)) {
      throw new Error(`No se pudo confirmar la apertura del chat. Esperado: "${chosen.title}". Actual: "${actual || "desconocido"}".`);
    }

    const search = sidebarSearchBox();
    if (search) {
      try { replaceEditableText(search, ""); } catch (_err) {}
    }
    return actual;
  }

  function parseMetaTimestamp(meta) {
    const text = String(meta || "");
    const m = text.match(/\[(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?,\s*(\d{1,2})\/(\d{1,2})\/(\d{4})\]/i);
    if (!m) return null;
    let hour = Number(m[1]);
    const minute = Number(m[2]);
    const ap = m[3].toLocaleLowerCase();
    if (ap === "p" && hour < 12) hour += 12;
    if (ap === "a" && hour === 12) hour = 0;
    const day = Number(m[4]);
    const month = Number(m[5]) - 1;
    const year = Number(m[6]);
    const d = new Date(year, month, day, hour, minute, 0, 0);
    return Number.isFinite(d.getTime()) ? d.getTime() : null;
  }

  function parseISODate(dateText, endOfDay = false) {
    const m = String(dateText || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    const y = Number(m[1]);
    const mo = Number(m[2]) - 1;
    const d = Number(m[3]);
    const dt = endOfDay
      ? new Date(y, mo, d, 23, 59, 59, 999)
      : new Date(y, mo, d, 0, 0, 0, 0);
    return Number.isFinite(dt.getTime()) ? dt.getTime() : null;
  }

  function messageRoot() {
    const root = document.querySelector("#main");
    if (!root) throw new Error("No hay un chat abierto en WhatsApp Web.");
    return root;
  }

  function renderedMessageRows(root = messageRoot()) {
    return [...root.querySelectorAll("[data-id]")].filter((el) => {
      const id = String(el.getAttribute("data-id") || "").trim();
      return Boolean(id);
    });
  }

  function findMessageScroller(root = messageRoot()) {
    const rows = renderedMessageRows(root);
    const candidates = new Set();

    for (const row of rows.slice(0, 30)) {
      let el = row;
      for (let i = 0; el && i < 12; i += 1, el = el.parentElement) {
        if (el === document.body || el === document.documentElement) break;
        if (root.contains(el)) candidates.add(el);
        if (el === root) break;
      }
    }

    const known = [
      root.querySelector('[data-testid="conversation-panel-messages"]'),
      root.querySelector('.copyable-area'),
    ].filter(Boolean);
    known.forEach((el) => candidates.add(el));

    const scored = [...candidates]
      .filter((el) => visible(el) && el.clientHeight > 150)
      .map((el) => {
        const style = getComputedStyle(el);
        const overflow = /auto|scroll/.test(style.overflowY || "");
        const scrollable = el.scrollHeight > el.clientHeight + 80;
        const messageCount = el.querySelectorAll("[data-id]").length;
        let score = 0;
        if (overflow) score += 80;
        if (scrollable) score += 70;
        score += Math.min(messageCount, 40);
        if (el === root) score -= 50;
        return { el, score };
      })
      .sort((a, b) => b.score - a.score);

    return scored[0]?.el || null;
  }

  function extractRenderedMessages(store, sequenceRef) {
    const root = messageRoot();
    let added = 0;
    for (const row of renderedMessageRows(root)) {
      const id = String(row.getAttribute("data-id") || "").trim();
      if (!id || store.has(id)) continue;
      const bubble = row.closest(".message-in, .message-out") || row;
      const metaNode = bubble.querySelector("[data-pre-plain-text]");
      const meta = metaNode ? String(metaNode.getAttribute("data-pre-plain-text") || "") : "";
      const textNode = metaNode || bubble;
      const rawText = String(textNode.innerText || textNode.textContent || "")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
      if (!rawText) continue;

      sequenceRef.value += 1;
      store.set(id, {
        id,
        from_me: bubble.classList.contains("message-out") || /true_/.test(id),
        meta,
        text: rawText.slice(0, 4000),
        _ts: parseMetaTimestamp(meta),
        _seq: sequenceRef.value,
      });
      added += 1;
    }
    return added;
  }

  function oldestTimestamp(store) {
    let oldest = null;
    for (const msg of store.values()) {
      if (msg._ts == null) continue;
      if (oldest == null || msg._ts < oldest) oldest = msg._ts;
    }
    return oldest;
  }

  function newestTimestamp(store) {
    let newest = null;
    for (const msg of store.values()) {
      if (msg._ts == null) continue;
      if (newest == null || msg._ts > newest) newest = msg._ts;
    }
    return newest;
  }

  async function waitForHistoryGrowth(store, seq, beforeOldest, beforeSize, timeoutMs = 3500) {
    const deadline = Date.now() + timeoutMs;
    let bestOldest = oldestTimestamp(store);

    while (Date.now() < deadline) {
      extractRenderedMessages(store, seq);
      const nowOldest = oldestTimestamp(store);
      if (store.size > beforeSize) return true;
      if (beforeOldest != null && nowOldest != null && nowOldest < beforeOldest) return true;
      if (bestOldest == null || (nowOldest != null && nowOldest < bestOldest)) bestOldest = nowOldest;
      await sleep(150);
    }
    return false;
  }

  function nudgeHistoryUp(scroller, aggressive = false) {
    const amount = Math.max(500, Math.floor(scroller.clientHeight * (aggressive ? 2.5 : 0.9)));
    try {
      scroller.scrollBy({ top: -amount, left: 0, behavior: "instant" });
    } catch (_err) {
      scroller.scrollTop = Math.max(0, scroller.scrollTop - amount);
    }
    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
    try {
      scroller.dispatchEvent(new WheelEvent("wheel", {
        deltaY: -amount,
        bubbles: true,
        cancelable: true,
      }));
    } catch (_err) {}
  }

  async function scanHistory({ limit = 200, fromDate = "", toDate = "" } = {}) {
    const requested = Math.max(1, Math.min(Number(limit) || 200, 1500));
    const startTs = parseISODate(fromDate, false);
    const endTs = parseISODate(toDate, true);
    if (fromDate && startTs == null) throw new Error("from_date debe tener formato YYYY-MM-DD.");
    if (toDate && endTs == null) throw new Error("to_date debe tener formato YYYY-MM-DD.");
    if (startTs != null && endTs != null && startTs > endTs) throw new Error("from_date no puede ser posterior a to_date.");

    const store = new Map();
    const seq = { value: 0 };
    extractRenderedMessages(store, seq);

    const scroller = findMessageScroller();
    let scrolls = 0;
    let stalledRounds = 0;
    let rescueAttempts = 0;
    let stoppedWithoutProof = false;
    let reachedRequestedStart = startTs != null && oldestTimestamp(store) != null && oldestTimestamp(store) <= startTs;
    const maxScrolls = startTs != null ? 260 : Math.min(260, Math.max(40, Math.ceil(requested / 8) * 3));

    if (scroller && !reachedRequestedStart && store.size < requested) {
      while (scrolls < maxScrolls) {
        const beforeSize = store.size;
        const beforeOldest = oldestTimestamp(store);

        nudgeHistoryUp(scroller, stalledRounds >= 2);
        if (scroller.scrollTop <= 6) {
          try {
            scroller.scrollTop = 1;
            scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
          } catch (_err) {}
        }

        const grew = await waitForHistoryGrowth(
          store,
          seq,
          beforeOldest,
          beforeSize,
          stalledRounds >= 2 ? 5000 : 3000,
        );

        scrolls += 1;
        const oldest = oldestTimestamp(store);

        if (startTs != null && oldest != null && oldest <= startTs) {
          reachedRequestedStart = true;
          break;
        }
        if (startTs == null && store.size >= requested) break;

        if (grew) {
          stalledRounds = 0;
          continue;
        }

        stalledRounds += 1;

        if (stalledRounds >= 3 && rescueAttempts < 3) {
          rescueAttempts += 1;
          try {
            scroller.focus?.();
            scroller.dispatchEvent(new KeyboardEvent("keydown", {
              key: "Home",
              code: "Home",
              bubbles: true,
              cancelable: true,
            }));
          } catch (_err) {}
          nudgeHistoryUp(scroller, true);
          await waitForHistoryGrowth(store, seq, oldestTimestamp(store), store.size, 5500);
          stalledRounds = 0;
          continue;
        }

        if (stalledRounds >= 6) {
          stoppedWithoutProof = true;
          break;
        }
      }
    } else if (!scroller) {
      stoppedWithoutProof = true;
    }

    if (scroller) {
      try {
        scroller.scrollTop = scroller.scrollHeight;
        scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
      } catch (_err) {}
    }

    let messages = [...store.values()]
      .filter((m) => {
        if (startTs != null && m._ts != null && m._ts < startTs) return false;
        if (endTs != null && m._ts != null && m._ts > endTs) return false;
        if ((startTs != null || endTs != null) && m._ts == null) return false;
        return true;
      })
      .sort((a, b) => {
        if (a._ts != null && b._ts != null && a._ts !== b._ts) return a._ts - b._ts;
        if (a._ts == null && b._ts != null) return 1;
        if (a._ts != null && b._ts == null) return -1;
        return a._seq - b._seq;
      });

    const totalMatched = messages.length;
    let truncated = false;
    if (messages.length > requested) {
      messages = messages.slice(-requested);
      truncated = true;
    }
    messages = messages.map(({ _ts, _seq, ...m }) => m);

    const oldest = oldestTimestamp(store);
    const newest = newestTimestamp(store);
    const completeForRequestedRange = startTs != null
      ? reachedRequestedStart && !truncated
      : store.size >= requested && !truncated;

    return {
      messages,
      history: {
        requested_limit: requested,
        collected_unique: store.size,
        matched_range: totalMatched,
        returned: messages.length,
        scrolls,
        rescue_attempts: rescueAttempts,
        stalled_without_proof: stoppedWithoutProof,
        reached_history_top: false,
        reached_requested_start: reachedRequestedStart,
        truncated,
        oldest_timestamp: oldest ? new Date(oldest).toISOString() : null,
        newest_timestamp: newest ? new Date(newest).toISOString() : null,
        complete_for_requested_range: completeForRequestedRange,
      },
    };
  }

  function listVisibleChats(limit) {
    const out = [];
    const seen = new Set();
    for (const row of chatRows()) {
      const title = rowTitle(row);
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
    replaceEditableText(box, text);
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
      const before = currentChatTitle();
      if (!before) throw new Error("No se pudo identificar el chat abierto.");
      const scan = await scanHistory({ limit: job.payload?.limit });
      const after = currentChatTitle();
      if (norm(before) !== norm(after)) throw new Error("El chat cambió mientras se leía el historial.");
      return {
        ok: true,
        operation: job.operation,
        build: BUILD,
        url: location.href,
        chat_title: after,
        ...scan,
      };
    }

    if (job.operation === "read_chat_history") {
      const actual = await openChatByTitle(job.payload?.chat_title);
      const scan = await scanHistory({
        limit: job.payload?.limit,
        fromDate: job.payload?.from_date,
        toDate: job.payload?.to_date,
      });
      const after = currentChatTitle();
      if (norm(actual) !== norm(after)) throw new Error("El chat cambió mientras se leía el historial.");
      return {
        ok: true,
        operation: job.operation,
        build: BUILD,
        url: location.href,
        chat_title: after,
        from_date: job.payload?.from_date || null,
        to_date: job.payload?.to_date || null,
        ...scan,
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
      const expected = cleanTitle(job.payload?.chat_title);
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
