package pe.profejohnny.mathbattle.model

data class StudentProfile(
    val uid: String = "",
    val rosterId: String = "",
    val publicName: String = "",
    val section: String = "",
    val avatarId: String = "ninja",
    val bestScore: Int = 0,
    val bestLevel: Int = 1,
    val bestAccuracy: Int = 0,
    val plays: Int = 0
)

data class RankingEntry(
    val uid: String = "",
    val publicName: String = "",
    val section: String = "",
    val avatarId: String = "ninja",
    val bestScore: Int = 0,
    val bestLevel: Int = 1,
    val bestAccuracy: Int = 0,
    val durationMs: Long = 0,
    val startedAtMs: Long = 0,
    val endedAtMs: Long = 0
)

data class BattleResult(
    val score: Int,
    val level: Int,
    val correct: Int,
    val wrong: Int,
    val bestStreak: Int,
    val durationMs: Long,
    val startedAtMs: Long,
    val endedAtMs: Long,
    val sessionId: String
) {
    val accuracy: Int get() = (correct * 100 / (correct + wrong).coerceAtLeast(1))
}

val BattleAvatars = listOf(
    "ninja" to "🥷🏻", "singer_boy" to "🧑🏻‍🎤", "singer_girl" to "👩🏻‍🎤",
    "astronaut_boy" to "🧑🏻‍🚀", "astronaut_girl" to "👩🏻‍🚀", "hero" to "🦸🏻",
    "heroine" to "🦸🏻‍♀️", "fighter" to "🥊", "martial" to "🥋", "dragon" to "🐉",
    "lightning" to "⚡", "tiger" to "🐯", "wolf" to "🐺", "lion" to "🦁", "eagle" to "🦅"
)

fun avatarGlyph(id: String) = BattleAvatars.firstOrNull { it.first == id }?.second ?: "⚡"
