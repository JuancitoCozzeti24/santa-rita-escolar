(() => {
  if (window.__SIEROOM_GRADING_TAB_HF_R67__) return;
  window.__SIEROOM_GRADING_TAB_HF_R67__ = true;

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
    el?.getAttribute?.("title"),
    el?.getAttribute?.("data-tooltip"),
    el?.getAttribute?.("aria-description"),
    el?.innerText && el.innerText.length < 160 ? el.innerText : "",
    el?.textContent && el.textContent.length < 160 ? el.textContent : "",
  ].filter(Boolean).join(" "));

  const isSubmissionPage = () =>
    /\/submissions\/by-status\/and-sort-last-name\/student\//.test(location.pathname);

  const isEditable = (el) => {
    if (!el || !(el instanceof Element)) return false;
    return el.matches?.('input,textarea,[contenteditable="true"],[role="textbox"]');
  };

  const isPrivateUiVisible = () => {
    const nodes = [...document.querySelectorAll('[aria-label],[placeholder],[data-placeholder],[role="heading"],h1,h2,h3,h4')];
    return nodes.some((el) => {
      if (!visible(el)) return false;
      const m = meta(el);
      return m.includes("comentarios privados") ||
        m.includes("comentario privado") ||
        m.includes("private comments") ||
        m.includes("private comment");
    });
  };

  const isGradeTabText = (m) => {
    const t = norm(m);
    if (!t) return false;
    return t === "calificaciones" || t === "calificacion" ||
      t === "grading" || t === "marking" ||
      t.includes("calificaciones") ||
      t.includes("herramienta de calificacion") ||
      t.includes("grading") || t.includes("marking");
  };

  const rejectText = (m) => {
    const t = norm(m);
    return t.includes("configuracion de calificaciones") ||
      t.includes("grade settings") ||
      t.includes("libro de calificaciones") ||
      t.includes("gradebook") ||
      t.includes("ayuda y comentarios") ||
      t.includes("help and feedback");
  };

  function textualCandidates() {
    const selector = 'button,[role="button"],[role="tab"],[aria-label],[title],[data-tooltip]';
    return [...document.querySelectorAll(selector)]
      .filter((el) => visible(el) && !isEditable(el))
      .map((el) => {
        const m = meta(el);
        if (!isGradeTabText(m) || rejectText(m)) return null;
        let score = 0;
        if (m === "calificaciones" || m === "grading" || m === "marking") score += 220;
        else if (m.includes("calificaciones") || m.includes("grading") || m.includes("marking")) score += 170;
        const role = norm(el.getAttribute("role"));
        if (el.tagName === "BUTTON" || role === "button" || role === "tab") score += 45;
        if (role === "tab") score += 35;
        const r = el.getBoundingClientRect();
        if (r.left + r.width / 2 >= window.innerWidth * 0.45) score += 30;
        if (el.getAttribute("aria-selected") === "true" || el.getAttribute("aria-pressed") === "true") score += 20;
        return { el, score, m };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score);
  }

  function safeSidebarFallback() {
    const controls = [...document.querySelectorAll('button,[role="button"],[role="tab"]')]
      .filter((el) => visible(el) && !isEditable(el))
      .map((el) => ({ el, m: meta(el), r: el.getBoundingClientRect() }))
      .filter((x) => {
        const w = x.r.width, h = x.r.height;
        const cx = x.r.left + w / 2;
        return cx >= window.innerWidth * 0.62 && w >= 20 && w <= 90 && h >= 20 && h <= 90;
      });

    const hasFiles = controls.some((x) =>
      x.m.includes("archivo") || x.m.includes("files") || x.m.includes("entrega") || x.m.includes("submission"));
    const hasBank = controls.some((x) =>
      x.m.includes("banco de comentarios") || x.m.includes("comment bank") || x.m.includes("comment_bank"));
    if (!hasFiles || !hasBank) return null;

    for (const seed of controls) {
      const sx = seed.r.left + seed.r.width / 2;
      const cluster = controls
        .filter((x) => Math.abs((x.r.left + x.r.width / 2) - sx) <= 34)
        .sort((a, b) => a.r.top - b.r.top);
      if (cluster.length < 3 || cluster.length > 5) continue;
      const filesIndex = cluster.findIndex((x) =>
        x.m.includes("archivo") || x.m.includes("files") || x.m.includes("entrega") || x.m.includes("submission"));
      const bankIndex = cluster.findIndex((x) =>
        x.m.includes("banco de comentarios") || x.m.includes("comment bank") || x.m.includes("comment_bank"));
      if (filesIndex < 0 || bankIndex < 0 || filesIndex === bankIndex) continue;
      const lo = Math.min(filesIndex, bankIndex);
      const hi = Math.max(filesIndex, bankIndex);
      if (hi - lo !== 2) continue;
      const middle = cluster[lo + 1];
      if (!middle || rejectText(middle.m)) continue;
      return middle.el;
    }
    return null;
  }

  let lastUrl = "";
  let attempts = 0;
  let lastAttemptAt = 0;

  function clickGradingTab() {
    if (!isSubmissionPage() || isPrivateUiVisible()) return false;
    if (lastUrl !== location.href) {
      lastUrl = location.href;
      attempts = 0;
      lastAttemptAt = 0;
    }
    if (attempts >= 4 || Date.now() - lastAttemptAt < 1600) return false;

    const candidates = textualCandidates();
    let target = null;
    let evidence = "";
    if (candidates[0] && candidates[0].score >= 200) {
      if (!candidates[1] || candidates[0].score - candidates[1].score >= 20 || candidates[0].m === "calificaciones") {
        target = candidates[0].el;
        evidence = `text:${candidates[0].m.slice(0, 80)}`;
      }
    }
    if (!target) {
      target = safeSidebarFallback();
      if (target) evidence = `sidebar:${meta(target).slice(0, 80) || "middle-control"}`;
    }
    if (!target) return false;

    attempts += 1;
    lastAttemptAt = Date.now();
    try {
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
      target.click();
      document.documentElement.setAttribute("data-sieroom-grading-panel-opened", "r6.7");
      document.documentElement.setAttribute("data-sieroom-grading-panel-evidence", evidence);
      return true;
    } catch (_) {
      return false;
    }
  }

  const run = () => {
    if (!isSubmissionPage()) return;
    clickGradingTab();
  };

  run();
  setTimeout(run, 450);
  setTimeout(run, 1200);
  setTimeout(run, 2600);
  setTimeout(run, 5200);

  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      run();
    }, 120);
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-label", "title", "data-tooltip", "aria-selected", "aria-pressed", "role"]
  });
})();