(() => {
  if (window.__SIEROOM_CLASSROOM_DELETE_R62_SINGLE_PASS__) return;
  window.__SIEROOM_CLASSROOM_DELETE_R62_SINGLE_PASS__ = true;

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

  function hasFullTeacherFeedbackStructure(text) {
    const raw = clean(text);
    const t = norm(raw);
    const goodMarkers = ["lo que hizo bien", "lo que hiciste bien"];
    const improveMarkers = ["lo que debe mejorar", "lo que debes mejorar", "lo que debes corregir"];
    const suggestionMarkers = ["sugerencias"];

    const hasGood = goodMarkers.some((marker) => t.includes(marker));
    const hasImprove = improveMarkers.some((marker) => t.includes(marker));
    const hasSuggestions = suggestionMarkers.some((marker) => t.includes(marker));
    if (!hasGood || !hasImprove || !hasSuggestions) return false;

    const allMarkers = [...goodMarkers, ...improveMarkers, ...suggestionMarkers];
    const positions = allMarkers
      .map((marker) => t.indexOf(marker))
      .filter((position) => position >= 0);
    const firstMarker = positions.length ? Math.min(...positions) : -1;
    if (firstMarker <= 0) return false;

    // El comentario estándar empieza por el nombre de pila (normalmente "Nombre,")
    // y puede tener una frase introductoria antes de los tres apartados.
    const lead = t.slice(0, firstMarker).trim();
    const firstLine = raw.split(/\n+/).map((line) => line.trim()).find(Boolean) || "";
    const plausibleFirstLine =
      firstLine.length >= 2 &&
      firstLine.length <= 120 &&
      /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(firstLine);
    const plausibleLead =
      lead.length >= 2 &&
      lead.length <= 320 &&
      /[a-z]/.test(lead);

    return plausibleFirstLine || plausibleLead;
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
      const renderedDuplicate = chosen.find(
        (item) => norm(item.text) === key && sameLogicalRenderedComment(item, row, container)
      );
      if (renderedDuplicate) {
        renderedDuplicate.representationCount = Number(renderedDuplicate.representationCount || 1) + 1;
        continue;
      }
      chosen.push({ ...row, domOrder: chosen.length, representationCount: 1 });
    }
    return chosen;
  }

  function stableCommentIds(host) {
    const attrs = ["data-comment-id", "data-id", "data-item-id", "data-stream-item-id"];
    const values = new Set();
    const nodes = [host, ...[...(host?.querySelectorAll?.("[data-comment-id],[data-id],[data-item-id],[data-stream-item-id]") || [])].slice(0, 12)];
    for (const node of nodes) {
      for (const attr of attrs) {
        const value = String(node?.getAttribute?.(attr) || "").trim();
        if (value) values.add(`${attr}:${value}`);
      }
    }
    return values;
  }

  function rectangleOverlapRatio(a, b) {
    if (!a || !b || a.width <= 0 || a.height <= 0 || b.width <= 0 || b.height <= 0) return 0;
    const left = Math.max(a.left, b.left);
    const top = Math.max(a.top, b.top);
    const right = Math.min(a.right, b.right);
    const bottom = Math.min(a.bottom, b.bottom);
    const width = Math.max(0, right - left);
    const height = Math.max(0, bottom - top);
    const intersection = width * height;
    const smaller = Math.min(a.width * a.height, b.width * b.height);
    return smaller > 0 ? intersection / smaller : 0;
  }

  function sameLogicalRenderedComment(a, b, container) {
    if (!a?.host || !b?.host) return false;
    if (a.host === b.host) return true;
    if (a.host.contains?.(b.host) || b.host.contains?.(a.host)) return true;

    const leftIds = stableCommentIds(a.host);
    const rightIds = stableCommentIds(b.host);
    if ([...leftIds].some((value) => rightIds.has(value))) return true;

    // Dos representaciones del mismo comentario de Classroom suelen compartir
    // exactamente el mismo botón "Más opciones", aunque estén envueltas por
    // nodos distintos.
    const leftMenu = findMenuButton(a.host, container);
    const rightMenu = findMenuButton(b.host, container);
    if (leftMenu && rightMenu && leftMenu === rightMenu) return true;

    // Última señal segura: dos cajas visuales prácticamente superpuestas con
    // el mismo texto. Dos comentarios reales aparecen en posiciones verticales
    // distintas y no cumplen este criterio.
    try {
      const ar = a.host.getBoundingClientRect();
      const br = b.host.getBoundingClientRect();
      const overlap = rectangleOverlapRatio(ar, br);
      const centerAX = ar.left + ar.width / 2;
      const centerAY = ar.top + ar.height / 2;
      const centerBX = br.left + br.width / 2;
      const centerBY = br.top + br.height / 2;
      if (
        overlap >= 0.92 &&
        Math.abs(centerAX - centerBX) <= 4 &&
        Math.abs(centerAY - centerBY) <= 4
      ) return true;
    } catch (_) {}

    return false;
  }

  function chooseTarget(rows, text, domOrder) {
    const wanted = norm(text);
    if (!wanted) throw new Error("Texto de comentario vacío.");

    if (domOrder !== null && domOrder !== undefined && domOrder !== "") {
      const index = Number(domOrder);
      if (!Number.isInteger(index) || index < 0) throw new Error("domOrder inválido.");
      const row = rows.find((item) => item.domOrder === index);
      if (row && norm(row.text) === wanted) return row;

      // Classroom puede reordenar el DOM entre la lectura y el borrado. Si la
      // posición ya no coincide, no abortamos por índice: buscamos el texto
      // exacto. Solo continuamos si existe UNA única coincidencia exacta.
      const exactAfterReorder = rows.filter((item) => norm(item.text) === wanted);
      if (exactAfterReorder.length === 1) return exactAfterReorder[0];
      if (exactAfterReorder.length === 0) {
        throw new Error("El comentario solicitado ya no está presente; no se borró nada.");
      }
      throw new Error("El texto solicitado aparece más de una vez tras el reordenamiento; no se borró nada por ambigüedad.");
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

  function visibleMenuRoots() {
    return [...document.querySelectorAll('[role="menu"],[role="listbox"]')]
      .filter((el) => visible(el));
  }

  function menuRootsLinkedToButton(menuButton) {
    const roots = [];
    const seen = new Set();
    const push = (el) => {
      if (!el || seen.has(el) || !visible(el)) return;
      seen.add(el);
      roots.push(el);
    };

    for (const attr of ["aria-controls", "aria-owns"]) {
      const raw = String(menuButton?.getAttribute?.(attr) || "").trim();
      for (const id of raw.split(/\s+/).filter(Boolean)) {
        push(document.getElementById(id));
      }
    }

    const buttonId = String(menuButton?.id || "").trim();
    if (buttonId) {
      for (const root of visibleMenuRoots()) {
        const labelled = String(root.getAttribute("aria-labelledby") || "")
          .split(/\s+/).filter(Boolean);
        if (labelled.includes(buttonId)) push(root);
      }
    }
    return roots;
  }

  function rectCenterDistance(a, b) {
    try {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      const ax = ar.left + ar.width / 2;
      const ay = ar.top + ar.height / 2;
      const bx = br.left + br.width / 2;
      const by = br.top + br.height / 2;
      return Math.hypot(ax - bx, ay - by);
    } catch (_) {
      return Number.POSITIVE_INFINITY;
    }
  }

  async function waitDeleteMenuItem(menuButton, timeoutMs = 6000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      // 1) Preferencia absoluta: el popup que Classroom relaciona
      // explícitamente con el botón exacto que acabamos de pulsar.
      const linkedRoots = menuRootsLinkedToButton(menuButton);
      for (const root of linkedRoots) {
        const controls = visibleDeleteControls(root);
        if (controls.length === 1) return controls[0];
        if (controls.length > 1) {
          throw new Error("R6: el menú exacto del comentario contiene varias acciones Eliminar/Borrar.");
        }
      }

      // 2) Fallback seguro: entre los menús visibles que contienen una acción
      // destructiva, elegir únicamente uno que esté inequívocamente junto al
      // botón pulsado. Esto descarta menús viejos que Classroom dejó en el DOM.
      const candidates = visibleMenuRoots()
        .map((root) => ({
          root,
          controls: visibleDeleteControls(root),
          distance: rectCenterDistance(menuButton, root),
        }))
        .filter((x) => x.controls.length > 0)
        .sort((a, b) => a.distance - b.distance);

      if (candidates.length === 1 && candidates[0].controls.length === 1) {
        return candidates[0].controls[0];
      }
      if (
        candidates.length > 1 &&
        candidates[0].controls.length === 1 &&
        candidates[0].distance <= 260 &&
        candidates[1].distance - candidates[0].distance >= 45
      ) {
        return candidates[0].controls[0];
      }

      // 3) Último fallback: si el documento entero expone una sola acción
      // visible, no hay ambigüedad real.
      const allControls = visibleDeleteControls(document);
      if (allControls.length === 1) return allControls[0];

      await sleep(160);
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


  function activeTeacherIdentity() {
    const selectors = [
      '[aria-label^="Cuenta de Google"]', '[aria-label^="Google Account"]',
      '[aria-label*="Cuenta de Google:"]', '[aria-label*="Google Account:"]',
      '[title^="Cuenta de Google"]', '[title^="Google Account"]'
    ].join(",");
    const values = [...document.querySelectorAll(selectors)]
      .filter(visible)
      .flatMap((el) => [
        el.getAttribute("aria-label"),
        el.getAttribute("title"),
        el.getAttribute("data-email")
      ])
      .filter(Boolean)
      .map((value) => String(value).trim());

    const emails = new Set();
    const names = new Set();
    const emailRx = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig;
    for (const value of values) {
      for (const match of value.matchAll(emailRx)) emails.add(String(match[0]).toLowerCase());
      let candidate = value
        .replace(/^(cuenta de google|google account)\s*:?\s*/i, "")
        .replace(/\([^)]*@[A-Z0-9._%+-]+\.[A-Z]{2,}\)/ig, "")
        .replace(emailRx, "")
        .replace(/[·|,;]+\s*$/g, "")
        .trim();
      if (candidate.length >= 3 && candidate.length <= 120) names.add(norm(candidate));
    }
    return { emails: [...emails], names: [...names].filter(Boolean) };
  }

  function rowLooksAuthoredByActiveTeacher(row) {
    const identity = activeTeacherIdentity();
    if (!identity.names.length) return false;
    const host = row?.host;
    const values = [
      host?.innerText,
      host?.textContent,
      host?.getAttribute?.("aria-label"),
      host?.getAttribute?.("title"),
      ...[...(host?.querySelectorAll?.("[aria-label],[title]") || [])].slice(0, 30)
        .flatMap((el) => [el.getAttribute("aria-label"), el.getAttribute("title")])
    ].filter(Boolean).join(" ");
    const haystack = norm(values);
    return identity.names.some((name) => name.length >= 3 && haystack.includes(name));
  }

  async function closeTransientMenu() {
    try {
      document.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true
      }));
      document.dispatchEvent(new KeyboardEvent("keyup", {
        key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true
      }));
    } catch (_) {}
    await sleep(100);
  }

  async function rowOffersDelete(row, container) {
    const menu = findMenuButton(row.host, container);
    if (!menu) return false;
    try {
      await closeTransientMenu();
      menu.scrollIntoView({ block: "nearest", inline: "nearest" });
      menu.click();
      const deleteItem = await waitDeleteMenuItem(menu, 1800);
      return Boolean(deleteItem);
    } finally {
      await closeTransientMenu();
    }
  }

  async function auditTeacherPrivateComments() {
    const section = await waitPrivateSection();
    await sleep(250);
    const rows = commentRows(section.container, section.label, section.composer);
    const comments = [];
    for (const row of rows) {
      const authoredByTeacherName = rowLooksAuthoredByActiveTeacher(row);
      const structuredFeedback = row.markers.length >= 2;
      const deleteAvailable = authoredByTeacherName
        ? true
        : (structuredFeedback ? await rowOffersDelete(row, section.container) : false);
      const teacherOwned = Boolean(authoredByTeacherName || (structuredFeedback && deleteAvailable));
      comments.push({
        text: row.text,
        domOrder: row.domOrder,
        characterCount: clean(row.text).length,
        markers: row.markers,
        structuredFeedback,
        teacherOwned,
        authoredByTeacherName,
        deleteAvailable,
        representationCount: Number(row.representationCount || 1),
      });
    }
    return {
      ok: true,
      operation: "audit_teacher_private_comments",
      comments,
      teacherCommentCount: comments.filter((item) => item.teacherOwned).length,
      method: "dom-v0.8.11-teacher-comment-audit-v1",
      url: location.href,
    };
  }

  function commentsAreDuplicates(a, b) {
    const left = norm(a?.text);
    const right = norm(b?.text);
    if (!left || !right) return false;
    if (left === right) return true;
    const shorter = left.length <= right.length ? left : right;
    const longer = left.length <= right.length ? right : left;
    const ratio = shorter.length / Math.max(1, longer.length);
    return shorter.length >= 80 && ratio >= 0.70 && longer.includes(shorter);
  }

  function duplicateTeacherGroups(comments) {
    // Regla docente estricta: una entrega no debe conservar más de UN comentario
    // perteneciente a la cuenta docente. El Bridge pudo regenerar una segunda
    // retroalimentación con redacción diferente; eso sigue siendo un duplicado
    // funcional aunque el texto no sea casi idéntico.
    const teacher = comments.filter((item) => item.teacherOwned);
    return teacher.length > 1 ? [teacher] : [];
  }

  async function deleteResolvedRowSinglePass(target, section) {
    const targetText = clean(target?.text);
    if (!targetText || !target?.host) throw new Error("R6.2: comentario objetivo inválido.");
    if (!target.host.isConnected) {
      throw new Error("R6.2: el comentario cambió antes del clic; se detiene en este alumno.");
    }

    const rowsBefore = commentRows(section.container, section.label, section.composer);
    const beforeMatchingCount = rowsBefore.filter((row) => norm(row.text) === norm(targetText)).length;
    if (beforeMatchingCount < 1) {
      throw new Error("R6.2: el comentario a borrar ya no está en la vista; se detiene en este alumno.");
    }

    const menu = findMenuButton(target.host, section.container);
    if (!menu) {
      throw new Error("R6.2: no apareció un menú de borrado seguro para el comentario; se detiene en este alumno.");
    }

    target.host.scrollIntoView({ block: "nearest", inline: "nearest" });
    menu.click();
    const deleteItem = await waitDeleteMenuItem(menu);
    if (!deleteItem) {
      throw new Error("R6.2: Classroom no ofreció Eliminar/Borrar; se detiene en este alumno.");
    }

    deleteItem.click();
    await confirmDeleteDialogIfNeeded();

    // Verificación LOCAL, en la misma pantalla. No reabre al alumno ni crea una
    // segunda operación de lectura en el servidor.
    const started = Date.now();
    while (Date.now() - started < 10000) {
      await sleep(350);
      const liveSection = await waitPrivateSection(2200);
      const rowsNow = commentRows(liveSection.container, liveSection.label, liveSection.composer);
      const afterMatchingCount = rowsNow.filter((row) => norm(row.text) === norm(targetText)).length;
      if (afterMatchingCount === beforeMatchingCount - 1) {
        return {
          ok: true,
          deleted: true,
          characterCount: targetText.length,
          beforeMatchingCount,
          afterMatchingCount,
          verification: "same_student_same_view_count_decreased_by_one",
        };
      }
    }
    throw new Error("R6.2: se pulsó borrar, pero no se confirmó que desapareciera exactamente un comentario en la misma vista; se detiene en este alumno.");
  }

  async function cleanupTeacherPrivateCommentDuplicatesSinglePass() {
    // R6.2: resolver UN alumno completo antes de avanzar.
    // Solo interesan retroalimentaciones con la estructura completa indicada por el docente.
    const section = await waitPrivateSection();
    await sleep(120);

    const rows = commentRows(section.container, section.label, section.composer);
    const structured = rows
      .filter((row) => hasFullTeacherFeedbackStructure(row.text))
      .map((row) => ({
        ...row,
        characterCount: clean(row.text).length,
      }));

    // FAST PATH: con cero o una retroalimentación estructurada es imposible
    // que exista el duplicado que buscamos. No abrimos menús ni hacemos sondeos.
    if (structured.length <= 1) {
      return {
        ok: true,
        resolved: true,
        operation: "cleanup_teacher_private_comment_duplicates_single_pass",
        duplicateDetected: false,
        initialStructuredFeedbackCount: structured.length,
        initialTeacherCommentCount: structured.length,
        deletedCount: 0,
        decision: structured.length === 0 ? "no_full_feedback_comment" : "single_full_feedback_comment",
        method: "dom-v0.8.12-duplicate-cleanup-single-pass-r6.2",
        url: location.href,
      };
    }

    // Solo cuando hay 2+ comentarios con la estructura completa verificamos
    // que sean del docente antes de plantear cualquier borrado.
    const owned = [];
    for (const row of structured) {
      const authoredByTeacherName = rowLooksAuthoredByActiveTeacher(row);
      const deleteAvailable = authoredByTeacherName
        ? true
        : await rowOffersDelete(row, section.container);
      const teacherOwned = Boolean(authoredByTeacherName || deleteAvailable);
      if (teacherOwned) {
        owned.push({
          ...row,
          authoredByTeacherName,
          deleteAvailable,
          teacherOwned: true,
        });
      }
    }

    if (owned.length <= 1) {
      return {
        ok: true,
        resolved: true,
        operation: "cleanup_teacher_private_comment_duplicates_single_pass",
        duplicateDetected: false,
        initialStructuredFeedbackCount: structured.length,
        initialTeacherCommentCount: owned.length,
        deletedCount: 0,
        decision: owned.length === 0
          ? "structured_comments_not_teacher_owned"
          : "single_teacher_full_feedback_comment",
        method: "dom-v0.8.12-duplicate-cleanup-single-pass-r6.2",
        url: location.href,
      };
    }

    const maxLength = Math.max(...owned.map((row) => row.characterCount));
    const maxRows = owned.filter((row) => row.characterCount === maxLength);

    let keeper;
    let tieMode = "none";
    if (maxRows.length === 1) {
      keeper = maxRows[0];
    } else {
      const normalizedMaxTexts = new Set(maxRows.map((row) => norm(row.text)));
      if (normalizedMaxTexts.size === 1) {
        // Dos o más comentarios idénticos: conservar cualquiera (el primero en DOM)
        // y borrar las demás copias idénticas.
        keeper = [...maxRows].sort((a, b) => a.domOrder - b.domOrder)[0];
        tieMode = "identical_max_text";
      } else {
        // La regla del usuario decide por más caracteres. Si son diferentes y
        // empatan exactamente en longitud, no existe un criterio seguro adicional.
        throw new Error(
          "R6.2 PAUSA: hay dos retroalimentaciones diferentes con exactamente la misma cantidad de caracteres; " +
          "no se borró ninguna porque la regla de conservar la más larga no permite desempatar."
        );
      }
    }

    const targets = owned
      .filter((row) => row !== keeper)
      .sort((a, b) => b.domOrder - a.domOrder);

    const deleted = [];
    for (const originalTarget of targets) {
      const liveSection = await waitPrivateSection();
      const liveRows = commentRows(
        liveSection.container,
        liveSection.label,
        liveSection.composer
      ).filter((row) => hasFullTeacherFeedbackStructure(row.text));

      const exact = liveRows.filter(
        (row) => norm(row.text) === norm(originalTarget.text)
      );
      if (!exact.length) {
        throw new Error(
          "R6.2 PAUSA: el comentario planificado para borrar ya no aparece en la vista; " +
          "se detiene en este alumno."
        );
      }

      // Si hay varias copias con texto idéntico, cualquiera de ellas puede borrarse.
      // Elegimos la última representación lógica visible y dejamos al menos una
      // cuando ese mismo texto es el del comentario keeper.
      if (
        norm(originalTarget.text) === norm(keeper.text) &&
        exact.length <= 1
      ) {
        throw new Error(
          "R6.2 PAUSA: solo queda una copia del comentario que debe conservarse; no se borró."
        );
      }

      const liveTarget = exact[exact.length - 1];
      const result = await deleteResolvedRowSinglePass(liveTarget, liveSection);
      deleted.push({
        characterCount: originalTarget.characterCount,
        domOrder: originalTarget.domOrder,
        identicalToKeeper: norm(originalTarget.text) === norm(keeper.text),
        result,
      });
    }

    return {
      ok: true,
      resolved: true,
      operation: "cleanup_teacher_private_comment_duplicates_single_pass",
      duplicateDetected: true,
      initialStructuredFeedbackCount: structured.length,
      initialTeacherCommentCount: owned.length,
      keeperCharacterCount: keeper.characterCount,
      keeperTieMode: tieMode,
      deletedCount: deleted.length,
      deleted,
      decision: tieMode === "identical_max_text"
        ? "kept_one_identical_deleted_other_copies"
        : "kept_longest_deleted_other_structured_feedback",
      method: "dom-v0.8.12-duplicate-cleanup-single-pass-r6.2",
      url: location.href,
    };
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
    const deleteItem = await waitDeleteMenuItem(menu);
    if (!deleteItem) throw new Error("Classroom no ofreció la opción Eliminar/Borrar para ese comentario; no se borró nada.");

    deleteItem.click();
    await confirmDeleteDialogIfNeeded();

    const started = Date.now();
    let stableDisappearances = 0;
    let lastAfterMatchingCount = beforeMatchingCount;

    while (Date.now() - started < 18000) {
      await sleep(500);

      // IMPORTANTE: no reutilizamos el contenedor anterior. Classroom puede
      // mantener un nodo viejo conectado durante varios segundos después de
      // eliminar el comentario, aunque la interfaz visible ya se haya actualizado.
      // Reubicamos desde cero la sección privada en cada comprobación.
      let currentSection;
      try {
        currentSection = await waitPrivateSection(3500);
      } catch (_) {
        stableDisappearances = 0;
        continue;
      }

      rows = commentRows(currentSection.container, currentSection.label, currentSection.composer);
      const afterMatchingCount = rows.filter((row) => norm(row.text) === norm(targetText)).length;
      lastAfterMatchingCount = afterMatchingCount;

      if (afterMatchingCount === beforeMatchingCount - 1) {
        stableDisappearances += 1;
        // Exigimos dos lecturas consecutivas del DOM fresco para evitar declarar
        // éxito por una transición temporal de Classroom.
        if (stableDisappearances >= 2) {
          return {
            ok: true,
            operation: "delete_private_comment",
            deleted: true,
            comment_text: targetText,
            dom_order: target.domOrder,
            before_matching_count: beforeMatchingCount,
            after_matching_count: afterMatchingCount,
            verification: "fresh_private_section_two_pass",
            method: "dom-v0.8.7-delete-v1",
            url: location.href,
          };
        }
      } else {
        stableDisappearances = 0;
      }
    }

    throw new Error(
      "Se ejecutó la acción de borrado, pero Classroom no confirmó de forma estable " +
      "que desapareciera exactamente un comentario coincidente. " +
      `Antes: ${beforeMatchingCount}; última lectura fresca: ${lastAfterMatchingCount}.`
    );
  }

  window.__SIEROOM_AUDIT_TEACHER_PRIVATE_COMMENTS__ = auditTeacherPrivateComments;
  window.__SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES__ = cleanupTeacherPrivateCommentDuplicatesSinglePass;
  window.__SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES_SINGLE_PASS_R6__ = cleanupTeacherPrivateCommentDuplicatesSinglePass;
  window.__SIEROOM_DELETE_PRIVATE_COMMENT_FN__ = deletePrivateComment;

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg) return;

    if (msg.type === "SIEROOM_AUDIT_TEACHER_PRIVATE_COMMENTS") {
      auditTeacherPrivateComments()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({
          ok: false,
          operation: "audit_teacher_private_comments",
          error: String(err?.message || err),
          url: location.href,
        }));
      return true;
    }

    if (msg.type === "SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES_SINGLE_PASS_R62") {
      cleanupTeacherPrivateCommentDuplicatesSinglePass()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({
          ok: false,
          resolved: false,
          operation: "cleanup_teacher_private_comment_duplicates_single_pass",
          error: String(err?.message || err),
          url: location.href,
        }));
      return true;
    }

    if (msg.type === "SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES_SINGLE_PASS_R6") {
      cleanupTeacherPrivateCommentDuplicatesSinglePass()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({
          ok: false,
          resolved: false,
          operation: "cleanup_teacher_private_comment_duplicates_single_pass",
          error: String(err?.message || err),
          url: location.href,
        }));
      return true;
    }

    if (msg.type === "SIEROOM_CLEANUP_TEACHER_PRIVATE_COMMENT_DUPLICATES") {
      cleanupTeacherPrivateCommentDuplicatesSinglePass()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({
          ok: false,
          operation: "cleanup_teacher_private_comment_duplicates",
          error: String(err?.message || err),
          url: location.href,
        }));
      return true;
    }

    if (msg.type === "SIEROOM_DELETE_PRIVATE_COMMENT") {
      deletePrivateComment(msg.commentText, msg.domOrder)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({
          ok: false,
          operation: "delete_private_comment",
          error: String(err?.message || err),
          url: location.href,
        }));
      return true;
    }
  });
})();
