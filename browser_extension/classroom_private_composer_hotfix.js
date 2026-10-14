(() => {
  if (window.__SIEROOM_PRIVATE_COMPOSER_HF_R64__) return;
  window.__SIEROOM_PRIVATE_COMPOSER_HF_R64__ = true;

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

  const meta = (el) => norm([
    el?.getAttribute?.("aria-label"),
    el?.getAttribute?.("placeholder"),
    el?.getAttribute?.("data-placeholder"),
    el?.getAttribute?.("title"),
    el?.getAttribute?.("aria-description"),
    el?.innerText && el.innerText.length < 160 ? el.innerText : "",
    el?.textContent && el.textContent.length < 160 ? el.textContent : "",
  ].filter(Boolean).join(" "));

  const isSubmissionPage = () => /\/submissions\/by-status\/and-sort-last-name\/student\//.test(location.pathname);

  const isPostedPrivateCommentAnchor = (el) => {
    const m = meta(el);
    return m.includes("comentario publicado por") || m.includes("comment posted by");
  };

  const isPrivateHeading = (el) => {
    const m = meta(el);
    return m.includes("comentarios privados") || m.includes("private comments");
  };

  const isHelpControl = (el) => {
    const m = meta(el);
    return m.includes("ayuda y comentarios") ||
      m.includes("ayuda y sugerencias") ||
      m.includes("help and feedback") ||
      m.includes("help & feedback") ||
      m.includes("send feedback") ||
      m.includes("enviar comentarios");
  };

  const isEditable = (el) => {
    if (!el || !(el instanceof Element) || !visible(el)) return false;
    if (el instanceof HTMLTextAreaElement) return !el.disabled && !el.readOnly;
    if (el instanceof HTMLInputElement) {
      const t = norm(el.type || "text");
      return !el.disabled && !el.readOnly && ["text", "search", ""].includes(t);
    }
    return el.getAttribute("contenteditable") === "true" || el.getAttribute("role") === "textbox";
  };

  const isLikelyCommentEditable = (el) => {
    if (!isEditable(el) || isHelpControl(el)) return false;
    if (el instanceof HTMLInputElement) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 140 || r.height < 24) return false;
    const m = meta(el);
    if (["buscar", "search", "calificacion", "calificación", "grade", "puntos", "points"].some((x) => m.includes(norm(x)))) return false;
    return true;
  };

  const isLauncher = (el) => {
    if (!el || !visible(el) || isEditable(el) || isHelpControl(el)) return false;
    const m = meta(el);
    return [
      "anadir comentario", "anade un comentario", "anadir un comentario",
      "agregar comentario", "agrega un comentario", "escribir comentario",
      "escribe un comentario", "add comment", "add a comment", "write a comment"
    ].some((x) => m.includes(x));
  };

  const near = (a, b, maxY = 360, maxX = 760) => {
    if (!a || !b) return false;
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    const ay = ar.top + ar.height / 2;
    const by = br.top + br.height / 2;
    const ax = ar.left + ar.width / 2;
    const bx = br.left + br.width / 2;
    return Math.abs(ay - by) <= maxY && Math.abs(ax - bx) <= maxX;
  };

  const ancestors = (el, max = 10) => {
    const out = [];
    let cur = el?.parentElement || null;
    for (let i = 0; cur && i < max; i++, cur = cur.parentElement) {
      if (cur === document.body || cur === document.documentElement) break;
      out.push(cur);
    }
    return out;
  };

  const explicitSendNear = (el) => {
    const er = el.getBoundingClientRect();
    const buttons = [...document.querySelectorAll('button,[role="button"]')].filter(visible);
    return buttons.some((b) => {
      if (isHelpControl(b)) return false;
      const m = meta(b);
      if (!["enviar", "publicar", "send", "post"].some((x) => m.includes(x))) return false;
      const br = b.getBoundingClientRect();
      const dy = Math.abs((br.top + br.height / 2) - (er.top + er.height / 2));
      const dx = Math.abs((br.left + br.width / 2) - (er.left + er.width / 2));
      return dy <= 240 && dx <= 560;
    });
  };

  function markPrivateComposer(el, evidence = "r6.4") {
    if (!isLikelyCommentEditable(el)) return;
    const m = meta(el);
    if (!m.includes("coment") && !m.includes("comment")) {
      el.setAttribute("data-placeholder", "Comentario privado");
    }
    el.setAttribute("data-sieroom-private-composer", evidence);
  }

  function markPrivateLauncher(el) {
    if (!isLauncher(el)) return;
    const m = meta(el);
    if (!m.includes("privad") && !m.includes("private")) {
      el.setAttribute("data-placeholder", "Añade un comentario privado");
    }
    el.setAttribute("data-sieroom-private-launcher", "r6.4");
  }

  function repairAround(anchor) {
    if (!anchor || !visible(anchor)) return;
    const roots = ancestors(anchor, 10);
    for (const root of roots) {
      const editables = [...root.querySelectorAll('textarea,input,[role="textbox"],[contenteditable="true"]')]
        .filter((el) => isLikelyCommentEditable(el) && near(el, anchor));
      if (editables.length) {
        editables.forEach((el) => markPrivateComposer(el, "r6.4-anchor"));
        return;
      }

      const launchers = [...root.querySelectorAll('button,[role="button"],[aria-label],[data-placeholder]')]
        .filter((el) => isLauncher(el) && near(el, anchor));
      if (launchers.length) {
        launchers.forEach(markPrivateLauncher);
        return;
      }
    }
  }

  function repairUnlabelledEmptyThread() {
    if (!isSubmissionPage()) return;

    const editables = [...document.querySelectorAll('textarea,[role="textbox"],[contenteditable="true"]')]
      .filter(isLikelyCommentEditable);
    if (!editables.length) return;

    const explicit = editables.filter((el) => {
      const m = meta(el);
      return m.includes("coment") || m.includes("comment") || m.includes("privad") || m.includes("private");
    });
    if (explicit.length === 1) {
      markPrivateComposer(explicit[0], "r6.4-explicit");
      return;
    }

    const withSend = editables.filter(explicitSendNear);
    if (withSend.length === 1) {
      markPrivateComposer(withSend[0], "r6.4-send-near");
      return;
    }

    // Fallback seguro para el hilo vacío de Classroom: en la página individual
    // de una entrega, si existe un único editor multilinea visible y está en la
    // mitad derecha (panel de evaluación), lo tratamos como comentario privado.
    const rightSide = editables.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.left + r.width / 2 >= window.innerWidth * 0.5;
    });
    if (rightSide.length === 1) {
      markPrivateComposer(rightSide[0], "r6.4-single-right-editor");
    }
  }

  function repair() {
    const labelledPrivate = [...document.querySelectorAll('[aria-label],[role="heading"],h1,h2,h3,h4')]
      .filter((el) => visible(el) && isPrivateHeading(el));
    for (const heading of labelledPrivate) repairAround(heading);

    const posted = [...document.querySelectorAll('[aria-label]')]
      .filter((el) => visible(el) && isPostedPrivateCommentAnchor(el));
    for (const anchor of posted) repairAround(anchor);

    if (!labelledPrivate.length && !posted.length) repairUnlabelledEmptyThread();
  }

  let scheduled = false;
  const scheduleRepair = () => {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      repair();
    }, 60);
  };

  repair();
  const observer = new MutationObserver(scheduleRepair);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-label", "placeholder", "data-placeholder", "contenteditable", "role"]
  });
})();