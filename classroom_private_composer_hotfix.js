(() => {
  if (window.__SIEROOM_PRIVATE_COMPOSER_HF_R63__) return;
  window.__SIEROOM_PRIVATE_COMPOSER_HF_R63__ = true;

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
    el?.innerText && el.innerText.length < 160 ? el.innerText : "",
    el?.textContent && el.textContent.length < 160 ? el.textContent : "",
  ].filter(Boolean).join(" "));

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
    return m.includes("ayuda y comentarios") || m.includes("help and feedback") || m.includes("send feedback");
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

  function markPrivateComposer(el) {
    if (!isEditable(el)) return;
    const m = meta(el);
    if (!m.includes("coment") && !m.includes("comment")) {
      el.setAttribute("data-placeholder", "Comentario privado");
    }
    el.setAttribute("data-sieroom-private-composer", "r6.3");
  }

  function markPrivateLauncher(el) {
    if (!isLauncher(el)) return;
    const m = meta(el);
    if (!m.includes("privad") && !m.includes("private")) {
      el.setAttribute("data-placeholder", "Añade un comentario privado");
    }
    el.setAttribute("data-sieroom-private-launcher", "r6.3");
  }

  function repairAround(anchor) {
    if (!anchor || !visible(anchor)) return;
    const roots = ancestors(anchor, 10);
    for (const root of roots) {
      const editables = [...root.querySelectorAll('textarea,input,[role="textbox"],[contenteditable="true"]')]
        .filter((el) => isEditable(el) && near(el, anchor));
      if (editables.length) {
        editables.forEach(markPrivateComposer);
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

  function repair() {
    const labelledPrivate = [...document.querySelectorAll('[aria-label],[role="heading"],h1,h2,h3,h4')]
      .filter((el) => visible(el) && isPrivateHeading(el));
    for (const heading of labelledPrivate) repairAround(heading);

    // La UI nueva puede ocultar el título "Comentarios privados" cuando ya existe
    // un hilo. En ese caso, el comentario publicado es una señal inequívoca y acotada
    // para localizar únicamente el compositor/launcher del mismo panel.
    const posted = [...document.querySelectorAll('[aria-label]')]
      .filter((el) => visible(el) && isPostedPrivateCommentAnchor(el));
    for (const anchor of posted) repairAround(anchor);
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
