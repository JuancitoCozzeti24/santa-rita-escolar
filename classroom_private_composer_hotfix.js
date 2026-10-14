(() => {
  if (window.__SIEROOM_PRIVATE_COMPOSER_HF_R65__) return;
  window.__SIEROOM_PRIVATE_COMPOSER_HF_R65__ = true;

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
    el?.innerText && el.innerText.length < 220 ? el.innerText : "",
    el?.textContent && el.textContent.length < 220 ? el.textContent : "",
  ].filter(Boolean).join(" "));

  const isSubmissionPage = () =>
    /\/submissions\/by-status\/and-sort-last-name\/student\//.test(location.pathname);

  function deepQueryAll(selector, root = document) {
    const out = [];
    const seen = new Set();

    const walk = (scope) => {
      let matches = [];
      let all = [];
      try { matches = [...scope.querySelectorAll(selector)]; } catch (_) {}
      for (const el of matches) {
        if (!seen.has(el)) {
          seen.add(el);
          out.push(el);
        }
      }
      try { all = [...scope.querySelectorAll("*")]; } catch (_) {}
      for (const el of all) {
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };

    walk(root);
    return out;
  }

  const parentLike = (el) => {
    if (!el) return null;
    if (el.parentElement) return el.parentElement;
    const root = el.getRootNode?.();
    return root && root.host instanceof Element ? root.host : null;
  };

  const ancestors = (el, max = 14) => {
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

  const isEditable = (el) => {
    if (!el || !(el instanceof Element) || !visible(el)) return false;
    if (el instanceof HTMLTextAreaElement) return !el.disabled && !el.readOnly;
    if (el instanceof HTMLInputElement) return false;
    return el.getAttribute("contenteditable") === "true" || el.getAttribute("role") === "textbox";
  };

  const isLikelyCommentEditable = (el) => {
    if (!isEditable(el) || isHelpControl(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 140 || r.height < 22) return false;
    const m = meta(el);
    if ([
      "buscar", "search", "calificacion", "calificación", "grade",
      "puntos", "points", "rubrica", "rúbrica", "criterion", "criterio"
    ].some((x) => m.includes(norm(x)))) return false;
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
    return ["enviar", "publicar", "send", "post"].some((x) => m.includes(norm(x)));
  };

  const explicitSendNear = (el) => {
    const er = el.getBoundingClientRect();
    return deepQueryAll('button,[role="button"]').filter(visible).some((b) => {
      if (!isSendControl(b)) return false;
      const br = b.getBoundingClientRect();
      const dy = Math.abs((br.top + br.height / 2) - (er.top + er.height / 2));
      const dx = Math.abs((br.left + br.width / 2) - (er.left + er.width / 2));
      return dy <= 260 && dx <= 620;
    });
  };

  function markPrivateComposer(el, evidence = "r6.5") {
    if (!isLikelyCommentEditable(el)) return false;
    const m = meta(el);
    if (!m.includes("coment") && !m.includes("comment")) {
      el.setAttribute("data-placeholder", "Comentario privado");
    }
    el.setAttribute("data-sieroom-private-composer", evidence);
    return true;
  }

  function markPrivateLauncher(el, evidence = "r6.5-launcher") {
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
    for (const root of ancestors(anchor, 14)) {
      const editables = deepQueryAll('textarea,[role="textbox"],[contenteditable="true"]', root)
        .filter((el) => isLikelyCommentEditable(el) && near(el, anchor));
      if (editables.length === 1) return markPrivateComposer(editables[0], "r6.5-anchor");
      if (editables.length > 1) {
        const explicit = editables.filter((el) => isPrivateText(meta(el)));
        if (explicit.length === 1) return markPrivateComposer(explicit[0], "r6.5-anchor-explicit");
      }

      const launchers = deepQueryAll('button,[role="button"],[aria-label],[data-placeholder]', root)
        .filter((el) => isLauncher(el) && near(el, anchor));
      if (launchers.length === 1) {
        markPrivateLauncher(launchers[0], "r6.5-anchor-launcher");
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
      return el.tagName === "BUTTON" ||
        role === "button" ||
        role === "tab" ||
        Boolean(el.getAttribute("aria-label")) ||
        Boolean(el.getAttribute("title")) ||
        Boolean(el.getAttribute("data-tooltip"));
    });
  }

  function hasVisiblePrivateComposer() {
    return deepQueryAll('textarea,[role="textbox"],[contenteditable="true"]')
      .some((el) => isLikelyCommentEditable(el) && isPrivateText(meta(el)));
  }

  let lastPanelClickAt = 0;
  let lastPanelClickUrl = "";

  async function tryOpenPrivatePanel() {
    if (!isSubmissionPage() || hasVisiblePrivateComposer()) return false;

    const controls = findVisiblePrivatePanelControls();
    if (!controls.length) return false;

    const ranked = controls.map((el) => {
      const m = meta(el);
      let score = 0;
      if (m === "comentarios privados" || m === "private comments") score += 100;
      if (m.includes("comentarios privados") || m.includes("private comments")) score += 80;
      if (m.includes("comentario privado") || m.includes("private comment")) score += 50;
      const role = norm(el.getAttribute("role"));
      if (el.tagName === "BUTTON" || role === "button" || role === "tab") score += 25;
      const r = el.getBoundingClientRect();
      if (r.left + r.width / 2 >= window.innerWidth * 0.45) score += 15;
      return { el, score };
    }).sort((a, b) => b.score - a.score);

    if (!ranked[0] || ranked[0].score < 90) return false;
    if (ranked[1] && ranked[1].score === ranked[0].score && ranked[1].el !== ranked[0].el) return false;

    const now = Date.now();
    if (lastPanelClickUrl === location.href && now - lastPanelClickAt < 3500) return false;

    lastPanelClickAt = now;
    lastPanelClickUrl = location.href;
    try {
      ranked[0].el.scrollIntoView({ block: "nearest", inline: "nearest" });
      ranked[0].el.click();
      document.documentElement.setAttribute("data-sieroom-private-panel-opened", "r6.5");
      await sleep(180);
      return true;
    } catch (_) {
      return false;
    }
  }

  function repairUnlabelledEmptyThread() {
    if (!isSubmissionPage()) return false;

    const editables = deepQueryAll('textarea,[role="textbox"],[contenteditable="true"]')
      .filter(isLikelyCommentEditable);
    if (!editables.length) return false;

    const explicit = editables.filter((el) => isPrivateText(meta(el)));
    if (explicit.length === 1) return markPrivateComposer(explicit[0], "r6.5-explicit");

    const commentish = editables.filter((el) => {
      const m = meta(el);
      return m.includes("coment") || m.includes("comment");
    });
    if (commentish.length === 1) return markPrivateComposer(commentish[0], "r6.5-commentish");

    const withSend = editables.filter(explicitSendNear);
    if (withSend.length === 1) return markPrivateComposer(withSend[0], "r6.5-send-near");

    const rightSide = editables.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.left + r.width / 2 >= window.innerWidth * 0.5;
    });
    if (rightSide.length === 1) return markPrivateComposer(rightSide[0], "r6.5-single-right-editor");

    return false;
  }

  async function repair() {
    if (!isSubmissionPage()) return;
    document.documentElement.setAttribute("data-sieroom-private-hf", "r6.5");

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
  setTimeout(() => repair().catch(() => {}), 500);
  setTimeout(() => repair().catch(() => {}), 1500);
  setTimeout(() => repair().catch(() => {}), 3000);

  const observer = new MutationObserver(scheduleRepair);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: [
      "aria-label", "placeholder", "data-placeholder", "contenteditable",
      "role", "title", "data-tooltip", "aria-expanded", "aria-selected"
    ]
  });
})();