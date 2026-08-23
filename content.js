(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  const visible = (el) => {
    if (!el || !(el instanceof Element)) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none";
  };

  const isEditable = (el) => {
    if (!el || !(el instanceof Element)) return false;
    if (el instanceof HTMLTextAreaElement) return !el.disabled && !el.readOnly;
    if (el instanceof HTMLInputElement) {
      const t = norm(el.type || "text");
      return !el.disabled && !el.readOnly && ["text", "search", ""].includes(t);
    }
    return el.getAttribute("contenteditable") === "true" || el.getAttribute("role") === "textbox";
  };

  const meta = (el) => norm([
    el?.getAttribute?.("aria-label"),
    el?.getAttribute?.("placeholder"),
    el?.getAttribute?.("data-placeholder"),
    el?.getAttribute?.("title"),
    el?.getAttribute?.("data-tooltip"),
    el?.getAttribute?.("aria-description"),
    el?.innerText && el.innerText.length < 140 ? el.innerText : "",
    el?.textContent && el.textContent.length < 140 ? el.textContent : "",
  ].filter(Boolean).join(" "));

  const isPrivateLabelText = (text) => {
    const t = norm(text);
    return t.includes("comentarios privados") || t.includes("private comments");
  };

  const isCommentComposerText = (text) => {
    const t = norm(text);
    return [
      "anade un comentario", "agrega un comentario", "añadir comentario",
      "escribe un comentario", "comentario privado", "private comment",
      "add a comment", "add comment", "write a comment"
    ].some((x) => t.includes(norm(x))) || t.includes("coment") || t.includes("comment");
  };

  function privateCommentLabel() {
    const nodes = [...document.querySelectorAll("body *")];
    const hits = nodes.filter((el) => {
      const t = norm(el.textContent);
      return visible(el) && t.length > 0 && t.length < 100 && isPrivateLabelText(t);
    });
    hits.sort((a, b) => (a.textContent || "").length - (b.textContent || "").length);
    return hits[0] || null;
  }

  function ancestorChain(el, max = 14) {
    const out = [];
    let cur = el;
    for (let i = 0; cur && i < max; i++, cur = cur.parentElement) out.push(cur);
    return out;
  }

  function commonAncestorDistance(a, b) {
    if (!a || !b) return 999;
    const aa = ancestorChain(a, 16);
    const bb = new Map(ancestorChain(b, 16).map((el, i) => [el, i]));
    for (let i = 0; i < aa.length; i++) {
      if (bb.has(aa[i])) return i + bb.get(aa[i]);
    }
    return 999;
  }

  function scoreCandidate(el, label) {
    if (!visible(el)) return -9999;
    const m = meta(el);
    if (!isCommentComposerText(m)) return -9999;

    let score = 0;
    if (isEditable(el)) score += 100;
    if (m.includes("anade un comentario") || m.includes("add a comment") || m.includes("private comment") || m.includes("comentario privado")) score += 55;
    if (m.includes("coment") || m.includes("comment")) score += 25;

    if (label) {
      const d = commonAncestorDistance(el, label);
      score += Math.max(0, 45 - d * 4);
      const er = el.getBoundingClientRect();
      const lr = label.getBoundingClientRect();
      if (er.top >= lr.top - 30) score += 12;
      if (Math.abs(er.left - lr.left) < 520) score += 18;
    }
    return score;
  }

  function composerCandidates(label) {
    const selector = [
      "textarea", "input", '[role="textbox"]', '[contenteditable="true"]',
      "[aria-label]", "[placeholder]", "[data-placeholder]", "[aria-description]"
    ].join(",");

    const unique = [...new Set(document.querySelectorAll(selector))];
    return unique
      .map((el) => ({ el, score: scoreCandidate(el, label) }))
      .filter((x) => x.score > -9999)
      .sort((a, b) => b.score - a.score);
  }

  function nearbyEditableCandidates(label, anchor) {
    const selector = 'textarea,input,[role="textbox"],[contenteditable="true"]';
    const lr = label?.getBoundingClientRect?.();
    const ar = anchor?.getBoundingClientRect?.();
    return [...document.querySelectorAll(selector)]
      .filter((el) => visible(el) && isEditable(el))
      .map((el) => {
        const er = el.getBoundingClientRect();
        let score = 0;
        const m = meta(el);
        if (isCommentComposerText(m)) score += 80;
        if (label) {
          const d = commonAncestorDistance(el, label);
          score += Math.max(0, 55 - d * 5);
          if (lr && Math.abs(er.left - lr.left) < 520) score += 25;
          if (lr && er.top >= lr.top - 40) score += 15;
        }
        if (anchor) {
          const d = commonAncestorDistance(el, anchor);
          score += Math.max(0, 70 - d * 7);
          if (ar && Math.abs(er.left - ar.left) < 260) score += 25;
          if (ar && Math.abs(er.top - ar.top) < 220) score += 25;
        }
        return { el, score };
      })
      .filter((x) => x.score >= 45)
      .sort((a, b) => b.score - a.score);
  }

  function placeholderTriggers(label) {
    const nodes = [...document.querySelectorAll("body *")];
    return nodes
      .filter((el) => {
        if (!visible(el) || isEditable(el)) return false;
        const m = meta(el);
        if (!m || m.length > 180) return false;
        const exactish = [
          "anade un comentario", "agrega un comentario", "escribe un comentario",
          "add a comment", "write a comment", "comentario privado", "private comment"
        ].some((x) => m.includes(norm(x)));
        return exactish;
      })
      .map((el) => ({ el, score: scoreCandidate(el, label) + 15 }))
      .sort((a, b) => b.score - a.score);
  }

  function bestPrivateRegion(label, composer) {
    if (!label) return document.body;
    const composerAncestors = new Set(ancestorChain(composer, 16));
    for (const el of ancestorChain(label, 16)) {
      if (composerAncestors.has(el) && el !== document.body && el !== document.documentElement) return el;
    }
    return label.parentElement || document.body;
  }

  async function findOrActivateComposer(label) {
    let candidates = composerCandidates(label);
    let editable = candidates.find((x) => isEditable(x.el));
    if (editable) return editable.el;

    // Classroom a veces muestra un contenedor "Añade un comentario…" que solo crea
    // el editor real después de hacer clic. Activamos únicamente un disparador que
    // esté claramente identificado como comentario y cerca de "Comentarios privados".
    const triggers = placeholderTriggers(label);
    for (const { el } of triggers.slice(0, 5)) {
      try {
        el.scrollIntoView({ block: "nearest", inline: "nearest" });
        el.click();
        await sleep(250);

        const active = document.activeElement;
        if (visible(active) && isEditable(active)) return active;

        candidates = composerCandidates(label);
        editable = candidates.find((x) => isEditable(x.el));
        if (editable) return editable.el;

        // Algunos editores de Classroom no conservan aria-label/placeholder en el
        // nodo editable que aparece después del clic. En ese caso usamos únicamente
        // editables espacial y estructuralmente cercanos al disparador privado.
        const nearby = nearbyEditableCandidates(label, el);
        if (nearby.length) return nearby[0].el;
      } catch (_) {}
    }
    return null;
  }

  function setNativeValue(el, value) {
    if (el instanceof HTMLTextAreaElement) {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter ? setter.call(el, value) : (el.value = value);
    } else if (el instanceof HTMLInputElement) {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter ? setter.call(el, value) : (el.value = value);
    }
  }

  function setComposerValue(el, value) {
    el.focus();

    if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
      setNativeValue(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }

    // Editores contenteditable de Google suelen reaccionar mejor a una edición real
    // que a asignar textContent directamente.
    try {
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand("insertText", false, value);
    } catch (_) {}

    if (!norm(el.innerText || el.textContent).includes(norm(value))) {
      el.textContent = value;
    }
    try {
      el.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, inputType: "insertText", data: value }));
    } catch (_) {}
    try {
      el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
    } catch (_) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function findSendButton(container, composer) {
    const roots = [
      container,
      composer?.parentElement,
      composer?.parentElement?.parentElement,
      composer?.parentElement?.parentElement?.parentElement,
    ].filter(Boolean);

    const wanted = [
      "enviar", "publicar", "send", "post", "comentar", "comment",
      "publica comentario", "enviar comentario"
    ];

    const seen = new Set();
    const scored = [];
    for (const root of roots) {
      for (const b of root.querySelectorAll('button,[role="button"]')) {
        if (seen.has(b) || !visible(b)) continue;
        seen.add(b);
        if (b.disabled || b.getAttribute("aria-disabled") === "true") continue;
        const m = meta(b);
        let score = 0;
        for (const w of wanted) if (m.includes(norm(w))) score += 25;
        if (m.includes("coment") || m.includes("comment")) score += 20;
        if (m.includes("enviar") || m.includes("send") || m.includes("publicar") || m.includes("post")) score += 35;
        if (score > 0) scored.push({ b, score });
      }
    }
    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.b || null;
  }

  function commentVisibleOutsideComposer(text, composer) {
    const wanted = norm(text);
    const nodes = [...document.querySelectorAll("body *")];
    return nodes.some((el) => {
      if (!visible(el) || el === composer || composer?.contains?.(el) || el.contains?.(composer)) return false;
      const t = norm(el.textContent);
      return t.length >= wanted.length && t.length < wanted.length + 400 && t.includes(wanted);
    });
  }

  function diagnostics(label) {
    const cand = composerCandidates(label).slice(0, 5).map(({ el, score }) => ({
      tag: el.tagName,
      role: el.getAttribute("role") || "",
      contenteditable: el.getAttribute("contenteditable") || "",
      aria: (el.getAttribute("aria-label") || "").slice(0, 80),
      placeholder: (el.getAttribute("placeholder") || el.getAttribute("data-placeholder") || "").slice(0, 80),
      score,
    }));
    return JSON.stringify({ label: Boolean(label), candidates: cand, url: location.href });
  }

  async function waitForPrivateSection(timeoutMs = 35000) {
    const started = Date.now();
    let lastLabel = null;
    while (Date.now() - started < timeoutMs) {
      const label = privateCommentLabel();
      if (label) lastLabel = label;
      if (label) {
        const composer = await findOrActivateComposer(label);
        if (composer) {
          const container = bestPrivateRegion(label, composer);
          return { label, composer, container };
        }
      }
      await sleep(500);
    }
    throw new Error(`No encontré el editor de Comentarios privados en esta entrega. Diagnóstico: ${diagnostics(lastLabel)}`);
  }

  async function postPrivateComment(comment) {
    const text = String(comment || "").trim();
    if (!text) throw new Error("Comentario vacío.");

    const { label, composer, container } = await waitForPrivateSection();
    const beforeText = norm(container?.textContent || "");
    if (beforeText.includes(norm(text)) || commentVisibleOutsideComposer(text, composer)) {
      return { ok: true, alreadyPresent: true, method: "dom-v0.7.3", url: location.href };
    }

    composer.scrollIntoView({ block: "nearest", inline: "nearest" });
    setComposerValue(composer, text);
    await sleep(650);

    const send = findSendButton(container, composer);
    if (!send) {
      throw new Error(`Encontré el editor de comentario privado, pero no pude identificar de forma segura el botón Enviar/Publicar. Diagnóstico: ${diagnostics(label)}`);
    }

    send.click();
    const started = Date.now();
    while (Date.now() - started < 18000) {
      await sleep(500);
      if (commentVisibleOutsideComposer(text, composer)) {
        return { ok: true, alreadyPresent: false, method: "dom-v0.7.3", url: location.href };
      }
    }
    throw new Error("Se pulsó Enviar/Publicar, pero no pude confirmar visualmente que el comentario apareciera.");
  }

  function cleanCommentText(value) {
    return String(value || "")
      .replace(/\r/g, "")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n[ \t]+/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function privateCommentMarkers(text) {
    const t = norm(text);
    return [
      "lo que hizo bien", "lo que debe mejorar", "sugerencias",
      "nota cuantitativa", "calificacion cuantitativa",
      "nota cualitativa", "calificacion cualitativa",
    ].filter((marker) => t.includes(marker));
  }

  function isPrivateCommentUiText(text) {
    const t = norm(text);
    if (!t) return true;
    return [
      "comentarios privados", "private comments", "anade un comentario",
      "agrega un comentario", "escribe un comentario", "add a comment",
      "write a comment", "enviar", "send", "publicar", "post",
    ].includes(t);
  }

  function commentReadCandidates(container, label, composer) {
    const semanticSelector = '[data-comment-id],[role="article"],[role="listitem"],li,div';
    const rows = [];
    for (const el of container.querySelectorAll(semanticSelector)) {
      if (!visible(el) || el === label || label?.contains?.(el)) continue;
      if (el === composer || composer?.contains?.(el) || el.contains?.(composer)) continue;
      const text = cleanCommentText(el.innerText || el.textContent || "");
      if (text.length < 2 || text.length > 6000 || isPrivateCommentUiText(text)) continue;
      const markers = privateCommentMarkers(text);
      const semantic = el.matches('[data-comment-id],[role="article"],[role="listitem"],li');
      if (markers.length < 2 && !semantic) continue;
      rows.push({ text, markers, semantic });
    }

    // Los contenedores de Classroom están anidados. Elegimos primero el nodo más
    // pequeño que conserva el comentario completo y descartamos padres que solo
    // repiten el mismo texto junto con controles de interfaz.
    rows.sort((a, b) => a.text.length - b.text.length);
    const chosen = [];
    for (const row of rows) {
      const key = norm(row.text);
      if (chosen.some((item) => norm(item.text) === key)) continue;
      if (chosen.some((item) => key.includes(norm(item.text)) && key.length > norm(item.text).length + 35)) continue;
      chosen.push(row);
    }
    return chosen;
  }

  async function readPrivateComments() {
    const { label, composer, container } = await waitForPrivateSection();
    await sleep(500);
    const candidates = commentReadCandidates(container, label, composer);
    return {
      ok: true,
      operation: "read_private_comments",
      count: candidates.length,
      comments: candidates.map((row) => ({
        text: row.text,
        markers: row.markers,
        structuredFeedback: row.markers.length >= 2,
      })),
      method: "dom-v0.7.16-read",
      url: location.href,
    };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg) return;
    const task = msg.type === "SIEROOM_POST_PRIVATE_COMMENT"
      ? postPrivateComment(msg.comment)
      : msg.type === "SIEROOM_READ_PRIVATE_COMMENTS"
        ? readPrivateComments()
        : null;
    if (!task) return;
    task
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, error: String(err?.message || err), url: location.href }));
    return true;
  });
})();
