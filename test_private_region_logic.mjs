import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("./browser_extension/content.js", import.meta.url), "utf8");
const start = source.indexOf("function shouldAcceptUnlabelledPrivateRegion");
const end = source.indexOf("\n\n  function bestPrivateRegion", start);
assert.ok(start >= 0 && end > start, "No se encontró la guardia del panel privado sin encabezado.");
const functionSource = source.slice(start, end);

const shouldAccept = Function(`"use strict"; ${functionSource}; return shouldAcceptUnlabelledPrivateRegion;`)();

assert.equal(shouldAccept({
  isDocumentRoot: false,
  explicitPrivateComposer: true,
  hasExistingPrivateThread: false,
  hasBoundedPrivateAction: true,
}), true, "Debe aceptar un hilo vacío con editor privado y botón Publicar acotado.");

assert.equal(shouldAccept({
  isDocumentRoot: false,
  explicitPrivateComposer: true,
  hasExistingPrivateThread: false,
  hasBoundedPrivateAction: false,
}), false, "Debe rechazar un editor privado sin región ni control de publicación verificable.");

assert.equal(shouldAccept({
  isDocumentRoot: false,
  explicitPrivateComposer: false,
  hasExistingPrivateThread: true,
  hasBoundedPrivateAction: true,
}), false, "Debe rechazar un editor no identificado explícitamente como privado.");

assert.equal(shouldAccept({
  isDocumentRoot: true,
  explicitPrivateComposer: true,
  hasExistingPrivateThread: true,
  hasBoundedPrivateAction: true,
}), false, "Nunca debe aceptar document.body/documentElement como región privada.");

assert.equal(shouldAccept({
  isDocumentRoot: false,
  explicitPrivateComposer: true,
  hasExistingPrivateThread: true,
  hasBoundedPrivateAction: false,
}), true, "Debe conservar la lectura segura de hilos privados ya existentes.");
