import {applicationDefault, initializeApp} from "firebase-admin/app";
import {getFirestore} from "firebase-admin/firestore";
import {createHash} from "node:crypto";
import {readFile} from "node:fs/promises";

const [csvPath] = process.argv.slice(2);
if (!csvPath) throw new Error("Uso: GOOGLE_APPLICATION_CREDENTIALS=... node scripts/import-roster.mjs roster.csv");
initializeApp({credential: applicationDefault()});
const db = getFirestore();
const text = await readFile(csvPath, "utf8");
const [header, ...lines] = text.trim().split(/\r?\n/);
const fields = header.split(",").map((v) => v.trim());
const required = ["externalCode", "fullName", "publicName", "section"];
if (!required.every((name) => fields.includes(name))) throw new Error(`Columnas requeridas: ${required.join(",")}`);

let batch = db.batch(); let pending = 0; let total = 0;
for (const line of lines) {
  const values = line.split(",").map((v) => v.trim());
  const row = Object.fromEntries(fields.map((field, i) => [field, values[i] || ""]));
  if (!/^(2A|2B|5A|5B)$/.test(row.section) || !row.publicName) throw new Error(`Fila inválida: ${line}`);
  const studentId = createHash("sha256").update(`math-battle:${row.externalCode}`).digest("hex").slice(0, 24);
  batch.set(db.collection("roster").doc(studentId), {
    publicName: row.publicName,
    sortName: row.fullName.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase(),
    section: row.section,
    active: true,
  }, {merge: true});
  pending++; total++;
  if (pending === 400) { await batch.commit(); batch = db.batch(); pending = 0; }
}
if (pending) await batch.commit();
console.log(`Importados ${total} estudiantes.`);
