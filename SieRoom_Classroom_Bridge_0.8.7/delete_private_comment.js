(() => {
  if (window.__SIEROOM_CLASSROOM_DELETE_087_V1__) return;
  window.__SIEROOM_CLASSROOM_DELETE_087_V1__ = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  const clean = (value) => String(value || "")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

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
    el?.innerText && el.innerText.length < 180 ? el.innerText : "",
    el?.textContent && el.textContent.length < 180 ? el.textContent : "",
  ].filter(Boolean).join(" "));

  const isEditable = (el) => {
    if (!el || !(el instanceof Element)) return false;
    if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) return !el.disabled && !el.readOnly;
    return el.getAttribute("contenteditable") === "true" || el.getAttribute("role") === "textbox";
  };

  function privateLabel() {
    const hits = [...document.querySelectorAll("body *")].filter((el) => {
      if (!visible(el)) return false;
      const t = norm(el.textContent);
      return t.length > 0 && t.length < 100 &&
        (t.includes("comentarios privados") || t.includes("private comments"));
    });
    hits.sort((a, b) => (a.textContent || "").length - (b.textContent || "").length);
    return hits[0] || null;
  }

  function directPrivateComposer() {
    const selector = 'textarea,input,[role="textbox"],[contenteditable="true"]';
    const candidates = [...document.querySelectorAll(selector)]
      .filter((el) => visible(el) && isEditable(el))
      .map((el) => {
        const m = meta(el);
        let score = 0;
        if (m.includes("comentario privado") || m.includes("private comment")) score += 180;
        if (m.includes("anade un comentario") || m.includes("add a comment")) score += 80;
        return { el, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
    return candidates[0]?.el || null;
  }

  function ancestors(el, max = 16) {
    const out = [];
    let cur = el;
    for (let i = 0; cur && i < max; i++, cur = cur.parentElement) out.push(cur);
    return out;
  }

  function boundedPrivateSection(label, composer) {
    if (!composer) return null;
    const composerAncestors = new Set(ancestors(composer));
    if (label) {
      for (const el of ancestors(label)) {
        if (composerAncestors.has(el) && el !== document.body && el !== document.documentElement) {
          return { label, composer, container: el };
        }
      }
    }
    for (const el of ancestors(composer, 12)) {
      if (el === composer || el === document.body || el === document.documentElement) continue;
      const hasSemanticComments = el.querySelectorAll('[data-comment-id],[role="article"],[role="listitem"]').length > 0;
      const hasMore = [...el.querySelectorAll('button,[role="button"]')].some((b) => {
        const m = meta(b);
        return m.includes("mas opciones") || m.includes("more options") || m.includes("more_vert");
      });
      if (hasSemanticComments || hasMore) return { label, composer, container: el };
    }
    return null;
  }

  async function waitPrivateSection(timeoutMs = 20000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const label = privateLabel();
      const composer = directPrivateComposer();
      const section = boundedPrivateSection(label, composer);
      if (section) return section;
      await sleep(350);
    }
    throw new Error("No pude delimitar de forma segura la sección de comentarios privados.");
  }

  function privateCommentMarkers(text) {
    const t = norm(text);
    return [
      "lo que hizo bien", "lo que hiciste bien",
      "lo que debe mejorar", "lo que debes mejorar", "lo que debes corregir", "sugerencias",
      "nota cuantitativa", "calificacion cuantitativa",
      "nota cualitativa", "calificacion cualitativa", "tu calificacion es",
    ].filter((marker) => t.includes(marker));
  }

  function isUiText(text) {
    const t = norm(text);
    if (!t) return true;
    return [
      "comentarios privados", "private comments", "anade un comentario",
      "agrega un comentario", "escribe un comentario", "add a comment",
      "write a comment", "enviar", "send", "publicar", "post",
      "instrucciones", "trabajo de los alumnos", "more_vert",
      "more_vert mas opciones", "mas opciones", "more options",
    ].includes(t);
  }

  function commentRows(container, label, composer) {
    const rows = [];
    const selector = '[data-comment-id],[role="article"],[role="listitem"],div';
    for (const el of container.querySelectorAll(selector)) {
      if (!visible(el) || el === label || label?.contains?.(el)) continue;
      if (el === composer || composer?.contains?.(el) || el.contains?.(composer)) continue;
      const text = clean(el.innerText || el.textContent || "");
      if (text.length < 2 || text.length > 6000 || isUiText(text)) continue;
      const markers = privateCommentMarkers(text);
      const semantic = el.matches('[data-comment-id],[role="article"],[role="listitem"]');
      if (markers.length < 2 && !semantic) continue;
      const host = el.closest('[data-comment-id],[role="article"],[role="listitem"]') || el;
      rows.push({ text, host, markers });
    }

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
      if (chosen.some((item) => norm(item.text) === key && item.host === row.host)) continue;
      chosen.push({ ...row, domOrder: chosen.length });
    }
    return chosen;
  }

  function chooseTarget(rows, text, domOrder) {
    const wanted = norm(text);
    if (!wanted) throw new Error("Texto de comentario vacío.");

    if (domOrder !== null && domOrder !== undefined && domOrder !== "") {
      const index = Number(domOrder);
      if (!Number.isInteger(index) || index < 0) throw new Error("domOrder inválido.");
      const row = rows.find((item) => item.domOrder === index);
      if (!row) throw new Error(`No existe un comentario en la posición ${index}.`);
      if (norm(row.text) !== wanted) {
        throw new Error("El comentario de esa posición ya no coincide exactamente con el texto solicitado; no se borró nada.");
      }
      return row;
    }

    const exact = rows.filter((row) => norm(row.text) === wanted);
    if (exact.length === 0) throw new Error("No encontré el comentario privado exacto solicitado.");
    if (exact.length > 1) {
      throw new Error("Hay más de un comentario privado con el mismo texto. Indica domOrder para evitar un borrado ambiguo.");
    }
    return exact[0];
  }

  function findMenuButton(host, container) {
    const moreWords = ["mas opciones", "more options", "more_vert", "acciones", "actions"];
    const inside = [...host.querySelectorAll('button,[role="button"]')]
      .filter((b) => visible(b) && !b.disabled && b.getAttribute("aria-disabled") !== "true")
      .map((b) => ({ b, m: meta(b) }))
      .filter((x) => moreWords.some((w) => x.m.includes(w)));
    if (inside.length === 1) return inside[0].b;
    if (inside.length > 1) return inside[inside.length - 1].b;

    const parent = host.parentElement;
    if (!parent || !container.contains(parent)) return null;
    const hr = host.getBoundingClientRect();
    const nearby = [...parent.querySelectorAll('button,[role="button"]')]
      .filter((b) => visible(b) && !host.contains(b) && !b.disabled && b.getAttribute("aria-disabled") !== "true")
      .map((b) => ({ b, m: meta(b), r: b.getBoundingClientRect() }))
      .filter((x) => moreWords.some((w) => x.m.includes(w)))
      .filter((x) => Math.abs((x.r.top + x.r.height / 2) - (hr.top + hr.height / 2)) <= Math.max(60, hr.height / 2 + 20));
    return nearby.length === 1 ? nearby[0].b : null;
  }

  function visibleDeleteControls(root = document) {
    const exact = new Set([
      "eliminar", "borrar", "delete",
      "eliminar comentario", "borrar comentario", "delete comment",
    ]);
    return [...root.querySelectorAll('[role="menuitem"],[role="option"],button,[role="button"]')]
      .filter((el) => visible(el) && !el.disabled && el.getAttribute("aria-disabled") !== "true")
      .filter((el) => exact.has(norm(el.innerText || el.textContent || el.getAttribute("aria-label") || "")));
  }

  async function waitDeleteMenuItem(timeoutMs = 6000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const controls = visibleDeleteControls(document);
      if (controls.length === 1) return controls[0];
      if (controls.length > 1) {
        const menuControls = controls.filter((el) => el.closest('[role="menu"]'));
        if (menuControls.length === 1) return menuControls[0];
        throw new Error("Aparecieron varias acciones Eliminar/Borrar; no se eligió ninguna por seguridad.");
      }
      await sleep(200);
    }
    return null;
  }

  async function confirmDeleteDialogIfNeeded() {
    const start = Date.now();
    while (Date.now() - start < 5000) {
      const dialogs = [...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].filter(visible);
      if (!dialogs.length) {
        await sleep(250);
        continue;
      }
      for (const dialog of dialogs) {
        const dialogText = norm(dialog.innerText || dialog.textContent || "");
        if (!dialogText.includes("coment") && !dialogText.includes("comment")) continue;
        const controls = visibleDeleteControls(dialog);
        if (controls.length === 1) {
          controls[0].click();
          return { confirmed: true };
        }
        if (controls.length > 1) {
          throw new Error("El diálogo de borrado contiene varias acciones destructivas ambiguas.");
        }
      }
      await sleep(250);
    }
    return { confirmed: false, noDialog: true };
  }

  async function deletePrivateComment(text, domOrder = null) {
    const targetText = clean(text);
    if (!targetText) throw new Error("Texto de comentario vacío.");

    const section = await waitPrivateSection();
    await sleep(350);
    let rows = commentRows(section.container, section.label, section.composer);
    const target = chooseTarget(rows, targetText, domOrder);
    const beforeMatchingCount = rows.filter((row) => norm(row.text) === norm(targetText)).length;

    const menu = findMenuButton(target.host, section.container);
    if (!menu) {
      throw new Error("El comentario exacto fue localizado, pero Classroom no mostró un menú propio y seguro para ese comentario. Probablemente no sea eliminable por esta cuenta.");
    }

    target.host.scrollIntoView({ block: "nearest", inline: "nearest" });
    menu.click();
    const deleteItem = await waitDeleteMenuItem();
    if (!deleteItem) throw new Error("Classroom no ofreció la opción Eliminar/Borrar para ese comentario; no se borró nada.");

    deleteItem.click();
    await confirmDeleteDialogIfNeeded();

    const started = Date.now();
    while (Date.now() - started < 12000) {
      await sleep(400);
      const currentSection = section.container?.isConnected ? section : await waitPrivateSection(3000);
      rows = commentRows(currentSection.container, currentSection.label, currentSection.composer);
      const afterMatchingCount = rows.filter((row) => norm(row.text) === norm(targetText)).length;
      if (afterMatchingCount === beforeMatchingCount - 1) {
        return {
          ok: true,
          operation: "delete_private_comment",
          deleted: true,
          comment_text: targetText,
          dom_order: target.domOrder,
          before_matching_count: beforeMatchingCount,
          after_matching_count: afterMatchingCount,
          method: "dom-v0.8.7-delete-v1",
          url: location.href,
        };
      }
    }

    throw new Error("Se ejecutó la acción de borrado, pero Classroom no confirmó que desapareciera exactamente un comentario coincidente.");
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "SIEROOM_DELETE_PRIVATE_COMMENT") return;
    deletePrivateComment(msg.commentText, msg.domOrder)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({
        ok: false,
        operation: "delete_private_comment",
        error: String(err?.message || err),
        url: location.href,
      }));
    return true;
  });
})();
