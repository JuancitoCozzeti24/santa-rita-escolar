package pe.profejohnny.mathbattle.data

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FieldValue
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await
import pe.profejohnny.mathbattle.BuildConfig
import pe.profejohnny.mathbattle.model.BattleResult
import pe.profejohnny.mathbattle.model.RankingEntry
import pe.profejohnny.mathbattle.model.StudentProfile

data class RosterChoice(val studentId: String, val publicName: String, val available: Boolean)

private const val OWNER_EMAIL = "profejohnnyb@gmail.com"

class MathBattleRepository(
    private val auth: FirebaseAuth = FirebaseAuth.getInstance(),
    private val firestore: FirebaseFirestore = FirebaseFirestore.getInstance()
) {
    val currentUid: String? get() = auth.currentUser?.uid
    val currentEmail: String? get() = auth.currentUser?.email
    val isSignedIn: Boolean get() = auth.currentUser != null
    val isAdmin: Boolean get() = currentEmail.equals(OWNER_EMAIL, ignoreCase = true)

    suspend fun loadMyProfile(): StudentProfile? {
        val uid = currentUid ?: return null
        return firestore.collection("profiles").document(uid).get().await().toObject(StudentProfile::class.java)
    }

    suspend fun listRoster(section: String): List<RosterChoice> = firestore.collection("roster")
        .whereEqualTo("section", section).whereEqualTo("active", true).orderBy("sortName")
        .get().await().documents.map { doc ->
            RosterChoice(doc.id, doc.getString("publicName") ?: "Estudiante", doc.getString("claimedUid").isNullOrBlank())
        }

    suspend fun claimStudent(studentId: String): StudentProfile {
        val uid = requireNotNull(currentUid) { "Debes iniciar sesión." }
        val rosterRef = firestore.collection("roster").document(studentId)
        val profileRef = firestore.collection("profiles").document(uid)
        firestore.runTransaction { tx ->
            val existing = tx.get(profileRef)
            if (existing.exists()) return@runTransaction null
            val roster = tx.get(rosterRef)
            require(roster.exists() && roster.getBoolean("active") == true) { "Estudiante no válido." }
            val claimedUid = roster.getString("claimedUid")
            require(claimedUid.isNullOrBlank() || claimedUid == uid) { "Ese estudiante ya está vinculado." }
            tx.set(profileRef, mapOf(
                "uid" to uid, "rosterId" to studentId,
                "publicName" to (roster.getString("publicName") ?: "Estudiante"),
                "section" to (roster.getString("section") ?: ""), "avatarId" to "ninja",
                "bestScore" to 0, "bestLevel" to 1, "bestAccuracy" to 0, "plays" to 0,
                "createdAt" to FieldValue.serverTimestamp(), "updatedAt" to FieldValue.serverTimestamp()
            ))
            tx.update(rosterRef, mapOf("claimedUid" to uid, "claimedAt" to FieldValue.serverTimestamp()))
            null
        }.await()
        return requireNotNull(loadMyProfile()) { "No se creó el perfil." }
    }

    suspend fun createPublicProfile(): StudentProfile {
        val user = requireNotNull(auth.currentUser) { "Debes iniciar sesión." }
        val uid = user.uid
        val profileRef = firestore.collection("profiles").document(uid)
        val existing = profileRef.get().await()
        if (!existing.exists()) {
            val googleName = user.displayName?.trim()?.take(40)
            val publicName = googleName?.takeIf { it.isNotBlank() }
                ?: user.email?.substringBefore('@')?.take(40)
                ?: "Jugador"
            profileRef.set(mapOf(
                "uid" to uid, "rosterId" to "PUBLIC", "publicName" to publicName,
                "section" to "LIBRE", "avatarId" to "ninja",
                "bestScore" to 0, "bestLevel" to 1, "bestAccuracy" to 0, "plays" to 0,
                "createdAt" to FieldValue.serverTimestamp(), "updatedAt" to FieldValue.serverTimestamp()
            )).await()
        }
        return requireNotNull(loadMyProfile()) { "No se creó el perfil de Batalla Libre." }
    }

    suspend fun selectOwnerSection(section: String): StudentProfile {
        require(isAdmin) { "Solo el propietario puede usar esta función." }
        require(section in setOf("2A", "2B", "5A", "5B")) { "Aula no válida." }
        val uid = requireNotNull(currentUid) { "Debes iniciar sesión." }
        val profileRef = firestore.collection("profiles").document(uid)
        val existing = profileRef.get().await()
        if (existing.exists()) {
            profileRef.update(mapOf(
                "publicName" to "Profe Johnny", "section" to section,
                "updatedAt" to FieldValue.serverTimestamp()
            )).await()
        } else {
            profileRef.set(mapOf(
                "uid" to uid, "rosterId" to "OWNER", "publicName" to "Profe Johnny",
                "section" to section, "avatarId" to "lightning",
                "bestScore" to 0, "bestLevel" to 1, "bestAccuracy" to 0, "plays" to 0,
                "createdAt" to FieldValue.serverTimestamp(), "updatedAt" to FieldValue.serverTimestamp()
            )).await()
        }
        return requireNotNull(loadMyProfile()) { "No se pudo crear el perfil del propietario." }
    }

    suspend fun updateAvatar(avatarId: String): StudentProfile {
        val uid = requireNotNull(currentUid)
        firestore.collection("profiles").document(uid)
            .update(mapOf("avatarId" to avatarId, "updatedAt" to FieldValue.serverTimestamp())).await()
        return requireNotNull(loadMyProfile())
    }

    suspend fun submit(result: BattleResult): Int? {
        val uid = requireNotNull(currentUid) { "Debes iniciar sesión." }
        val profileRef = firestore.collection("profiles").document(uid)
        val boardRef = firestore.collection("rankingEntries").document("${uid}_${result.sessionId}")
        val submissionRef = firestore.collection("scoreSubmissions").document("${uid}_${result.sessionId}")
        val profile = profileRef.get().await()
        require(profile.exists()) { "Primero vincula tu identidad." }
        val section = profile.getString("section")?.takeIf { it.isNotBlank() }
            ?: throw IllegalStateException("Tu perfil no tiene aula asignada.")
        val publicName = profile.getString("publicName")?.takeIf { it.isNotBlank() } ?: "Participante"
        val avatarId = profile.getString("avatarId") ?: "ninja"
        // El ranking es la escritura principal. No debe cancelarse si falla el historial
        // auxiliar o la actualización de estadísticas del perfil.
        boardRef.set(mapOf(
            "uid" to uid, "publicName" to publicName,
            "section" to section, "avatarId" to avatarId,
            "bestScore" to result.score, "bestLevel" to result.level,
            "bestAccuracy" to result.accuracy, "durationMs" to result.durationMs,
            "startedAtMs" to result.startedAtMs, "endedAtMs" to result.endedAtMs,
            "achievedAt" to FieldValue.serverTimestamp(), "clientVersion" to BuildConfig.VERSION_NAME
        )).await()

        runCatching {
            submissionRef.set(mapOf(
                "uid" to uid, "score" to result.score, "level" to result.level,
                "correct" to result.correct, "wrong" to result.wrong, "accuracy" to result.accuracy,
                "bestStreak" to result.bestStreak, "durationMs" to result.durationMs,
                "startedAtMs" to result.startedAtMs, "endedAtMs" to result.endedAtMs,
                "sessionId" to result.sessionId, "clientVersion" to BuildConfig.VERSION_NAME,
                "createdAt" to FieldValue.serverTimestamp()
            )).await()
        }
        runCatching {
            val profileUpdates = mutableMapOf<String, Any>(
                "plays" to FieldValue.increment(1), "updatedAt" to FieldValue.serverTimestamp()
            )
            val currentBest = profile.getLong("bestScore")?.toInt() ?: -1
            val currentDuration = profile.getLong("bestDurationMs") ?: Long.MAX_VALUE
            val isBest = result.score > currentBest ||
                (result.score == currentBest && result.durationMs < currentDuration)
            if (isBest) profileUpdates.putAll(mapOf(
                "bestScore" to result.score, "bestLevel" to result.level,
                "bestAccuracy" to result.accuracy, "bestDurationMs" to result.durationMs,
                "bestStartedAtMs" to result.startedAtMs, "bestEndedAtMs" to result.endedAtMs
            ))
            profileRef.update(profileUpdates).await()
        }
        return runCatching {
            ranking(section).indexOfFirst { it.uid == uid }.takeIf { it >= 0 }?.plus(1)
        }.getOrNull()
    }

    suspend fun ranking(section: String): List<RankingEntry> = firestore.collection("rankingEntries")
        .whereEqualTo("section", section)
        .limit(500).get().await().documents.mapNotNull { it.toObject(RankingEntry::class.java) }
        .groupBy { it.uid }
        .mapNotNull { (_, attempts) -> attempts.minWithOrNull(compareByDescending<RankingEntry> { it.bestScore }.thenBy { it.durationMs }) }
        .sortedWith(compareByDescending<RankingEntry> { it.bestScore }.thenBy { it.durationMs })
        .take(100)

    suspend fun deleteRankingEntry(uid: String) {
        require(isAdmin) { "Solo el propietario puede administrar el ranking." }
        val docs = firestore.collection("rankingEntries").whereEqualTo("uid", uid).get().await().documents
        val batch = firestore.batch()
        docs.forEach { batch.delete(it.reference) }
        batch.commit().await()
    }

    suspend fun clearRanking(section: String) {
        require(isAdmin) { "Solo el propietario puede administrar el ranking." }
        val docs = firestore.collection("rankingEntries").whereEqualTo("section", section).get().await().documents
        docs.chunked(400).forEach { group ->
            val batch = firestore.batch()
            group.forEach { batch.delete(it.reference) }
            batch.commit().await()
        }
    }

    fun signOut() = auth.signOut()
}
