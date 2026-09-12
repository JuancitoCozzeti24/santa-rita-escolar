import {applicationDefault, initializeApp} from "firebase-admin/app";
import {getFirestore} from "firebase-admin/firestore";
import {createHash} from "node:crypto";
import {readFile} from "node:fs/promises";

const [csvPath] = process.argv.slice(2);
if (!csvPath) throw new Error("Uso: GOOGLE_APPLICATION_CREDENTIALS=... node scripts/import-roster.mjs roster.csv");
initializeApp({credential: applicationDefault()});
const db = getFirestore();
const text = (await readFile(csvPath, "utf8")).replace(/^\uFEFF/, "");

function parseCsv(source) {
  const records = [];
  let record = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < source.length; index++) {
    const character = source[index];
    if (quoted) {
      if (character === '"' && source[index + 1] === '"') {
        field += '"';
        index++;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ",") {
      record.push(field);
      field = "";
    } else if (character === "\n") {
      record.push(field.replace(/\r$/, ""));
      records.push(record);
      record = [];
      field = "";
    } else {
      field += character;
    }
  }
  if (field || record.length) {
    record.push(field);
    records.push(record);
  }
  return records.filter((row) => row.some(Boolean));
}

const records = parseCsv(text);
const fields = records.shift().map((v) => v.trim().replace(/^\+/, ""));
const required = ["externalCode", "fullName", "publicName", "section"];
if (!required.every((name) => fields.includes(name))) throw new Error(`Columnas requeridas: ${required.join(",")}`);

let batch = db.batch(); let pending = 0; let total = 0;
for (const values of records) {
  const row = Object.fromEntries(fields.map((field, i) => [field, values[i] || ""]));
  if (!/^(2A|2B|5A|5B)$/.test(row.section) || !row.publicName) throw new Error("La matrícula contiene una fila inválida.");
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
