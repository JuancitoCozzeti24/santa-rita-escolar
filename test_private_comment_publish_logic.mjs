import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("./browser_extension/content.js", import.meta.url), "utf8");
const normSource = `const norm = (s) => String(s || "")
  .normalize("NFD")
  .replace(/[\\u0300-\\u036f]/g, "")
  .replace(/\\s+/g, " ")
  .trim()
  .toLowerCase();`;

const actionStart = source.indexOf("const isHelpFeedbackControlText");
const actionEnd = source.indexOf("\n\n  function privateCommentLabel", actionStart);
assert.ok(actionStart >= 0 && actionEnd > actionStart, "No se encontraron las guardias de publicación.");
const actionSource = source.slice(actionStart, actionEnd);
const isExplicitSend = Function(
  `"use strict"; ${normSource} ${actionSource}; return isExplicitCommentSendText;`
)();

assert.equal(isExplicitSend("Publicar"), true);
assert.equal(isExplicitSend("Enviar comentario privado"), true);
assert.equal(isExplicitSend("Post private comment"), true);
assert.equal(isExplicitSend("Ayuda y comentarios"), false);
assert.equal(isExplicitSend("Help & feedback"), false);
assert.equal(isExplicitSend("Enviar comentarios"), false);
assert.equal(isExplicitSend("Comentar"), false);

const matchStart = source.indexOf("function commentFingerprints");
const matchEnd = source.indexOf("\n\n  function composerHasFullText", matchStart);
assert.ok(matchStart >= 0 && matchEnd > matchStart, "No se encontró la confirmación por huellas.");
const matchSource = source.slice(matchStart, matchEnd);
const commentTextMatches = Function(
  `"use strict"; ${normSource} ${matchSource}; return commentTextMatches;`
)();

const detailed = `Resultado\n17/20 — A.\n\nLo que hiciste bien\nResuelve operaciones matriciales con orden.\n\nLo que debes reforzar o hiciste mal\nEn la pregunta 14 debe obtener x=4 y verificar por sustitución. En la 17 falta x=-3.\n\nSugerencias\nRevisa signos, dimensiones e interpretación final.`;
assert.equal(commentTextMatches(detailed, detailed), true, "Debe reconocer el comentario completo.");
assert.equal(
  commentTextMatches(detailed.slice(0, detailed.indexOf("Sugerencias")), detailed),
  true,
  "Debe reconocer una representación visual truncada que conserva dos huellas independientes."
);
assert.equal(
  commentTextMatches(
    "Resultado 12/20 — B. Lo que hiciste bien Trabajo parcial. Lo que debes reforzar o hiciste mal La pregunta 8 está en blanco.",
    detailed
  ),
  false,
  "No debe confundir retroalimentaciones distintas."
);

const bridge = fs.readFileSync(new URL("./browser_extension/bridge.js", import.meta.url), "utf8");
const retryStart = bridge.indexOf("function isMissingPrivateEditorResult");
const retryEnd = bridge.indexOf("\n\nasync function reloadClassroomTarget", retryStart);
assert.ok(retryStart >= 0 && retryEnd > retryStart, "No se encontró la guardia de reintento seguro.");
const retrySource = bridge.slice(retryStart, retryEnd);
const isMissingPrivateEditorResult = Function(
  `"use strict"; ${retrySource}; return isMissingPrivateEditorResult;`
)();

assert.equal(isMissingPrivateEditorResult({
  ok: false,
  error: "No encontré el editor de Comentarios privados en esta entrega."
}), true, "La ausencia previa a escribir admite un solo reload.");
assert.equal(isMissingPrivateEditorResult({
  ok: false,
  error: "Se pulsó Enviar/Publicar, pero no pude confirmar visualmente."
}), false, "Un resultado ambiguo después del clic jamás debe reintentarse automáticamente.");

const ensureStart = bridge.indexOf("async function ensureClassroomTab");
const ensureEnd = bridge.indexOf("\n\nfunction promiseTimeout", ensureStart);
assert.ok(ensureStart >= 0 && ensureEnd > ensureStart, "No se encontró ensureClassroomTab.");
const ensureSource = bridge.slice(ensureStart, ensureEnd);

const runEnsureScenario = Function(`"use strict";
  return async function run(existingUrl, targetUrl) {
    let classroomTabId = 77;
    const calls = [];
    class BridgeResetError extends Error {}
    const chrome = { tabs: {
      get: async () => ({ id: 77, status: "complete", url: existingUrl }),
      update: async (_id, options) => { calls.push(["update", options.url]); return { id: 77, status: "complete", url: options.url }; },
      create: async (options) => { calls.push(["create", options.url]); return { id: 88, status: "complete", url: options.url }; }
    }};
    const classroomTargetMatches = (actual, expected) => actual === expected;
    const activateTab = async (id) => { calls.push(["activate", id]); };
    const sleep = async (ms) => { calls.push(["sleep", ms]); };
    const assertGeneration = () => {};
    const assertTabTarget = async (id, expected) => { calls.push(["assert", expected]); return { id, status: "complete", url: expected }; };
    const waitTabTargetComplete = async (id, expected) => { calls.push(["wait", expected]); return { id, status: "complete", url: expected }; };
    ${ensureSource}
    const tab = await ensureClassroomTab(targetUrl, 0);
    return { tab, calls };
  };
`)();

const sameTarget = await runEnsureScenario("https://classroom.google.com/student/1", "https://classroom.google.com/student/1");
assert.equal(sameTarget.calls.some(([name]) => name === "update"), false,
  "La lectura y escritura consecutivas del mismo alumno no deben recargar la vista.");
assert.equal(sameTarget.calls.some(([name, value]) => name === "sleep" && value === 900), true);

const otherTarget = await runEnsureScenario("https://classroom.google.com/student/1", "https://classroom.google.com/student/2");
assert.equal(otherTarget.calls.some(([name]) => name === "update"), true,
  "Cambiar de alumno sí debe navegar a la entrega exacta solicitada.");
