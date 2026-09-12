package pe.profejohnny.mathbattle.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.util.UUID
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import pe.profejohnny.mathbattle.data.MathBattleRepository
import pe.profejohnny.mathbattle.data.RosterChoice
import pe.profejohnny.mathbattle.game.GameEngine
import pe.profejohnny.mathbattle.game.MathQuestion
import pe.profejohnny.mathbattle.model.BattleResult
import pe.profejohnny.mathbattle.model.RankingEntry
import pe.profejohnny.mathbattle.model.StudentProfile

enum class Screen { BOOT, INTRO, SIGN_IN, SECTION, STUDENT, AVATAR, LOBBY, COUNTDOWN, GAME, LEVEL_UP, RESULT, RANKING }

data class GameState(
    val question: MathQuestion = GameEngine.question(),
    val score: Int = 0,
    val correct: Int = 0,
    val wrong: Int = 0,
    val streak: Int = 0,
    val bestStreak: Int = 0,
    val level: Int = 1,
    val remaining: Double = 10.0,
    val startedAt: Long = 0,
    val selectedChoice: String? = null,
    val lastCorrect: Boolean? = null,
    val sessionId: String = UUID.randomUUID().toString()
)

data class UiState(
    val screen: Screen = Screen.BOOT,
    val loading: Boolean = false,
    val message: String? = null,
    val firebaseReady: Boolean = true,
    val profile: StudentProfile? = null,
    val section: String = "2A",
    val roster: List<RosterChoice> = emptyList(),
    val ranking: List<RankingEntry> = emptyList(),
    val game: GameState = GameState(),
    val countdown: Int = 3,
    val countdownLabel: String = "UN RETADOR ENTRA A LA BATALLA",
    val sectionRank: Int? = null,
    val isAdmin: Boolean = false,
    val lastDurationMs: Long = 0,
    val lastEndedAtMs: Long = 0
)

class MathBattleViewModel(private val firebaseReady: Boolean) : ViewModel() {
    private val repository = if (firebaseReady) MathBattleRepository() else null
    private val _state = MutableStateFlow(UiState(firebaseReady = firebaseReady))
    val state: StateFlow<UiState> = _state.asStateFlow()
    private var timer: Job? = null

    fun enterBattle() { _state.value = _state.value.copy(screen = Screen.INTRO) }
    fun introFinished() {
        viewModelScope.launch {
            if (!firebaseReady) {
                _state.value = _state.value.copy(screen = Screen.SIGN_IN, message = "Falta conectar este APK con el proyecto Firebase.")
                return@launch
            }
            val profile = runCatching { repository?.loadMyProfile() }.getOrNull()
            val resolvedProfile = profile ?: if (repository?.isAdmin == true) adminProfile() else null
            _state.value = _state.value.copy(
                screen = if (resolvedProfile == null) Screen.SIGN_IN else Screen.LOBBY,
                profile = resolvedProfile,
                isAdmin = repository?.isAdmin == true
            )
        }
    }

    fun signedIn() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, message = null)
            val profile = runCatching { repository?.loadMyProfile() }.getOrNull()
            val resolvedProfile = profile ?: if (repository?.isAdmin == true) adminProfile() else null
            _state.value = _state.value.copy(
                loading = false,
                profile = resolvedProfile,
                isAdmin = repository?.isAdmin == true,
                screen = if (resolvedProfile == null) Screen.SECTION else Screen.LOBBY,
                message = if (resolvedProfile == null) "Cuenta Google verificada. Ahora elige tu aula." else null
            )
        }
    }

    fun authFailed(message: String) { _state.value = _state.value.copy(loading = false, message = message) }
    fun setLoading() { _state.value = _state.value.copy(loading = true, message = null) }

    fun chooseSection(section: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(section = section, roster = emptyList(), loading = true, message = null, screen = Screen.STUDENT)
            runCatching { requireNotNull(repository).listRoster(section) }
                .onSuccess { _state.value = _state.value.copy(roster = it, loading = false) }
                .onFailure { _state.value = _state.value.copy(loading = false, message = friendly(it)) }
        }
    }

    fun chooseStudent(studentId: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, message = null)
            runCatching { requireNotNull(repository).claimStudent(studentId) }
                .onSuccess { _state.value = _state.value.copy(profile = it, loading = false, screen = Screen.AVATAR) }
                .onFailure { _state.value = _state.value.copy(loading = false, message = friendly(it)) }
        }
    }

    fun chooseAvatar(avatarId: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, message = null)
            runCatching { requireNotNull(repository).updateAvatar(avatarId) }
                .onSuccess { _state.value = _state.value.copy(profile = it, loading = false, screen = Screen.LOBBY) }
                .onFailure { _state.value = _state.value.copy(loading = false, message = friendly(it)) }
        }
    }

    fun startBattle() {
        viewModelScope.launch {
            _state.value = _state.value.copy(screen = Screen.COUNTDOWN, countdown = 3, countdownLabel = "UN RETADOR ENTRA A LA BATALLA", sectionRank = null)
            for (n in 3 downTo 1) { _state.value = _state.value.copy(countdown = n); delay(800) }
            val initial = GameState(startedAt = System.currentTimeMillis())
            _state.value = _state.value.copy(screen = Screen.GAME, game = initial)
            startTimer()
        }
    }

    private fun startTimer() {
        timer?.cancel()
        var last = System.nanoTime()
        timer = viewModelScope.launch {
            while (isActive && _state.value.screen == Screen.GAME) {
                delay(50)
                val now = System.nanoTime()
                val elapsed = (now - last) / 1_000_000_000.0
                last = now
                val game = _state.value.game
                val left = (game.remaining - elapsed).coerceAtLeast(0.0)
                _state.value = _state.value.copy(game = game.copy(remaining = left))
                if (left <= 0.0) finishBattle()
            }
        }
    }

    fun answer(choice: String) {
        val current = _state.value
        if (current.screen != Screen.GAME || current.game.selectedChoice != null) return
        timer?.cancel()
        val game = current.game
        val correct = choice == game.question.answer
        val newScore = game.score + if (correct) 1 else 0
        val nextLevel = GameEngine.levelFor(newScore)
        val updated = game.copy(
            score = newScore,
            correct = game.correct + if (correct) 1 else 0,
            wrong = game.wrong + if (correct) 0 else 1,
            streak = if (correct) game.streak + 1 else 0,
            bestStreak = maxOf(game.bestStreak, if (correct) game.streak + 1 else 0),
            remaining = GameEngine.timeAfter(game.remaining, correct, game.level),
            selectedChoice = choice,
            lastCorrect = correct,
            level = nextLevel
        )
        _state.value = current.copy(game = updated)
        viewModelScope.launch {
            delay(if (correct) 280 else 450)
            if (updated.remaining <= 0) { finishBattle(); return@launch }
            if (correct && GameEngine.milestoneFor(newScore) != null) {
                _state.value = _state.value.copy(screen = Screen.LEVEL_UP)
            } else {
                _state.value = _state.value.copy(game = updated.copy(question = GameEngine.question(newScore), selectedChoice = null, lastCorrect = null))
                startTimer()
            }
        }
    }

    fun continueLevel() {
        timer?.cancel()
        viewModelScope.launch {
            val game = _state.value.game
            val milestone = GameEngine.milestoneFor(game.score) ?: return@launch
            _state.value = _state.value.copy(screen = Screen.COUNTDOWN, countdown = 3, countdownLabel = milestone.countdownLabel)
            for (n in 3 downTo 1) { _state.value = _state.value.copy(countdown = n); delay(800) }
            if (milestone.final) {
                finishBattle()
            } else {
                val cap = GameEngine.levels[game.level - 1].capSeconds
                _state.value = _state.value.copy(screen = Screen.GAME, game = game.copy(question = GameEngine.question(game.score), remaining = cap, selectedChoice = null, lastCorrect = null))
                startTimer()
            }
        }
    }

    fun finishBattle() {
        val current = _state.value
        if (current.screen !in listOf(Screen.GAME, Screen.LEVEL_UP, Screen.COUNTDOWN)) return
        timer?.cancel()
        val endedAt = System.currentTimeMillis()
        val duration = (endedAt - current.game.startedAt).coerceAtLeast(0)
        _state.value = current.copy(
            screen = Screen.RESULT,
            lastDurationMs = duration,
            lastEndedAtMs = endedAt
        )
        val g = current.game
        viewModelScope.launch {
            val result = BattleResult(
                g.score, g.level, g.correct, g.wrong, g.bestStreak,
                duration, g.startedAt, endedAt, g.sessionId
            )
            runCatching { repository?.submit(result) }.onSuccess { rank -> _state.value = _state.value.copy(sectionRank = rank) }
        }
    }

    fun showRanking(section: String = _state.value.profile?.section ?: _state.value.section) {
        viewModelScope.launch {
            _state.value = _state.value.copy(screen = Screen.RANKING, section = section, loading = true, message = null)
            runCatching { requireNotNull(repository).ranking(section) }
                .onSuccess { _state.value = _state.value.copy(ranking = it, loading = false) }
                .onFailure { _state.value = _state.value.copy(loading = false, message = friendly(it)) }
        }
    }

    fun goLobby() { timer?.cancel(); _state.value = _state.value.copy(screen = Screen.LOBBY, message = null) }
    fun deleteRankingEntry(uid: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, message = null)
            runCatching { requireNotNull(repository).deleteRankingEntry(uid) }
                .onSuccess { showRanking(_state.value.section) }
                .onFailure { _state.value = _state.value.copy(loading = false, message = friendly(it)) }
        }
    }
    fun clearRanking() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, message = null)
            runCatching { requireNotNull(repository).clearRanking(_state.value.section) }
                .onSuccess { showRanking(_state.value.section) }
                .onFailure { _state.value = _state.value.copy(loading = false, message = friendly(it)) }
        }
    }
    fun goSections() { _state.value = _state.value.copy(screen = Screen.SECTION, message = null) }
    fun signOut() { timer?.cancel(); repository?.signOut(); _state.value = UiState(screen = Screen.SIGN_IN, firebaseReady = firebaseReady) }
    fun clearMessage() { _state.value = _state.value.copy(message = null) }
    fun onAppPaused() { if (_state.value.screen == Screen.GAME) finishBattle() }

    private fun adminProfile() = StudentProfile(
        uid = repository?.currentUid.orEmpty(),
        publicName = "Profe Johnny",
        section = "2A",
        avatarId = "lightning"
    )

    private fun friendly(error: Throwable): String = when {
        error.message?.contains("email", true) == true -> "Ese nombre no corresponde al correo Google con el que ingresaste."
        error.message?.contains("claimed", true) == true -> "Ese estudiante ya tiene una cuenta vinculada."
        else -> "No se pudo completar la operación. Revisa Internet e inténtalo nuevamente."
    }
}

class MathBattleViewModelFactory(private val firebaseReady: Boolean) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = MathBattleViewModel(firebaseReady) as T
}
