(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none";
  };

  function privateCommentLabel() {
    const nodes = [...document.querySelectorAll("body *")];
    const hits = nodes.filter((el) => {
      const t = norm(el.textContent).trim();
      return visible(el) && t.length > 0 && t.length < 80 && (t.includes("comentarios privados") || t.includes("private comments"));
    });
    hits.sort((a, b) => (a.textContent || "").length - (b.textContent || "").length);
    return hits[0] || null;
  }

  function candidateContainers(label) {
    const out = [];
    let cur = label;
    for (let i = 0; cur && i < 9; i++, cur = cur.parentElement) out.push(cur);
    return out;
  }

  function findComposer(label) {
    const selectors = [
      'textarea[aria-label*="coment" i]',
      'textarea[placeholder*="coment" i]',
      '[role="textbox"][contenteditable="true"]',
      'textarea'
    ];
    for (const container of candidateContainers(label)) {
      for (const sel of selectors) {
        const hit = [...container.querySelectorAll(sel)].find(visible);
        if (hit) return { composer: hit, container };
      }
    }
    // Fallback global, pero solo si el aria/placeholder indica comentario.
    return { composer: [...document.querySelectorAll('textarea,[role="textbox"][contenteditable="true"]')].find((el) => {
      const meta = norm(`${el.getAttribute("aria-label") || ""} ${el.getAttribute("placeholder") || ""}`);
      return visible(el) && meta.includes("coment");
    }) || null, container: label?.parentElement || document.body };
  }

  function setComposerValue(el, value) {
    el.focus();
    if (el instanceof HTMLTextAreaElement) {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter ? setter.call(el, value) : (el.value = value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    if (el instanceof HTMLInputElement) {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter ? setter.call(el, value) : (el.value = value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    el.textContent = value;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
  }

  function findSendButton(container, composer) {
    const roots = [container, composer.parentElement, composer.parentElement?.parentElement].filter(Boolean);
    const wanted = ["enviar", "publicar", "send", "post", "comentar", "comment"];
    for (const root of roots) {
      const buttons = [...root.querySelectorAll('button,[role="button"]')].filter(visible);
      for (const b of buttons) {
        if (b.disabled || b.getAttribute("aria-disabled") === "true") continue;
        const meta = norm([
          b.getAttribute("aria-label"), b.getAttribute("title"), b.textContent,
          b.getAttribute("data-tooltip"), b.getAttribute("jsname")
        ].filter(Boolean).join(" "));
        if (wanted.some((x) => meta.includes(x))) return b;
      }
    }
    return null;
  }

  async function waitForPrivateSection(timeoutMs = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const label = privateCommentLabel();
      if (label) {
        const found = findComposer(label);
        if (found.composer) return { label, ...found };
      }
      await sleep(500);
    }
    throw new Error("No encontré el cuadro de Comentarios privados en esta entrega.");
  }

  async function postPrivateComment(comment) {
    const text = String(comment || "").trim();
    if (!text) throw new Error("Comentario vacío.");
    const { label, composer, container } = await waitForPrivateSection();
    const beforeText = norm(container.textContent);
    if (beforeText.includes(norm(text))) {
      return { ok: true, alreadyPresent: true, method: "dom", url: location.href };
    }
    setComposerValue(composer, text);
    await sleep(400);
    const send = findSendButton(container, composer);
    if (!send) {
      throw new Error("Encontré el cuadro de comentario privado, pero no pude identificar de forma segura el botón Enviar/Publicar.");
    }
    send.click();
    const started = Date.now();
    while (Date.now() - started < 15000) {
      await sleep(500);
      const label2 = privateCommentLabel() || label;
      let scope = label2;
      for (let i = 0; scope && i < 7; i++, scope = scope.parentElement) {
        if (norm(scope.textContent).includes(norm(text))) {
          return { ok: true, alreadyPresent: false, method: "dom", url: location.href };
        }
      }
    }
    throw new Error("Se pulsó Enviar/Publicar, pero no pude confirmar visualmente que el comentario apareciera.");
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "SIEROOM_POST_PRIVATE_COMMENT") return;
    postPrivateComment(msg.comment)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err), url: location.href }));
    return true;
  });
})();
