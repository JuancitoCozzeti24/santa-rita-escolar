(() => {
  if (window.__SIEROOM_PRIVATE_COMPOSER_HF_R67__) return;
  window.__SIEROOM_PRIVATE_COMPOSER_HF_R67__ = true;

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

  const meta = (el) => norm([
    el?.getAttribute?.("aria-label"),
    el?.getAttribute?.("placeholder"),
    el?.getAttribute?.("data-placeholder"),
    el?.getAttribute?.("title"),
    el?.getAttribute?.("data-tooltip"),
    el?.getAttribute?.("aria-description"),
    el?.innerText && el.innerText.length < 240 ? el.innerText : "",
    el?.textContent && el.textContent.length < 240 ? el.textContent : "",
  ].filter(Boolean).join(" "));

  const isSubmissionPage = () =>
    /\/submissions\/by-status\/and-sort-last-name\/student\//.test(location.pathname);

  const nativeDocumentQSA = Document.prototype.querySelectorAll;
  const nativeElementQSA = Element.prototype.querySelectorAll;
  const nativeFragmentQSA = DocumentFragment.prototype.querySelectorAll;

  function nativeQueryAll(scope, selector) {
    try {
      if (scope instanceof Document) return [...nativeDocumentQSA.call(scope, selector)];
      if (scope instanceof DocumentFragment) return [...nativeFragmentQSA.call(scope, selector)];
      if (scope instanceof Element) return [...nativeElementQSA.call(scope, selector)];
    } catch (_) {}
    return [];
  }

  function deepQueryAll(selector, root = document) {
    const out = [];
    const seenElements = new Set();
    const seenScopes = new Set();
    const add = (el) => {
      if (el && !seenElements.has(el)) {
        seenElements.add(el);
        out.push(el);
      }
    };
    const walk = (scope) => {
      if (!scope || seenScopes.has(scope)) return;
      seenScopes.add(scope);
      nativeQueryAll(scope, selector).forEach(add);
      for (const el of nativeQueryAll(scope, "*")) {
        if (el.shadowRoot) walk(el.shadowRoot);
        if (el instanceof HTMLIFrameElement || el instanceof HTMLFrameElement) {
          try {
            if (el.contentDocument) walk(el.contentDocument);
          } catch (_) {}
        }
      }
    };
    walk(root);
    return out;
  }

  try {
    Object.defineProperty(document, "querySelectorAll", {
      configurable: true,
      value(selector) { return deepQueryAll(selector, document); }
    });
    Object.defineProperty(document, "querySelector", {
      configurable: true,
      value(selector) { return deepQueryAll(selector, document)[0] || null; }
    });
    document.documentElement.setAttribute("data-sieroom-deep-dom", "r6.7");
  } catch (_) {}

  const parentLike = (el) => {
    if (!el) return null;
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode?.();
    if (root && root.host instanceof Element) return root.host;
    try {
      const frame = el.ownerDocument?.defaultView?.frameElement;
      if (frame instanceof Element) return frame;
    } catch (_) {}
    return null;
  };

  const ancestors = (el, max = 18) => {
    const out = [];
    let cur = parentLike(el);
    for (let i = 0; cur && i < max; i++, cur = parentLike(cur)) {
      if (cur === document.body || cur === document.documentElement) break;
      out.push(cur);
    }
    return out;
  };

  const isHelpControl = (el) => {
    const m = meta(el);
    return [
      "ayuda y comentarios", "ayuda y sugerencias",
      "help and feedback", "help & feedback",
      "send feedback", "enviar comentarios"
    ].some((x) => m.includes(norm(x)));
  };

  const isGradeOrSearch = (el) => {
    const m = meta(el);
    const type = norm(el?.getAttribute?.("type"));
    if (type === "number" || type === "search") return true;
    return [
      "buscar", "search", "calificacion", "calificación", "grade",
      "puntos", "points", "rubrica", "rúbrica", "criterion", "criterio",
      "nota /", "grade /"
    ].some((x) => m.includes(norm(x)));
  };

  const isEditable = (el) => {
    if (!el || !(el instanceof Element) || !visible(el)) return false;
    if (el instanceof HTMLTextAreaElement) return !el.disabled && !el.readOnly;
    if (el instanceof HTMLInputElement) {
      const type = norm(el.type || "text");
      return !el.disabled && !el.readOnly && ["text", "", "tel"].includes(type);
    }
    return el.getAttribute("contenteditable") === "true" || el.getAttribute("role") === "textbox";
  };

  const isLikelyCommentEditable = (el) => {
    if (!isEditable(el) || isHelpControl(el) || isGradeOrSearch(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 120 || r.height < 18) return false;
    return true;
  };

  const isPrivateText = (text) => {
    const t = norm(text);
    return t.includes("comentarios privados") ||
      t.includes("comentario privado") ||
      t.includes("private comments") ||
      t.includes("private comment");
  };

  const isPostedPrivateAnchor = (el) => {
    const m = meta(el);
    return m.includes("comentario publicado por") ||
      m.includes("comment posted by") ||
      m.includes("comentario privado publicado") ||
      m.includes("private comment posted");
  };

  const isLauncher = (el) => {
    if (!el || !visible(el) || isEditable(el) || isHelpControl(el)) return false;
    const m = meta(el);
    return [
      "anadir comentario", "añadir comentario", "anade un comentario",
      "añade un comentario", "anadir un comentario", "añadir un comentario",
      "agregar comentario", "agrega un comentario",
      "escribir comentario", "escribe un comentario",
      "add comment", "add a comment", "write a comment"
    ].some((x) => m.includes(norm(x)));
  };

  const near = (a, b, maxY = 420, maxX = 900) => {
    if (!a || !b) return false;
    const ar = a.getBoundingClientRect();
    const br = b.getBoundingClientRect();
    const ay = ar.top + ar.height / 2;
    const by = br.top + br.height / 2;
    const ax = ar.left + ar.width / 2;
    const bx = br.left + br.width / 2;
    return Math.abs(ay - by) <= maxY && Math.abs(ax - bx) <= maxX;
  };

  const isSendControl = (el) => {
    if (!visible(el) || isHelpControl(el)) return false;
    const m = meta(el);
    return [
      "enviar", "publicar", "send", "post",
      "publicar comentario", "send comment", "post comment"
    ].some((x) => m.includes(norm(x)));
  };

  const explicitSendNear = (el) => {
    const er = el.getBoundingClientRect();
    return deepQueryAll('button,[role="button"]').filter(visible).some((b) => {
      if (!isSendControl(b)) return false;
      const br = b.getBoundingClientRect();
      const dy = Math.abs((br.top + br.height / 2) - (er.top + er.height / 2));
      const dx = Math.abs((br.left + br.width / 2) - (er.left + er.width / 2));
      return dy <= 240 && dx <= 560;
    });
  };

  function markPrivateComposer(el, evidence = "r6.7") {
    if (!isLikelyCommentEditable(el)) return false;
    const m = meta(el);
    if (!m.includes("coment") && !m.includes("comment")) {
      el.setAttribute("data-placeholder", "Comentario privado");
    }
    el.setAttribute("data-sieroom-private-composer", evidence);
    return true;
  }

  function markPrivateLauncher(el, evidence = "r6.7-launcher") {
    if (!isLauncher(el)) return false;
    const m = meta(el);
    if (!m.includes("privad") && !m.includes("private")) {
      el.setAttribute("data-placeholder", "Añade un comentario privado");
    }
    el.setAttribute("data-sieroom-private-launcher", evidence);
    return true;
  }

  function repairAround(anchor) {
    if (!anchor || !visible(anchor)) return false;
    for (const root of ancestors(anchor, 18)) {
      const editables = deepQueryAll('textarea,input,[role="textbox"],[contenteditable="true"]', root)
        .filter((el) => isLikelyCommentEditable(el) && near(el, anchor));
      if (editables.length === 1) return markPrivateComposer(editables[0], "r6.7-anchor");
      if (editables.length > 1) {
        const explicit = editables.filter((el) => isPrivateText(meta(el)));
        if (explicit.length === 1) return markPrivateComposer(explicit[0], "r6.7-anchor-explicit");
        const withSend = editables.filter(explicitSendNear);
        if (withSend.length === 1) return markPrivateComposer(withSend[0], "r6.7-anchor-send");
      }

      const launchers = deepQueryAll('button,[role="button"],[aria-label],[data-placeholder]', root)
        .filter((el) => isLauncher(el) && near(el, anchor));
      if (launchers.length === 1) {
        markPrivateLauncher(launchers[0], "r6.7-anchor-launcher");
        return true;
      }
    }
    return false;
  }

  function findVisiblePrivatePanelControls() {
    return deepQueryAll(
      'button,[role="button"],[role="tab"],[aria-label],[title],[data-tooltip]'
    ).filter((el) => {
      if (!visible(el) || isHelpControl(el) || isEditable(el)) return false;
      const m = meta(el);
      if (!isPrivateText(m)) return false;
      const role = norm(el.getAttribute("role"));
      return el.tagName === "BUTTON" || role === "button" || role === "tab" ||
        Boolean(el.getAttribute("aria-label")) || Boolean(el.getAttribute("title")) ||
        Boolean(el.getAttribute("data-tooltip"));
    });
  }

  function findSafeGenericCommentControls() {
    return deepQueryAll(
      'button,[role="button"],[role="tab"],[aria-label],[title],[data-tooltip]'
    ).filter((el) => {
      if (!visible(el) || isHelpControl(el) || isEditable(el)) return false;
      const m = meta(el);
      if (!(m.includes("coment") || m.includes("comment"))) return false;
      const r = el.getBoundingClientRect();
      if (r.left + r.width / 2 < window.innerWidth * 0.45) return false;
      return true;
    });
  }

  function hasVisiblePrivateComposer() {
    return deepQueryAll('textarea,input,[role="textbox"],[contenteditable="true"]')
      .some((el) => isLikelyCommentEditable(el) && isPrivateText(meta(el)));
  }

  let lastPanelClickAt = 0;
  let lastPanelClickUrl = "";

  async function clickRankedControl(controls, generic = false) {
    if (!controls.length) return false;
    const ranked = controls.map((el) => {
      const m = meta(el);
      let score = 0;
      if (m === "comentarios privados" || m === "private comments") score += 120;
      if (m.includes("comentarios privados") || m.includes("private comments")) score += 100;
      if (m.includes("comentario privado") || m.includes("private comment")) score += 80;
      if (generic && (m.includes("coment") || m.includes("comment"))) score += 35;
      const role = norm(el.getAttribute("role"));
      if (el.tagName === "BUTTON" || role === "button" || role === "tab") score += 25;
      const r = el.getBoundingClientRect();
      if (r.left + r.width / 2 >= window.innerWidth * 0.45) score += 20;
      return { el, score };
    }).sort((a, b) => b.score - a.score);

    const minimum = generic ? 70 : 100;
    if (!ranked[0] || ranked[0].score < minimum) return false;
    if (ranked[1] && ranked[1].score === ranked[0].score && ranked[1].el !== ranked[0].el) return false;

    const now = Date.now();
    if (lastPanelClickUrl === location.href && now - lastPanelClickAt < 3500) return false;
    lastPanelClickAt = now;
    lastPanelClickUrl = location.href;
    try {
      ranked[0].el.scrollIntoView({ block: "nearest", inline: "nearest" });
      ranked[0].el.click();
      document.documentElement.setAttribute(
        "data-sieroom-private-panel-opened",
        generic ? "r6.7-generic" : "r6.7-private"
      );
      await sleep(220);
      return true;
    } catch (_) {
      return false;
    }
  }

  async function tryOpenPrivatePanel() {
    if (!isSubmissionPage() || hasVisiblePrivateComposer()) return false;
    if (await clickRankedControl(findVisiblePrivatePanelControls(), false)) return true;
    const generic = findSafeGenericCommentControls();
    if (generic.length === 1) return clickRankedControl(generic, true);
    return false;
  }

  function repairUnlabelledEmptyThread() {
    if (!isSubmissionPage()) return false;

    const editables = deepQueryAll('textarea,input,[role="textbox"],[contenteditable="true"]')
      .filter(isLikelyCommentEditable);
    if (!editables.length) return false;

    const explicit = editables.filter((el) => isPrivateText(meta(el)));
    if (explicit.length === 1) return markPrivateComposer(explicit[0], "r6.7-explicit");

    const commentish = editables.filter((el) => {
      const m = meta(el);
      return m.includes("coment") || m.includes("comment");
    });
    if (commentish.length === 1) return markPrivateComposer(commentish[0], "r6.7-commentish");

    const withSend = editables.filter(explicitSendNear);
    if (withSend.length === 1) return markPrivateComposer(withSend[0], "r6.7-send-near");

    const rightWide = editables.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.left + r.width / 2 >= window.innerWidth * 0.5 && r.width >= 180;
    });
    if (rightWide.length === 1) return markPrivateComposer(rightWide[0], "r6.7-single-right-wide-editor");

    return false;
  }

  async function repair() {
    if (!isSubmissionPage()) return;
    document.documentElement.setAttribute("data-sieroom-private-hf", "r6.7");

    const anchors = deepQueryAll(
      '[aria-label],[role="heading"],h1,h2,h3,h4,[title],[data-tooltip]'
    ).filter((el) => visible(el) && (isPrivateText(meta(el)) || isPostedPrivateAnchor(el)));

    for (const anchor of anchors) {
      if (repairAround(anchor)) return;
    }

    if (repairUnlabelledEmptyThread()) return;

    const opened = await tryOpenPrivatePanel();
    if (opened) {
      setTimeout(() => repair().catch(() => {}), 250);
      setTimeout(() => repair().catch(() => {}), 800);
      setTimeout(() => repair().catch(() => {}), 1600);
    }
  }

  let scheduled = false;
  const scheduleRepair = () => {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      repair().catch(() => {});
    }, 70);
  };

  repair().catch(() => {});
  setTimeout(() => repair().catch(() => {}), 450);
  setTimeout(() => repair().catch(() => {}), 1200);
  setTimeout(() => repair().catch(() => {}), 2600);
  setTimeout(() => repair().catch(() => {}), 5200);

  const observer = new MutationObserver(scheduleRepair);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: [
      "aria-label", "placeholder", "data-placeholder", "contenteditable",
      "role", "title", "data-tooltip", "aria-expanded", "aria-selected", "type"
    ]
  });
})();