import {initializeApp} from "firebase-admin/app";
import {FieldValue, getFirestore, Timestamp} from "firebase-admin/firestore";
import {HttpsError, onCall, onRequest} from "firebase-functions/v2/https";

initializeApp();
const db = getFirestore();
const regions = ["us-central1"];
const sections = new Set(["2A", "2B", "5A", "5B"]);
const avatars = new Set(["ninja", "singer_boy", "singer_girl", "astronaut_boy", "astronaut_girl", "hero", "heroine", "fighter", "martial", "dragon", "lightning", "tiger", "wolf", "lion", "eagle"]);

function requireUser(request: {auth?: {uid: string; token: Record<string, unknown>}}) {
  if (!request.auth) throw new HttpsError("unauthenticated", "Debes iniciar sesión con Google.");
  const email = String(request.auth.token.email || "").trim().toLowerCase();
  if (!email || request.auth.token.email_verified !== true) throw new HttpsError("permission-denied", "El correo Google no está verificado.");
  return {uid: request.auth.uid, email};
}

export const listRoster = onCall({region: regions, enforceAppCheck: true}, async (request) => {
  requireUser(request);
  const section = String(request.data?.section || "").toUpperCase();
  if (!sections.has(section)) throw new HttpsError("invalid-argument", "Sección no válida.");
  const snapshot = await db.collection("roster").where("section", "==", section).where("active", "==", true).orderBy("sortName").get();
  return {students: snapshot.docs.map((doc) => ({
    studentId: doc.id,
    publicName: doc.get("publicName"),
    available: !doc.get("claimedUid"),
  }))};
});

export const claimStudent = onCall({region: regions, enforceAppCheck: true}, async (request) => {
  const {uid, email} = requireUser(request);
  const studentId = String(request.data?.studentId || "");
  if (!/^[A-Za-z0-9_-]{4,100}$/.test(studentId)) throw new HttpsError("invalid-argument", "Estudiante no válido.");
  const rosterRef = db.collection("roster").doc(studentId);
  const profileRef = db.collection("profiles").doc(uid);

  await db.runTransaction(async (tx) => {
    const [roster, existing] = await Promise.all([tx.get(rosterRef), tx.get(profileRef)]);
    if (existing.exists) return;
    if (!roster.exists || roster.get("active") !== true) throw new HttpsError("not-found", "El estudiante no está activo.");
    if (roster.get("claimedUid") && roster.get("claimedUid") !== uid) throw new HttpsError("already-exists", "Ese estudiante ya está vinculado.");
    if (String(roster.get("emailLower") || "").toLowerCase() !== email) throw new HttpsError("permission-denied", "El correo no corresponde al estudiante.");
    const profile = {
      uid,
      publicName: roster.get("publicName"),
      section: roster.get("section"),
      avatarId: "ninja",
      bestScore: 0,
      bestLevel: 1,
      bestAccuracy: 0,
      plays: 0,
      createdAt: FieldValue.serverTimestamp(),
      updatedAt: FieldValue.serverTimestamp(),
    };
    tx.create(profileRef, profile);
    tx.update(rosterRef, {claimedUid: uid, claimedAt: FieldValue.serverTimestamp()});
  });
  return {ok: true};
});

export const updateAvatar = onCall({region: regions, enforceAppCheck: true}, async (request) => {
  const {uid} = requireUser(request);
  const avatarId = String(request.data?.avatarId || "");
  if (!avatars.has(avatarId)) throw new HttpsError("invalid-argument", "Avatar no válido.");
  await db.collection("profiles").doc(uid).update({avatarId, updatedAt: FieldValue.serverTimestamp()});
  await db.collection("leaderboard").doc(uid).set({avatarId}, {merge: true});
  return {ok: true};
});

export const submitScore = onCall({region: regions, enforceAppCheck: true}, async (request) => {
  const {uid} = requireUser(request);
  const score = Number(request.data?.score);
  const correct = Number(request.data?.correct);
  const wrong = Number(request.data?.wrong);
  const level = Number(request.data?.level);
  const accuracy = Number(request.data?.accuracy);
  const bestStreak = Number(request.data?.bestStreak);
  const durationMs = Number(request.data?.durationMs);
  const sessionId = String(request.data?.sessionId || "");
  if (![score, correct, wrong, level, accuracy, bestStreak, durationMs].every(Number.isFinite) ||
      score !== correct || score < 0 || score > 500 || wrong < 0 || wrong > 500 ||
      level !== (score < 30 ? 1 : score < 50 ? 2 : 3) || accuracy < 0 || accuracy > 100 ||
      bestStreak < 0 || bestStreak > correct || durationMs < (correct + wrong) * 180 ||
      !/^[a-f0-9-]{30,40}$/i.test(sessionId)) {
    throw new HttpsError("invalid-argument", "Resultado no válido.");
  }

  const profileRef = db.collection("profiles").doc(uid);
  const boardRef = db.collection("leaderboard").doc(uid);
  const submissionRef = db.collection("scoreSubmissions").doc(`${uid}_${sessionId}`);
  let section = "";
  await db.runTransaction(async (tx) => {
    const [profile, duplicate] = await Promise.all([tx.get(profileRef), tx.get(submissionRef)]);
    if (!profile.exists) throw new HttpsError("failed-precondition", "Primero vincula tu identidad.");
    if (duplicate.exists) throw new HttpsError("already-exists", "La partida ya fue registrada.");
    section = String(profile.get("section"));
    tx.create(submissionRef, {uid, score, correct, wrong, level, accuracy, bestStreak, durationMs, sessionId, clientVersion: String(request.data?.clientVersion || ""), createdAt: FieldValue.serverTimestamp()});
    const previous = Number(profile.get("bestScore") || 0);
    tx.update(profileRef, {plays: FieldValue.increment(1), updatedAt: FieldValue.serverTimestamp(), ...(score > previous ? {bestScore: score, bestLevel: level, bestAccuracy: accuracy} : {})});
    if (score > previous) tx.set(boardRef, {uid, publicName: profile.get("publicName"), section, avatarId: profile.get("avatarId"), bestScore: score, bestLevel: level, bestAccuracy: accuracy, achievedAt: FieldValue.serverTimestamp()});
  });
  const ahead = await db.collection("leaderboard").where("section", "==", section).where("bestScore", ">", score).count().get();
  return {ok: true, sectionRank: ahead.data().count + 1};
});

export const publicLeaderboard = onRequest({region: regions, cors: true}, async (request, response) => {
  const section = String(request.query.section || "2A").toUpperCase();
  if (!sections.has(section)) { response.status(400).json({error: "invalid_section"}); return; }
  const snapshot = await db.collection("leaderboard").where("section", "==", section).orderBy("bestScore", "desc").orderBy("achievedAt", "asc").limit(100).get();
  response.set("Cache-Control", "public, max-age=15, s-maxage=30");
  response.json({section, updatedAt: Timestamp.now().toMillis(), players: snapshot.docs.map((doc, index) => ({rank: index + 1, publicName: doc.get("publicName"), section: doc.get("section"), avatarId: doc.get("avatarId"), bestScore: doc.get("bestScore"), bestLevel: doc.get("bestLevel"), bestAccuracy: doc.get("bestAccuracy")}))});
});
