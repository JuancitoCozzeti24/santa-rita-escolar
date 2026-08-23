(() => {
  if (window.__SIEROOM_CLASSROOM_BRIDGE_080__) return;
  window.__SIEROOM_CLASSROOM_BRIDGE_080__ = true;

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
      return !el.disabled && !el.readOnly && ["text", "search", "number", "tel", ""].includes(t);
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

  function directPrivateComposer() {
    // Classroom puede ocultar el encabezado "Comentarios privados" pero mantener
    // el editor con aria-label como "Añade un comentario privado…".
    const selector = 'textarea,input,[role="textbox"],[contenteditable="true"]';
    const candidates = [...document.querySelectorAll(selector)]
      .filter((el) => visible(el) && isEditable(el))
      .map((el) => {
        const m = meta(el);
        let score = 0;
        if (m.includes("comentario privado") || m.includes("private comment")) score += 180;
        if (m.includes("anade un comentario") || m.includes("add a comment")) score += 90;
        if ((m.includes("coment") || m.includes("comment")) && !m.includes("calificacion") && !m.includes("grade")) score += 45;
        return { el, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
    return candidates[0]?.el || null;
  }

  async function waitForPrivateSection(timeoutMs = 35000) {
    const started = Date.now();
    let lastLabel = null;
    while (Date.now() - started < timeoutMs) {
      const direct = directPrivateComposer();
      if (direct) {
        const label = privateCommentLabel();
        const container = bestPrivateRegion(label, direct);
        return { label, composer: direct, container };
      }

      const label = privateCommentLabel();
      if (label) lastLabel = label;
      if (label) {
        const composer = await findOrActivateComposer(label);
        if (composer) {
          const container = bestPrivateRegion(label, composer);
          return { label, composer, container };
        }
      }
      await sleep(400);
    }
    throw new Error(`No encontré el editor de Comentarios privados en esta entrega. Diagnóstico: ${diagnostics(lastLabel)}`);
  }

  async function postPrivateComment(comment) {
    const text = String(comment || "").trim();
    if (!text) throw new Error("Comentario vacío.");

    const { label, composer, container } = await waitForPrivateSection();
    const beforeText = norm(container?.textContent || "");
    if (beforeText.includes(norm(text)) || commentVisibleOutsideComposer(text, composer)) {
      return { ok: true, alreadyPresent: true, method: "dom-v0.8.1", url: location.href };
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
        return { ok: true, alreadyPresent: false, method: "dom-v0.8.1", url: location.href };
      }
    }
    throw new Error("Se pulsó Enviar/Publicar, pero no pude confirmar visualmente que el comentario apareciera.");
  }


  function ancestorText(el, levels = 4) {
    const parts = [];
    let cur = el;
    for (let i = 0; cur && i < levels; i++, cur = cur.parentElement) {
      const t = String(cur.innerText || cur.textContent || "");
      if (t && t.length < 1200) parts.push(t);
    }
    return norm(parts.join(" "));
  }

  function gradeCandidateScore(el) {
    if (!visible(el) || !isEditable(el)) return -9999;
    const m = meta(el);
    const ctx = ancestorText(el, 5);
    if (m.includes("coment") || m.includes("comment") || ctx.includes("comentarios privados")) return -9999;

    let score = 0;
    const gradeWords = ["calificacion", "calificar", "nota", "grade", "puntos", "points"];
    for (const w of gradeWords) {
      if (m.includes(w)) score += 55;
      if (ctx.includes(w)) score += 20;
    }

    const aria = norm(el.getAttribute?.("aria-label"));
    if (aria.includes("calificacion") || aria.includes("grade")) score += 100;
    if (el instanceof HTMLInputElement && norm(el.type) === "number") score += 35;

    // En la vista individual de Classroom el campo suele estar en un panel lateral
    // y su contenido actual es vacío, "Sin calificar" o un valor corto.
    const value = String(el.value ?? el.textContent ?? "").trim();
    if (value.length <= 6) score += 10;

    return score;
  }

  function findGradeInput() {
    const selector = 'input,textarea,[role="textbox"],[contenteditable="true"]';
    const candidates = [...document.querySelectorAll(selector)]
      .map((el) => ({ el, score: gradeCandidateScore(el) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
    return candidates[0]?.el || null;
  }

  function gradeDiagnostics() {
    const selector = 'input,textarea,[role="textbox"],[contenteditable="true"]';
    const cand = [...document.querySelectorAll(selector)]
      .filter((el) => visible(el))
      .map((el) => ({
        tag: el.tagName,
        type: el.getAttribute("type") || "",
        aria: (el.getAttribute("aria-label") || "").slice(0, 100),
        placeholder: (el.getAttribute("placeholder") || "").slice(0, 100),
        value: String(el.value ?? el.textContent ?? "").slice(0, 40),
        score: gradeCandidateScore(el)
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
    return JSON.stringify({ candidates: cand, url: location.href });
  }

  async function waitForGradeInput(timeoutMs = 25000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const input = findGradeInput();
      if (input) return input;
      await sleep(400);
    }
    throw new Error(`No encontré el campo de calificación. Diagnóstico: ${gradeDiagnostics()}`);
  }

  async function applyGradeInBrowser(grade) {
    if (grade === null || grade === undefined || grade === "") {
      return { applied: false, skipped: true };
    }
    const numeric = Number(grade);
    if (!Number.isFinite(numeric)) throw new Error(`Calificación inválida: ${grade}`);

    const el = await waitForGradeInput();
    el.scrollIntoView({ block: "center", inline: "nearest" });
    el.focus();

    const value = String(numeric);
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      setNativeValue(el, value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      setComposerValue(el, value);
    }

    // Classroom a veces persiste la nota al perder foco o al pulsar Enter.
    try {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", bubbles: true }));
    } catch (_) {}
    try { el.blur(); } catch (_) {}
    await sleep(1100);

    const current = String(el.value ?? el.innerText ?? el.textContent ?? "").trim();
    if (current && current !== value && Number(current) !== numeric) {
      throw new Error(`Classroom no conservó la calificación ${value}. Valor visible: ${current}`);
    }

    return { applied: true, grade: numeric, fieldMeta: meta(el).slice(0, 160) };
  }

  function buttonText(el) {
    return norm([
      el?.innerText,
      el?.textContent,
      el?.getAttribute?.("aria-label"),
      el?.getAttribute?.("title")
    ].filter(Boolean).join(" "));
  }

  function isReturnText(t) {
    const s = norm(t);
    return s === "devolver" || s === "return" ||
      s.startsWith("devolver ") || s.startsWith("return ") ||
      s.includes("devolver trabajo") || s.includes("return work");
  }

  function findReturnButton(root = document) {
    const buttons = [...root.querySelectorAll('button,[role="button"]')]
      .filter((b) => visible(b) && !b.disabled && b.getAttribute("aria-disabled") !== "true")
      .map((b) => {
        const t = buttonText(b);
        let score = 0;
        if (t === "devolver" || t === "return") score += 160;
        if (t.startsWith("devolver ") || t.startsWith("return ")) score += 110;
        if (t.includes("devolver trabajo") || t.includes("return work")) score += 80;
        if (t.includes("todos") || t.includes("all students")) score -= 100;
        return { b, t, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
    return buttons[0]?.b || null;
  }

  function pageLooksReturned() {
    const visibleTexts = [...document.querySelectorAll("body *")]
      .filter((el) => visible(el))
      .map((el) => norm(el.innerText || el.textContent || ""))
      .filter((t) => t && t.length < 100);
    return visibleTexts.some((t) =>
      t === "devuelto" || t === "returned" ||
      t.includes("trabajo devuelto") || t.includes("work returned")
    );
  }

  async function waitForReturnButton(timeoutMs = 25000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (pageLooksReturned()) return null;
      const b = findReturnButton(document);
      if (b) return b;
      await sleep(400);
    }
    if (pageLooksReturned()) return null;
    throw new Error("No encontré el botón Devolver en la entrega.");
  }

  async function confirmReturnDialog() {
    const start = Date.now();
    while (Date.now() - start < 10000) {
      const dialogs = [...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')]
        .filter((d) => visible(d));
      for (const dialog of dialogs) {
        const b = findReturnButton(dialog);
        if (b) {
          b.click();
          return true;
        }
      }
      // Algunas versiones no exponen role=dialog; si aparece un segundo botón
      // Devolver visible, usamos el de mayor z-index/último en DOM.
      const all = [...document.querySelectorAll('button,[role="button"]')]
        .filter((b) => visible(b) && isReturnText(buttonText(b)) &&
          !b.disabled && b.getAttribute("aria-disabled") !== "true");
      if (all.length >= 2) {
        all[all.length - 1].click();
        return true;
      }
      await sleep(300);
    }
    return false;
  }

  async function returnSubmissionInBrowser() {
    if (pageLooksReturned()) return { returned: true, alreadyReturned: true };

    const b = await waitForReturnButton();
    if (!b) return { returned: true, alreadyReturned: true };

    b.scrollIntoView({ block: "center", inline: "nearest" });
    b.click();
    await sleep(500);
    await confirmReturnDialog();
    await sleep(1200);

    // Aunque Classroom no siempre muestra inmediatamente la palabra "Devuelto",
    // si el botón desapareció tras confirmar consideramos la acción aceptada.
    const stillThere = findReturnButton(document);
    const returned = pageLooksReturned() || !stillThere;
    if (!returned) {
      throw new Error("Se pulsó Devolver, pero Classroom no confirmó visualmente la devolución.");
    }
    return { returned: true, alreadyReturned: false };
  }

  async function processSubmission(payload = {}) {
    const comment = String(payload.comment || "").trim();
    const grade = payload.grade;
    const returnAfterComment = Boolean(payload.returnAfterComment);

    let commentResult = { ok: true, skipped: true, alreadyPresent: false };
    if (comment) {
      commentResult = await postPrivateComment(comment);
      if (!commentResult?.ok) throw new Error(commentResult?.error || "No se pudo publicar el comentario privado.");
      await sleep(500);
    }

    const gradeResult = await applyGradeInBrowser(grade);
    if (gradeResult.applied) await sleep(700);

    let returnResult = { returned: false, skipped: true };
    if (returnAfterComment) {
      returnResult = await returnSubmissionInBrowser();
    }

    return {
      ok: true,
      method: "dom-v0.8.1",
      url: location.href,
      comment: commentResult,
      grade: gradeResult,
      return: returnResult,
      browser_followup_done: true,
      browser_grade_applied: Boolean(gradeResult.applied),
      browser_grade: gradeResult.applied ? Number(gradeResult.grade) : null,
      browser_returned: Boolean(returnResult.returned)
    };
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
      method: "dom-v0.8.1-read",
      url: location.href,
    };
  }

  function extractEmailsFromPage() {
    const found = new Set();
    const rx = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig;

    function addFrom(value) {
      const text = String(value || "");
      for (const m of text.matchAll(rx)) found.add(String(m[0]).toLowerCase());
    }

    addFrom(document.body?.innerText || "");
    addFrom(document.body?.textContent || "");

    const selector = [
      "[aria-label]", "[title]", "[data-tooltip]", "[data-tooltip-text]",
      "[data-email]", "[href]"
    ].join(",");

    for (const el of document.querySelectorAll(selector)) {
      addFrom(el.getAttribute("aria-label"));
      addFrom(el.getAttribute("title"));
      addFrom(el.getAttribute("data-tooltip"));
      addFrom(el.getAttribute("data-tooltip-text"));
      addFrom(el.getAttribute("data-email"));
      addFrom(el.getAttribute("href"));
    }

    return [...found];
  }

  function checkExpectedAccount(expectedEmail) {
    const expected = String(expectedEmail || "").trim().toLowerCase();
    const detectedEmails = extractEmailsFromPage();
    const body = norm(document.body?.innerText || "");
    const classNotFound =
      body.includes("no se encontro la clase") ||
      body.includes("class not found") ||
      body.includes("couldn't find the class") ||
      body.includes("could not find the class");

    if (!expected) {
      return { ok: null, reason: "missing_expected_email", detectedEmails, classNotFound, url: location.href };
    }

    if (detectedEmails.includes(expected)) {
      return { ok: true, expectedEmail: expected, detectedEmails, classNotFound, url: location.href };
    }

    if (detectedEmails.length) {
      return { ok: false, expectedEmail: expected, detectedEmails, classNotFound, url: location.href };
    }

    return {
      ok: null,
      expectedEmail: expected,
      detectedEmails: [],
      classNotFound,
      reason: "email_not_visible_in_dom",
      url: location.href
    };
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg) return;

    if (msg.type === "SIEROOM_PING") {
      sendResponse({ ok: true, version: "0.8.1", url: location.href });
      return;
    }

    if (msg.type === "SIEROOM_CHECK_ACCOUNT") {
      sendResponse(checkExpectedAccount(msg.expectedEmail));
      return;
    }

    if (msg.type === "SIEROOM_READ_PRIVATE_COMMENTS") {
      readPrivateComments()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ ok: false, error: String(err?.message || err), url: location.href }));
      return true;
    }

    if (msg.type === "SIEROOM_POST_PRIVATE_COMMENT") {
      postPrivateComment(msg.comment)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ ok: false, error: String(err?.message || err), url: location.href }));
      return true;
    }

    if (msg.type === "SIEROOM_PROCESS_SUBMISSION") {
      processSubmission({
        comment: msg.comment,
        grade: msg.grade,
        returnAfterComment: msg.returnAfterComment
      })
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ ok: false, error: String(err?.message || err), url: location.href }));
      return true;
    }
  });
})();
