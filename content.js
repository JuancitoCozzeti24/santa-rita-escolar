(() => {
  if (window.__SIEROOM_CLASSROOM_BRIDGE_087__) return;
  window.__SIEROOM_CLASSROOM_BRIDGE_087__ = true;

  const inflightSubmissionRequests = new Map();
  const completedSubmissionRequests = new Map();

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

  const isHelpFeedbackControlText = (text) => {
    const t = norm(text);
    return [
      "ayuda y comentarios", "ayuda y sugerencias", "help and feedback",
      "help & feedback", "send feedback", "enviar comentarios"
    ].some((value) => t.includes(norm(value)));
  };

  const isExplicitCommentSendText = (text) => {
    const t = norm(text);
    if (!t || isHelpFeedbackControlText(t)) return false;
    return ["enviar", "publicar", "send", "post"].some((value) => t.includes(norm(value)));
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

  function hasBoundedPrivateComposerAction(container, composer) {
    if (!container || !composer || container === document.body || container === document.documentElement) {
      return false;
    }
    const cr = composer.getBoundingClientRect();
    return [...container.querySelectorAll('button,[role="button"]')].some((button) => {
      if (!visible(button)) return false;
      const m = meta(button);
      if (!isExplicitCommentSendText(m)) return false;
      const br = button.getBoundingClientRect();
      const verticalDistance = Math.abs((br.top + br.height / 2) - (cr.top + cr.height / 2));
      const horizontalDistance = Math.abs((br.left + br.width / 2) - (cr.left + cr.width / 2));
      return verticalDistance <= 240 && horizontalDistance <= 560;
    });
  }

  function shouldAcceptUnlabelledPrivateRegion({
    isDocumentRoot,
    explicitPrivateComposer,
    hasExistingPrivateThread,
    hasBoundedPrivateAction,
  }) {
    return !isDocumentRoot && explicitPrivateComposer &&
      (hasExistingPrivateThread || hasBoundedPrivateAction);
  }

  function bestPrivateRegion(label, composer) {
    if (!composer || !visible(composer) || !isEditable(composer)) return null;
    const composerAncestors = new Set(ancestorChain(composer, 16));
    if (label) {
      for (const el of ancestorChain(label, 16)) {
        if (composerAncestors.has(el) && el !== document.body && el !== document.documentElement) {
          return { container: el, evidence: "private_label_and_composer" };
        }
      }
      return null;
    }

    // Classroom oculta a veces el encabezado "Comentarios privados" cuando el
    // hilo todavía está vacío. Aceptamos ese estado únicamente si el editor se
    // identifica EXPLÍCITAMENTE como privado y comparte un ancestro acotado con
    // su control Enviar/Publicar. Nunca se usa document.body: esa ruta mezclaba
    // alumnos de la misma aula.
    const composerMeta = meta(composer);
    const explicitPrivateComposer = composerMeta.includes("comentario privado") ||
      composerMeta.includes("private comment");
    if (!explicitPrivateComposer) return null;
    for (const el of ancestorChain(composer, 14)) {
      if (el === composer || el === document.body || el === document.documentElement) continue;
      const text = cleanCommentText(el.innerText || el.textContent || "");
      const semanticCount = el.querySelectorAll('[data-comment-id],[role="article"],[role="listitem"]').length;
      const hasExistingPrivateThread = semanticCount > 0 || privateCommentMarkers(text).length >= 2;
      const hasEmptyPrivateComposer = hasBoundedPrivateComposerAction(el, composer);
      if (shouldAcceptUnlabelledPrivateRegion({
        isDocumentRoot: el === document.body || el === document.documentElement,
        explicitPrivateComposer,
        hasExistingPrivateThread,
        hasBoundedPrivateAction: hasEmptyPrivateComposer,
      })) {
        return { container: el, evidence: "bounded_private_composer" };
      }
    }
    return null;
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

    const seen = new Set();
    const scored = [];
    for (const root of roots) {
      for (const b of root.querySelectorAll('button,[role="button"]')) {
        if (seen.has(b) || !visible(b)) continue;
        seen.add(b);
        if (b.disabled || b.getAttribute("aria-disabled") === "true") continue;
        const m = meta(b);
        if (!isExplicitCommentSendText(m)) continue;
        let score = 0;
        if (m.includes("comentario privado") || m.includes("private comment")) score += 80;
        if (m.includes("coment") || m.includes("comment")) score += 25;
        if (m.includes("enviar") || m.includes("send")) score += 60;
        if (m.includes("publicar") || m.includes("post")) score += 60;
        if (score > 0) scored.push({ b, score });
      }
    }
    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.b || null;
  }

  function commentVisibleOutsideComposer(text, composer, container) {
    const wanted = norm(text);
    if (!wanted || !container || container === document.body || container === document.documentElement) {
      return false;
    }
    const nodes = [container, ...container.querySelectorAll("*")];
    return nodes.some((el) => {
      if (!visible(el) || el === composer || composer?.contains?.(el) || el.contains?.(composer)) return false;
      const t = norm(el.textContent);
      return t.length >= wanted.length && t.length < wanted.length + 400 && t.includes(wanted);
    });
  }

  function composerText(composer) {
    if (!composer) return "";
    if (composer instanceof HTMLTextAreaElement || composer instanceof HTMLInputElement) {
      return String(composer.value || "");
    }
    return String(composer.innerText || composer.textContent || "");
  }

  function commentFingerprints(text) {
    const wanted = norm(text);
    if (!wanted) return [];
    const first = wanted.slice(0, Math.min(100, wanted.length));
    const reinforceAt = wanted.indexOf("lo que debes reforzar");
    const middle = reinforceAt >= 0 ? wanted.slice(reinforceAt, reinforceAt + 90) : "";
    const last = wanted.slice(Math.max(0, wanted.length - 90));
    return [...new Set([first, middle, last].filter((value) => value.length >= 45))];
  }

  function commentTextMatches(candidate, wanted) {
    const actual = norm(candidate);
    const expected = norm(wanted);
    if (!actual || !expected) return false;
    if (actual.includes(expected)) return true;
    const fingerprints = commentFingerprints(expected);
    const matches = fingerprints.filter((value) => actual.includes(value)).length;
    return matches >= Math.min(2, fingerprints.length);
  }

  function composerHasFullText(composer, wanted) {
    const actual = norm(composerText(composer));
    const expected = norm(wanted);
    return Boolean(actual && expected && actual.includes(expected));
  }

  function privateSectionNow() {
    const direct = directPrivateComposer();
    if (direct) {
      const label = privateCommentLabel();
      const scoped = bestPrivateRegion(label, direct);
      if (scoped) return { label, composer: direct, ...scoped };
    }
    const label = privateCommentLabel();
    if (!label) return null;
    const composer = composerCandidates(label).find((item) => isEditable(item.el))?.el || null;
    if (!composer) return null;
    const scoped = bestPrivateRegion(label, composer);
    return scoped ? { label, composer, ...scoped } : null;
  }

  function postedCommentVisible(text, section) {
    if (!section?.container) return false;
    if (commentVisibleOutsideComposer(text, section.composer, section.container)) return true;
    const candidates = commentReadCandidates(
      section.container, section.label, section.composer, false
    );
    return candidates.some((row) => commentTextMatches(row.text, text));
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
        const scoped = bestPrivateRegion(label, direct);
        if (scoped) return { label, composer: direct, ...scoped };
      }

      const label = privateCommentLabel();
      if (label) lastLabel = label;
      if (label) {
        const composer = await findOrActivateComposer(label);
        if (composer) {
          const scoped = bestPrivateRegion(label, composer);
          if (scoped) return { label, composer, ...scoped };
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
    if (beforeText.includes(norm(text)) ||
        postedCommentVisible(text, { label, composer, container })) {
      return { ok: true, alreadyPresent: true, method: "dom-v0.8.7", url: location.href };
    }

    composer.scrollIntoView({ block: "nearest", inline: "nearest" });
    setComposerValue(composer, text);
    const fillStarted = Date.now();
    while (Date.now() - fillStarted < 3500 && !composerHasFullText(composer, text)) {
      await sleep(250);
    }
    if (!composerHasFullText(composer, text)) {
      throw new Error("Encontré el editor privado, pero Classroom no confirmó que el texto quedara cargado; no se pulsó Publicar.");
    }
    await sleep(700);

    const send = findSendButton(container, composer);
    if (!send) {
      throw new Error(`Encontré el editor de comentario privado, pero no pude identificar de forma segura el botón Enviar/Publicar. Diagnóstico: ${diagnostics(label)}`);
    }

    const sendMeta = meta(send);
    send.click();
    const started = Date.now();
    while (Date.now() - started < 22000) {
      await sleep(500);
      const currentSection = privateSectionNow();
      if (postedCommentVisible(text, currentSection) ||
          (container?.isConnected && postedCommentVisible(text, { label, composer, container }))) {
        return { ok: true, alreadyPresent: false, method: "dom-v0.8.7", url: location.href };
      }
    }
    throw new Error(
      `Se pulsó Enviar/Publicar, pero no pude confirmar visualmente que el comentario apareciera. ` +
      `Control usado: ${sendMeta || "sin etiqueta"}.`
    );
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

  const SIEROOM_CONTENT_BUILD = "0.8.7-HF4-GRADE-TARGET-DEDUP-SINGLE-PASS-R6";

  function gradeTargetLog(event, detail = {}) {
    try { console.info(`[SieRoom HF4] ${event}`, detail); } catch (_) {}
  }

  function studentIdFromClassroomUrl(value) {
    try {
      const u = new URL(String(value || ""), location.origin);
      const match = u.pathname.match(/\/student\/([^/?#]+)/);
      return match ? decodeURIComponent(match[1]) : "";
    } catch (_) {
      return "";
    }
  }

  function assertSubmissionStudentTarget(targetStudentId, expectedSubmissionUrl = "") {
    const expectedFromUrl = studentIdFromClassroomUrl(expectedSubmissionUrl);
    const target = String(targetStudentId || expectedFromUrl || "").trim();
    const current = studentIdFromClassroomUrl(location.href);

    gradeTargetLog("target_student_id", { target_student_id: target });
    gradeTargetLog("current_student_id", { current_student_id: current });

    if (!target) {
      throw new Error("PAUSA DE SEGURIDAD HF4: no recibí target_student_id para calificar.");
    }
    if (expectedFromUrl && expectedFromUrl !== target) {
      throw new Error(
        `PAUSA DE SEGURIDAD HF4: target_student_id (${target}) no coincide con submission_url (${expectedFromUrl}).`
      );
    }
    if (!current || current !== target) {
      throw new Error(
        `PAUSA DE SEGURIDAD HF4: la URL activa pertenece a otro alumno. Esperado: ${target}. Actual: ${current || "desconocido"}.`
      );
    }
    return { targetStudentId: target, currentStudentId: current };
  }

  function localAncestorText(el, root, levels = 5) {
    const parts = [];
    let cur = el;
    for (let i = 0; cur && i < levels; i++, cur = cur.parentElement) {
      const t = String(cur.innerText || cur.textContent || "");
      if (t && t.length < 1200) parts.push(t);
      if (cur === root) break;
    }
    return norm(parts.join(" "));
  }

  function gradeCandidateScore(el, root) {
    if (!visible(el) || !isEditable(el)) return -9999;
    const m = meta(el);
    const ctx = localAncestorText(el, root, 5);
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

    const value = String(el.value ?? el.textContent ?? "").trim();
    if (value.length <= 16) score += 10;
    if (norm(value).includes("sin calificar") || norm(value).includes("ungraded")) score += 20;

    return score;
  }

  function studentIdsInside(root) {
    const ids = new Set();
    const links = [];
    if (root?.matches?.('a[href*="/student/"]')) links.push(root);
    for (const a of root?.querySelectorAll?.('a[href*="/student/"]') || []) links.push(a);
    for (const a of links) {
      const id = studentIdFromClassroomUrl(a.href || a.getAttribute?.("href"));
      if (id) ids.add(id);
    }
    return [...ids];
  }

  function gradeFieldSummary(el, score = null) {
    return {
      tag: el?.tagName || "",
      type: el?.getAttribute?.("type") || "",
      role: el?.getAttribute?.("role") || "",
      aria: (el?.getAttribute?.("aria-label") || "").slice(0, 120),
      placeholder: (el?.getAttribute?.("placeholder") || "").slice(0, 120),
      value: String(el?.value ?? el?.innerText ?? el?.textContent ?? "").trim().slice(0, 60),
      score
    };
  }

  function targetStudentContainers(targetStudentId) {
    const selector = 'input,textarea,[role="textbox"],[contenteditable="true"]';
    const targetLinks = [...document.querySelectorAll('a[href*="/student/"]')]
      .filter((a) => studentIdFromClassroomUrl(a.href || a.getAttribute("href")) === targetStudentId);

    const seen = new Set();
    const containers = [];

    for (const link of targetLinks) {
      let node = link;
      for (let level = 0; node && level < 10; level++, node = node.parentElement) {
        if (!node || node === document.body || node === document.documentElement || seen.has(node)) continue;
        seen.add(node);
        if (!visible(node)) continue;

        const ids = studentIdsInside(node);
        if (!ids.includes(targetStudentId) || ids.some((id) => id !== targetStudentId)) continue;

        const fields = [...node.querySelectorAll(selector)]
          .filter((el) => visible(el) && isEditable(el))
          .map((el) => ({ el, score: gradeCandidateScore(el, node) }))
          .filter((item) => item.score > 0)
          .sort((a, b) => b.score - a.score);

        if (!fields.length || fields.length > 3) continue;

        const selectedEvidence = [
          link.getAttribute?.("aria-current"),
          link.getAttribute?.("aria-selected"),
          node.getAttribute?.("aria-current"),
          node.getAttribute?.("aria-selected")
        ].some((v) => String(v || "").toLowerCase() === "true" || String(v || "").toLowerCase() === "page");

        const textLength = String(node.innerText || node.textContent || "").length;
        let containerScore = 500 - (level * 20);
        if (fields.length === 1) containerScore += 180;
        if (selectedEvidence) containerScore += 80;
        if (textLength < 800) containerScore += 30;

        containers.push({ node, link, fields, level, containerScore, selectedEvidence, textLength });
      }
    }

    return containers.sort((a, b) => b.containerScore - a.containerScore);
  }


  function nearestStudentIdsForGradeField(el, maxLevels = 7) {
    let cur = el;
    for (let level = 0; cur && level < maxLevels; level++, cur = cur.parentElement) {
      if (cur === document.body || cur === document.documentElement) break;
      const ids = studentIdsInside(cur);
      if (ids.length) return ids;
    }
    return [];
  }

  function explicitGradeMetaScore(el) {
    const m = meta(el);
    const aria = norm(el?.getAttribute?.("aria-label"));
    const placeholder = norm(el?.getAttribute?.("placeholder"));
    let score = 0;

    const strongest = [
      "modificar nota", "editar nota", "cambiar nota",
      "edit grade", "modify grade", "change grade"
    ];
    if (strongest.some((x) => m.includes(x))) score += 320;

    if (aria.includes("calificacion") || aria.includes("nota") || aria.includes("grade")) score += 220;
    if (placeholder.includes("calificacion") || placeholder.includes("nota") || placeholder.includes("grade")) score += 180;

    return score;
  }

  function targetRowGradeCandidates(targetStudentId) {
    const selector = 'input,textarea,[role="textbox"],[contenteditable="true"]';
    const targetLinks = [...document.querySelectorAll('a[href*="/student/"]')]
      .filter((a) => studentIdFromClassroomUrl(a.href || a.getAttribute("href")) === targetStudentId)
      .filter((a) => visible(a));

    if (targetLinks.length !== 1) return [];

    const link = targetLinks[0];
    const lr = link.getBoundingClientRect();
    const linkCenterY = lr.top + lr.height / 2;

    return [...document.querySelectorAll(selector)]
      .filter((el) => visible(el) && isEditable(el))
      .map((el) => {
        const baseScore = gradeCandidateScore(el, document.body);
        if (baseScore <= 0) return null;

        const ids = nearestStudentIdsForGradeField(el);
        if (ids.some((id) => id !== targetStudentId)) return null;

        const er = el.getBoundingClientRect();
        const fieldCenterY = er.top + er.height / 2;
        const yDistance = Math.abs(fieldCenterY - linkCenterY);
        const maxRowDistance = Math.max(58, lr.height * 1.8);
        if (yDistance > maxRowDistance) return null;

        const xPlausible = er.right >= lr.left - 80;
        if (!xPlausible) return null;

        const explicitScore = explicitGradeMetaScore(el);
        const score = 700 + baseScore + explicitScore - (yDistance * 5);
        return {
          el,
          score,
          yDistance: Math.round(yDistance),
          scopeIds: ids,
          strategy: "target_row_geometry"
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score);
  }

  function activeDetailGradeCandidates(targetStudentId) {
    const selector = 'input,textarea,[role="textbox"],[contenteditable="true"]';

    return [...document.querySelectorAll(selector)]
      .filter((el) => visible(el) && isEditable(el))
      .map((el) => {
        const explicitScore = explicitGradeMetaScore(el);
        if (explicitScore < 180) return null;

        const baseScore = gradeCandidateScore(el, document.body);
        if (baseScore <= 0) return null;

        const ids = nearestStudentIdsForGradeField(el);
        if (ids.some((id) => id !== targetStudentId)) return null;

        // Preferimos controles del panel de detalle que no estén ligados a la fila
        // de otro alumno. La URL exacta ya fue validada antes de llegar aquí.
        const scopeBonus = ids.length === 0 ? 140 : 60;
        return {
          el,
          score: explicitScore + baseScore + scopeBonus,
          scopeIds: ids,
          strategy: "active_detail_explicit_grade"
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score);
  }

  function resolveTargetGradeField(targetStudentId) {
    const containers = targetStudentContainers(targetStudentId);
    const ancestorDiagnostics = containers.slice(0, 6).map((c) => ({
      strategy: "ancestor_scope",
      container_score: c.containerScore,
      level: c.level,
      selected: c.selectedEvidence,
      field_count: c.fields.length,
      fields: c.fields.map((f) => gradeFieldSummary(f.el, f.score))
    }));

    const rowCandidates = targetRowGradeCandidates(targetStudentId);
    const detailCandidates = activeDetailGradeCandidates(targetStudentId);
    const diagnostics = [
      ...ancestorDiagnostics,
      {
        strategy: "target_row_geometry",
        candidate_count: rowCandidates.length,
        fields: rowCandidates.slice(0, 6).map((f) => ({
          ...gradeFieldSummary(f.el, f.score),
          y_distance: f.yDistance,
          scope_student_ids: f.scopeIds
        }))
      },
      {
        strategy: "active_detail_explicit_grade",
        candidate_count: detailCandidates.length,
        fields: detailCandidates.slice(0, 6).map((f) => ({
          ...gradeFieldSummary(f.el, f.score),
          scope_student_ids: f.scopeIds
        }))
      }
    ];

    gradeTargetLog("grade_field_candidates", {
      target_student_id: targetStudentId,
      grade_field_candidates: diagnostics
    });

    let matched = null;
    let strategy = "";

    if (containers.length) {
      const best = containers[0];
      const fields = best.fields;
      if (fields.length > 1) {
        const gap = fields[0].score - fields[1].score;
        if (gap < 25) {
          throw new Error(
            `PAUSA DE SEGURIDAD HF4: encontré varias cajas de nota ambiguas dentro del contenedor de ${targetStudentId}.`
          );
        }
      }
      matched = fields[0];
      strategy = "ancestor_scope";
    } else if (rowCandidates.length) {
      if (rowCandidates.length > 1) {
        const gap = rowCandidates[0].score - rowCandidates[1].score;
        if (gap < 45) {
          throw new Error(
            `PAUSA DE SEGURIDAD HF4: hay varias cajas alineadas con la fila del alumno objetivo; no se eligió ninguna.`
          );
        }
      }
      matched = rowCandidates[0];
      strategy = "target_row_geometry";
    } else if (detailCandidates.length === 1) {
      matched = detailCandidates[0];
      strategy = "active_detail_explicit_grade";
    } else if (detailCandidates.length > 1) {
      throw new Error(
        `PAUSA DE SEGURIDAD HF4: el panel activo contiene varias cajas explícitas de nota; no se eligió ninguna.`
      );
    } else {
      return null;
    }

    const summary = {
      ...gradeFieldSummary(matched.el, matched.score),
      strategy,
      scope_student_ids: matched.scopeIds || []
    };
    gradeTargetLog("matched_grade_field", {
      target_student_id: targetStudentId,
      matched_grade_field: summary
    });
    return { el: matched.el, summary, diagnostics };
  }

  function gradeDiagnostics(targetStudentId) {
    const linkCount = [...document.querySelectorAll('a[href*="/student/"]')]
      .filter((a) => studentIdFromClassroomUrl(a.href || a.getAttribute("href")) === targetStudentId).length;
    return JSON.stringify({
      target_student_id: targetStudentId,
      current_student_id: studentIdFromClassroomUrl(location.href),
      exact_target_links: linkCount,
      url: location.href
    });
  }

  async function waitForTargetGradeField(targetStudentId, expectedSubmissionUrl, timeoutMs = 25000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      assertSubmissionStudentTarget(targetStudentId, expectedSubmissionUrl);
      const match = resolveTargetGradeField(targetStudentId);
      if (match?.el) return match;
      await sleep(400);
    }
    throw new Error(
      `No encontré una caja de calificación acotada al alumno objetivo. Diagnóstico: ${gradeDiagnostics(targetStudentId)}`
    );
  }

  async function applyGradeInBrowser(grade, targetStudentId, expectedSubmissionUrl) {
    if (grade === null || grade === undefined || grade === "") {
      return { applied: false, skipped: true };
    }
    const numeric = Number(grade);
    if (!Number.isFinite(numeric)) throw new Error(`Calificación inválida: ${grade}`);

    const beforeGuard = assertSubmissionStudentTarget(targetStudentId, expectedSubmissionUrl);
    const match = await waitForTargetGradeField(beforeGuard.targetStudentId, expectedSubmissionUrl);
    const el = match.el;

    assertSubmissionStudentTarget(beforeGuard.targetStudentId, expectedSubmissionUrl);
    const before = String(el.value ?? el.innerText ?? el.textContent ?? "").trim();
    gradeTargetLog("grade_before", {
      target_student_id: beforeGuard.targetStudentId,
      grade_before: before
    });

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

    try { el.blur(); } catch (_) {}
    await sleep(1100);

    const afterGuard = assertSubmissionStudentTarget(beforeGuard.targetStudentId, expectedSubmissionUrl);
    const persistedMatch = resolveTargetGradeField(beforeGuard.targetStudentId);
    if (!persistedMatch?.el) {
      throw new Error("Classroom dejó de mostrar la caja de nota del alumno objetivo después de escribir.");
    }

    const current = String(
      persistedMatch.el.value ?? persistedMatch.el.innerText ?? persistedMatch.el.textContent ?? ""
    ).trim();
    gradeTargetLog("grade_after", {
      target_student_id: beforeGuard.targetStudentId,
      current_student_id: afterGuard.currentStudentId,
      grade_after: current
    });

    const normalizedCurrent = current.replace(",", ".");
    const numericMatch = normalizedCurrent.match(/-?\d+(?:\.\d+)?/);
    const persistedNumber = numericMatch ? Number(numericMatch[0]) : NaN;
    if (!Number.isFinite(persistedNumber) || Math.abs(persistedNumber - numeric) > 1e-9) {
      throw new Error(
        `Classroom no confirmó que la calificación ${value} quedara persistida en el alumno objetivo. ` +
        `Valor visible: ${current || "vacío"}.`
      );
    }

    const result = {
      applied: true,
      grade: numeric,
      target_student_id: beforeGuard.targetStudentId,
      current_student_id: afterGuard.currentStudentId,
      grade_field_candidates: match.diagnostics,
      matched_grade_field: match.summary,
      grade_before: before,
      grade_after: current,
      browser_grade_applied: true
    };
    gradeTargetLog("browser_grade_applied", result);
    return result;
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


  async function prepareTeacherCommentGuard() {
    const cleanup = window.__SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES__;
    const audit = window.__SIEROOM_AUDIT_TEACHER_PRIVATE_COMMENTS__;
    if (typeof cleanup !== "function" || typeof audit !== "function") {
      throw new Error(
        "BLOQUEO ANTI-DUPLICADO: no está disponible el auditor de comentarios propios; no se publicará ningún comentario."
      );
    }

    const cleanupResult = await cleanup();
    if (!cleanupResult?.ok || !Array.isArray(cleanupResult.comments)) {
      throw new Error(
        cleanupResult?.error ||
        "BLOQUEO ANTI-DUPLICADO: no pude auditar y limpiar comentarios privados existentes."
      );
    }

    const teacherComments = cleanupResult.comments.filter((item) => item.teacherOwned);
    return {
      cleanup: cleanupResult,
      teacherComments,
      teacherCommentCount: teacherComments.length,
    };
  }

  async function processSubmissionOnce(requestId, payload = {}) {
    const key = String(requestId || "").trim();
    if (!key) {
      throw new Error("BLOQUEO ANTI-DUPLICADO: falta requestId estable para esta operación.");
    }

    if (completedSubmissionRequests.has(key)) {
      return {
        ...completedSubmissionRequests.get(key),
        idempotentReplay: true,
        requestId: key,
      };
    }

    if (inflightSubmissionRequests.has(key)) {
      const result = await inflightSubmissionRequests.get(key);
      return { ...result, idempotentReplay: true, requestId: key };
    }

    const task = processSubmission(payload)
      .then((result) => {
        const finalResult = { ...result, requestId: key, idempotentReplay: false };
        completedSubmissionRequests.set(key, finalResult);
        while (completedSubmissionRequests.size > 100) {
          const firstKey = completedSubmissionRequests.keys().next().value;
          completedSubmissionRequests.delete(firstKey);
        }
        return finalResult;
      })
      .finally(() => inflightSubmissionRequests.delete(key));

    inflightSubmissionRequests.set(key, task);
    return await task;
  }

  async function processSubmission(payload = {}) {
    const comment = String(payload.comment || "").trim();
    const grade = payload.grade;
    const returnAfterComment = Boolean(payload.returnAfterComment);

    let commentResult = { ok: true, skipped: true, alreadyPresent: false };
    if (comment) {
      const guard = await prepareTeacherCommentGuard();

      // Regla estricta: si ya existe al menos UN comentario perteneciente a la
      // cuenta docente, jamás publicamos otro. Antes de bloquear, el guard limpia
      // únicamente duplicados claros y conserva el comentario más largo.
      if (guard.teacherCommentCount > 0) {
        commentResult = {
          ok: true,
          skipped: true,
          alreadyPresent: true,
          blockedByExistingTeacherComment: true,
          existingTeacherCommentCount: guard.teacherCommentCount,
          duplicateCleanup: {
            duplicateGroups: Number(guard.cleanup?.duplicateGroups || 0),
            deletedCount: Number(guard.cleanup?.deletedCount || 0),
          },
        };
      } else {
        commentResult = await postPrivateComment(comment);
        if (!commentResult?.ok) throw new Error(commentResult?.error || "No se pudo publicar el comentario privado.");
        commentResult.duplicateCleanup = {
          duplicateGroups: Number(guard.cleanup?.duplicateGroups || 0),
          deletedCount: Number(guard.cleanup?.deletedCount || 0),
        };
      }
      await sleep(500);
    }

    const targetGuard = assertSubmissionStudentTarget(payload.targetStudentId, payload.expectedSubmissionUrl);
    const gradeResult = await applyGradeInBrowser(grade, targetGuard.targetStudentId, payload.expectedSubmissionUrl);
    if (gradeResult.applied) await sleep(700);

    let returnResult = { returned: false, skipped: true };
    if (returnAfterComment) {
      assertSubmissionStudentTarget(targetGuard.targetStudentId, payload.expectedSubmissionUrl);
      returnResult = await returnSubmissionInBrowser();
      assertSubmissionStudentTarget(targetGuard.targetStudentId, payload.expectedSubmissionUrl);
    }

    const finalTargetGuard = assertSubmissionStudentTarget(targetGuard.targetStudentId, payload.expectedSubmissionUrl);
    return {
      ok: true,
      method: "dom-v0.8.7",
      url: location.href,
      comment: commentResult,
      grade: gradeResult,
      return: returnResult,
      browser_followup_done: true,
      browser_grade_applied: Boolean(gradeResult.applied),
      browser_grade: gradeResult.applied ? Number(gradeResult.grade) : null,
      browser_returned: Boolean(returnResult.returned),
      target_student_id: finalTargetGuard.targetStudentId,
      current_student_id: finalTargetGuard.currentStudentId,
      grade_field_candidates: gradeResult.grade_field_candidates || [],
      matched_grade_field: gradeResult.matched_grade_field || null,
      grade_before: gradeResult.grade_before ?? null,
      grade_after: gradeResult.grade_after ?? null,
      content_build: SIEROOM_CONTENT_BUILD
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
      "lo que hizo bien", "lo que hiciste bien",
      "lo que debe mejorar", "lo que debes mejorar", "sugerencias",
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
      "instrucciones", "trabajo de los alumnos", "more_vert",
      "more_vert mas opciones", "mas opciones",
    ].includes(t);
  }

  function commentReadCandidates(container, label, composer, structuredOnly = false) {
    const semanticSelector = '[data-comment-id],[role="article"],[role="listitem"],div';
    const rows = [];
    for (const el of container.querySelectorAll(semanticSelector)) {
      if (!visible(el) || el === label || label?.contains?.(el)) continue;
      if (el === composer || composer?.contains?.(el) || el.contains?.(composer)) continue;
      const text = cleanCommentText(el.innerText || el.textContent || "");
      if (text.length < 2 || text.length > 6000 || isPrivateCommentUiText(text)) continue;
      const markers = privateCommentMarkers(text);
      const semantic = el.matches('[data-comment-id],[role="article"],[role="listitem"]');
      if (structuredOnly && markers.length < 2) continue;
      if (!structuredOnly && markers.length < 2 && !semantic) continue;
      const host = el.closest('[data-comment-id],[role="article"],[role="listitem"]') || el;
      const timeEl = host.querySelector?.('time[datetime]');
      rows.push({
        text,
        markers,
        semantic,
        timestamp: timeEl?.getAttribute?.("datetime") || null,
      });
    }

    // Eliminamos envolturas que contienen otro candidato más preciso, pero
    // conservamos el orden real del DOM. Ordenar por longitud destruía la
    // cronología cuando un alumno tenía más de una retroalimentación.
    const minimal = rows.filter((row, index) => {
      const key = norm(row.text);
      return !rows.some((other, otherIndex) => {
        if (otherIndex === index) return false;
        const otherKey = norm(other.text);
        return key.includes(otherKey) && key.length > otherKey.length + 35;
      });
    });
    const chosen = [];
    for (const row of minimal) {
      const key = norm(row.text);
      if (chosen.some((item) => norm(item.text) === key)) continue;
      chosen.push({ ...row, domOrder: chosen.length });
    }
    return chosen;
  }

  async function readPrivateComments() {
    const { label, composer, container, evidence } = await waitForPrivateSection(20000);
    await sleep(500);
    const candidates = commentReadCandidates(container, label, composer, false);
    return {
      ok: true,
      operation: "read_private_comments",
      count: candidates.length,
      comments: candidates.map((row) => ({
        text: row.text,
        markers: row.markers,
        structuredFeedback: row.markers.length >= 2,
        timestamp: row.timestamp,
        domOrder: row.domOrder,
      })),
      private_section_verified: Boolean(label),
      bounded_private_region_verified: true,
      student_scope_verified: true,
      scope_evidence: evidence,
      comment_order: "document_order",
      method: "dom-v0.8.7-read-hf4",
      content_build: SIEROOM_CONTENT_BUILD,
      current_student_id: studentIdFromClassroomUrl(location.href),
      url: location.href,
    };
  }

  function emailsFromValues(values) {
    const found = new Set();
    const rx = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig;
    for (const value of values || []) {
      const text = String(value || "");
      for (const m of text.matchAll(rx)) found.add(String(m[0]).toLowerCase());
    }
    return [...found];
  }

  function extractActiveAccountEmails() {
    // Solo se confía en el control de la cuenta ACTIVA de Google. Abrir el selector
    // y recorrer todas las cuentas producía un falso positivo cuando el correo
    // esperado era apenas una cuenta secundaria del navegador.
    const selectors = [
      '[aria-label^="Cuenta de Google"]', '[aria-label^="Google Account"]',
      '[aria-label*="Cuenta de Google:"]', '[aria-label*="Google Account:"]',
      '[title^="Cuenta de Google"]', '[title^="Google Account"]'
    ].join(",");
    const controls = [...document.querySelectorAll(selectors)].filter((el) => {
      if (!visible(el)) return false;
      const rect = el.getBoundingClientRect();
      return rect.top < 160 && rect.left > Math.max(0, window.innerWidth * 0.45);
    });
    const values = [];
    for (const el of controls) {
      values.push(el.getAttribute("aria-label"), el.getAttribute("title"), el.getAttribute("data-email"));
    }
    return emailsFromValues(values);
  }

  async function checkExpectedAccount(expectedEmail) {
    const expected = String(expectedEmail || "").trim().toLowerCase();
    const detectedEmails = extractActiveAccountEmails();
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
      sendResponse({
        ok: true,
        version: "0.8.7",
        build: SIEROOM_CONTENT_BUILD,
        duplicateGuard: typeof window.__SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES__ === "function",
        url: location.href
      });
      return;
    }

    if (msg.type === "SIEROOM_CHECK_ACCOUNT") {
      checkExpectedAccount(msg.expectedEmail)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ ok: null, reason: String(err?.message || err), url: location.href }));
      return true;
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
      processSubmissionOnce(msg.requestId, {
        comment: msg.comment,
        grade: msg.grade,
        returnAfterComment: msg.returnAfterComment,
        targetStudentId: msg.targetStudentId,
        expectedSubmissionUrl: msg.expectedSubmissionUrl
      })
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ ok: false, error: String(err?.message || err), url: location.href }));
      return true;
    }
  });
})();
