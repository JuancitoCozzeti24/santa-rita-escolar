package pe.profejohnny.mathbattle.data

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.google.firebase.functions.FirebaseFunctions
import kotlinx.coroutines.tasks.await
import pe.profejohnny.mathbattle.BuildConfig
import pe.profejohnny.mathbattle.model.BattleResult
import pe.profejohnny.mathbattle.model.RankingEntry
import pe.profejohnny.mathbattle.model.StudentProfile

data class RosterChoice(val studentId: String, val publicName: String, val available: Boolean)

class MathBattleRepository(
    private val auth: FirebaseAuth = FirebaseAuth.getInstance(),
    private val functions: FirebaseFunctions = FirebaseFunctions.getInstance("us-central1"),
    private val firestore: FirebaseFirestore = FirebaseFirestore.getInstance()
) {
    val currentUid: String? get() = auth.currentUser?.uid
    val currentEmail: String? get() = auth.currentUser?.email

    suspend fun loadMyProfile(): StudentProfile? {
        val uid = currentUid ?: return null
        return firestore.collection("profiles").document(uid).get().await().toObject(StudentProfile::class.java)
    }

    suspend fun listRoster(section: String): List<RosterChoice> {
        val result = functions.getHttpsCallable("listRoster").call(mapOf("section" to section)).await().data
        @Suppress("UNCHECKED_CAST") val rows = (result as? Map<*, *>)?.get("students") as? List<Map<String, Any?>> ?: emptyList()
        return rows.mapNotNull {
            val id = it["studentId"] as? String ?: return@mapNotNull null
            RosterChoice(id, it["publicName"] as? String ?: "Estudiante", it["available"] as? Boolean ?: false)
        }
    }

    suspend fun claimStudent(studentId: String): StudentProfile {
        functions.getHttpsCallable("claimStudent").call(mapOf("studentId" to studentId)).await()
        return requireNotNull(loadMyProfile()) { "No se creó el perfil" }
    }

    suspend fun updateAvatar(avatarId: String): StudentProfile {
        functions.getHttpsCallable("updateAvatar").call(mapOf("avatarId" to avatarId)).await()
        return requireNotNull(loadMyProfile())
    }

    suspend fun submit(result: BattleResult): Int? {
        val data = functions.getHttpsCallable("submitScore").call(
            mapOf(
                "score" to result.score,
                "level" to result.level,
                "correct" to result.correct,
                "wrong" to result.wrong,
                "accuracy" to result.accuracy,
                "bestStreak" to result.bestStreak,
                "durationMs" to result.durationMs,
                "sessionId" to result.sessionId,
                "clientVersion" to BuildConfig.VERSION_NAME
            )
        ).await().data
        return ((data as? Map<*, *>)?.get("sectionRank") as? Number)?.toInt()
    }

    suspend fun ranking(section: String): List<RankingEntry> = firestore.collection("leaderboard")
        .whereEqualTo("section", section)
        .orderBy("bestScore", Query.Direction.DESCENDING)
        .orderBy("achievedAt", Query.Direction.ASCENDING)
        .limit(100)
        .get().await().documents.mapNotNull { it.toObject(RankingEntry::class.java) }

    fun signOut() = auth.signOut()
}
