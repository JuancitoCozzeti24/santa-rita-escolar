package pe.profejohnny.mathbattle.ui

import android.app.Activity
import android.media.MediaPlayer
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import pe.profejohnny.mathbattle.R
import pe.profejohnny.mathbattle.auth.GoogleAuthManager
import pe.profejohnny.mathbattle.game.GameEngine
import pe.profejohnny.mathbattle.model.BattleAvatars
import pe.profejohnny.mathbattle.model.StudentProfile
import pe.profejohnny.mathbattle.model.avatarGlyph

private val Ink = Color(0xFF0B0D14)
private val Panel = Color(0xFF1A1D2B)
private val Panel2 = Color(0xFF242737)
private val Lime = Color(0xFFB5F75B)
private val Purple = Color(0xFFA982E8)
private val Muted = Color(0xFF9AA0B5)
private val Red = Color(0xFFFF607D)

@Composable
fun MathBattleApp(viewModel: MathBattleViewModel) {
    val state by viewModel.state.collectAsState()
    BattleAudio(state)
    MaterialTheme(colorScheme = darkColorScheme(primary = Lime, secondary = Purple, background = Ink, surface = Panel)) {
        Surface(Modifier.fillMaxSize(), color = Ink) {
            when (state.screen) {
                Screen.BOOT -> BootScreen(viewModel::enterBattle)
                Screen.INTRO -> IntroScreen(viewModel::introFinished)
                Screen.SIGN_IN -> SignInScreen(state, viewModel)
                Screen.SECTION -> SectionScreen(state, viewModel)
                Screen.STUDENT -> StudentScreen(state, viewModel)
                Screen.AVATAR -> AvatarScreen(state, viewModel)
                Screen.LOBBY -> LobbyScreen(state, viewModel)
                Screen.COUNTDOWN -> CountdownScreen(state)
                Screen.GAME -> GameScreen(state, viewModel)
                Screen.LEVEL_UP -> LevelUpScreen(state, viewModel)
                Screen.RESULT -> ResultScreen(state, viewModel)
                Screen.RANKING -> RankingScreen(state, viewModel)
            }
            if (state.loading) LoadingOverlay()
        }
    }
}

@Composable
private fun BootScreen(onEnter: () -> Unit) {
    val activity = LocalContext.current as? Activity
    val context = LocalContext.current
    BoxWithConstraints(
        Modifier.fillMaxSize().background(
            Brush.radialGradient(listOf(Color(0xFF321B3D), Ink), radius = 1100f)
        ).padding(horizontal = if (maxWidth > 900.dp) 72.dp else 32.dp, vertical = 24.dp)
    ) {
        val titleSize = if (maxWidth > 900.dp) 72.sp else 48.sp
        val actionWidth = if (maxWidth > 900.dp) .68f else .82f
        Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
            Eyebrow("MATH BATTLE")
            Text("DEMUESTRA QUE\nPUEDES LUCHAR!!", color = Color.White, fontSize = titleSize, lineHeight = titleSize, fontWeight = FontWeight.Black, textAlign = TextAlign.Center)
            Text("¿O te quedarás ahí demostrando qué serás en el futuro?", color = Muted, fontSize = if (maxWidth > 900.dp) 22.sp else 16.sp, modifier = Modifier.padding(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(22.dp), modifier = Modifier.fillMaxWidth(actionWidth).padding(top = 18.dp)) {
                ImageAction(R.drawable.enter_battle, "Entraré a la batalla", Modifier.weight(1f)) {
                    MediaPlayer.create(context, R.raw.evil_laugh)?.apply {
                        setOnCompletionListener { it.release() }
                        start()
                    }
                    onEnter()
                }
                ImageAction(R.drawable.leave_battle, "Tengo miedo, me voy", Modifier.weight(1f)) { activity?.finish() }
            }
        }
    }
}

@Composable
private fun ImageAction(resource: Int, label: String, modifier: Modifier = Modifier, action: () -> Unit) {
    Image(painterResource(resource), label, modifier.clickable(onClick = action), contentScale = ContentScale.FillWidth)
}

@Composable
private fun IntroScreen(onFinished: () -> Unit) {
    val context = LocalContext.current
    val player = remember {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(Uri.parse("android.resource://${context.packageName}/${R.raw.intro}")))
            prepare(); playWhenReady = true
            addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_ENDED) onFinished() }
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) = onFinished()
            })
        }
    }
    DisposableEffect(Unit) { onDispose { player.release() } }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(factory = { PlayerView(it).apply { useController = false; this.player = player } }, modifier = Modifier.fillMaxSize())
        OutlinedButton(onClick = onFinished, modifier = Modifier.align(Alignment.TopEnd).padding(20.dp)) { Text("Saltar intro") }
    }
}

@Composable
private fun SignInScreen(state: UiState, viewModel: MathBattleViewModel) {
    val context = LocalContext.current
    val activity = context as Activity
    val scope = rememberCoroutineScope()
    CenterCard {
        Eyebrow("IDENTIDAD SEGURA")
        Text("Entra con Google", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Black)
        Text("Usa tu cuenta institucional. Tu correo solo sirve para comprobar tu identidad y nunca aparecerá en el ranking.", color = Muted, textAlign = TextAlign.Center)
        Spacer(Modifier.height(18.dp))
        if (!state.firebaseReady) {
            Message("Compilación de estructura: Firebase todavía no tiene credenciales asignadas.")
        } else {
            Button(onClick = {
                viewModel.setLoading()
                scope.launch {
                    GoogleAuthManager(activity).signIn()
                        .onSuccess { viewModel.signedIn() }
                        .onFailure { viewModel.authFailed("No se pudo iniciar sesión con Google. Inténtalo nuevamente.") }
                }
            }) { Text("CONTINUAR CON GOOGLE", fontWeight = FontWeight.Bold) }
        }
        state.message?.let { Message(it) }
    }
}

@Composable
private fun SectionScreen(state: UiState, viewModel: MathBattleViewModel) {
    CenterCard {
        Eyebrow("CUENTA GOOGLE VERIFICADA")
        Text("¿A qué aula perteneces?", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Black)
        Text("Selecciona tu grado y sección.", color = Muted)
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), modifier = Modifier.padding(top = 20.dp)) {
            listOf("2A", "2B", "5A", "5B").forEach { section ->
                BattleButton(section.replace("A", ".º A").replace("B", ".º B")) { viewModel.chooseSection(section) }
            }
        }
        state.message?.let { Message(it) }
    }
}

@Composable
private fun StudentScreen(state: UiState, viewModel: MathBattleViewModel) {
    BackHandler { viewModel.goSections() }
    Column(Modifier.fillMaxSize().padding(34.dp)) {
        Eyebrow("${state.section.first()}.º ${state.section.last()} · LISTA OFICIAL")
        Text("Elige tu nombre", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Black)
        Text("La app comprobará que el nombre corresponda al correo Google con el que ingresaste.", color = Muted)
        state.message?.let { Message(it) }
        LazyColumn(Modifier.fillMaxWidth().weight(1f).padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            items(state.roster, key = { it.studentId }) { student ->
                OutlinedButton(
                    onClick = { viewModel.chooseStudent(student.studentId) }, enabled = student.available,
                    modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(12.dp)
                ) {
                    Text(student.publicName, Modifier.weight(1f), textAlign = TextAlign.Start)
                    Text(if (student.available) "DISPONIBLE" else "VINCULADO", color = if (student.available) Lime else Muted, fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun AvatarScreen(state: UiState, viewModel: MathBattleViewModel) {
    CenterCard(width = 760.dp) {
        Eyebrow("ÚLTIMO PASO")
        Text("Elige tu avatar", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Black)
        Text("Este personaje será visible junto a ${state.profile?.publicName.orEmpty()} en el ranking.", color = Muted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 22.dp)) {
            BattleAvatars.forEach { (id, glyph) ->
                Box(Modifier.size(68.dp).clip(RoundedCornerShape(18.dp)).background(Panel2).border(1.dp, Purple.copy(alpha = .35f), RoundedCornerShape(18.dp)).clickable { viewModel.chooseAvatar(id) }, contentAlignment = Alignment.Center) {
                    Text(glyph, fontSize = 36.sp)
                }
            }
        }
        state.message?.let { Message(it) }
    }
}

@Composable
private fun LobbyScreen(state: UiState, viewModel: MathBattleViewModel) {
    val profile = state.profile ?: return
    Row(Modifier.fillMaxSize().padding(32.dp), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
        Box(Modifier.weight(1.35f).fillMaxHeight().clip(RoundedCornerShape(24.dp)).background(Brush.horizontalGradient(listOf(Color(0xFF312345), Color(0xFF171523))))) {
            Image(painterResource(R.drawable.rival), null, Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(.56f), contentScale = ContentScale.Crop)
            Column(Modifier.fillMaxHeight().padding(34.dp), verticalArrangement = Arrangement.Center) {
                Eyebrow("CÁLCULO MENTAL · CONTRARRELOJ")
                Text("TU MENTE.\nTU MEJOR\n", color = Color.White, fontSize = 50.sp, lineHeight = 47.sp, fontWeight = FontWeight.Black)
                Text("BATALLA.", color = Lime, fontSize = 50.sp, lineHeight = 47.sp, fontWeight = FontWeight.Black)
                Text("Tres respuestas. Una oportunidad.\n¿Hasta dónde puedes llegar?", color = Muted, modifier = Modifier.padding(vertical = 15.dp))
                Button(onClick = viewModel::startBattle) { Text("¡A LA BATALLA!  ↗", fontWeight = FontWeight.Black) }
            }
        }
        Column(Modifier.weight(.8f).fillMaxHeight().clip(RoundedCornerShape(24.dp)).background(Panel).padding(26.dp)) {
            Text(avatarGlyph(profile.avatarId), fontSize = 54.sp)
            Text(profile.publicName, fontSize = 30.sp, fontWeight = FontWeight.Black)
            Text("${profile.section} · ${profile.bestScore} pts", color = Lime)
            Spacer(Modifier.height(22.dp))
            Button(onClick = { viewModel.showRanking() }, modifier = Modifier.fillMaxWidth()) { Text("🏆 VER RANKING") }
            OutlinedButton(onClick = { viewModel.goSections() }, modifier = Modifier.fillMaxWidth()) { Text("CAMBIAR AULA") }
            OutlinedButton(onClick = viewModel::signOut, modifier = Modifier.fillMaxWidth()) { Text("CERRAR SESIÓN") }
            Spacer(Modifier.weight(1f))
            Text("NIVEL 01  Sumas y restas\nNIVEL 02  Potencias de 2\nNIVEL 03  Operaciones combinadas", color = Muted, lineHeight = 24.sp)
        }
    }
}

@Composable
private fun CountdownScreen(state: UiState) {
    CenterCard {
        Eyebrow("UN RETADOR ENTRA A LA BATALLA")
        Text(avatarGlyph(state.profile?.avatarId.orEmpty()), fontSize = 68.sp)
        Text("¡Bienvenido, ${state.profile?.publicName.orEmpty()}!", fontSize = 34.sp, fontWeight = FontWeight.Black)
        Text(state.countdown.toString(), color = Lime, fontSize = 112.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun GameScreen(state: UiState, viewModel: MathBattleViewModel) {
    val game = state.game
    val rule = GameEngine.levels[game.level - 1]
    val danger = game.remaining < rule.capSeconds * .3
    val pulse = rememberInfiniteTransition(label = "neonTimer").animateFloat(
        initialValue = .35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(280), RepeatMode.Reverse),
        label = "dangerPulse"
    ).value
    BackHandler { viewModel.finishBattle() }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val wide = maxWidth > 900.dp
        val horizontalPadding = if (wide) 64.dp else 30.dp
        val answerHeight = if (wide) (maxHeight * .27f).coerceAtMost(190.dp) else 118.dp
        Column(Modifier.fillMaxSize().padding(horizontal = horizontalPadding, vertical = 18.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(avatarGlyph(state.profile?.avatarId.orEmpty()), fontSize = if (wide) 48.sp else 36.sp)
                Text(state.profile?.publicName.orEmpty(), fontSize = if (wide) 22.sp else 16.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 10.dp).weight(1f))
                Column(horizontalAlignment = Alignment.CenterHorizontally) { Eyebrow("NIVEL ${game.level}${if (game.level == 3) " · ∞" else ""}"); Text(rule.name, fontSize = if (wide) 22.sp else 16.sp, fontWeight = FontWeight.Bold) }
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.End) { Eyebrow("PUNTOS"); Text(game.score.toString(), color = Lime, fontSize = if (wide) 64.sp else 48.sp, fontWeight = FontWeight.Black) }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("TIEMPO RESTANTE", color = if (danger) Red.copy(alpha = pulse) else Muted, fontSize = 11.sp, modifier = Modifier.weight(1f))
                Text("%.1f s".format(game.remaining), color = if (danger) Red.copy(alpha = pulse) else Color.White, fontSize = if (wide) 22.sp else 16.sp, fontWeight = FontWeight.Bold)
            }
            Box(
                Modifier.fillMaxWidth().height(if (wide) 18.dp else 13.dp)
                    .shadow(if (danger) (18.dp * pulse) else 4.dp, CircleShape, ambientColor = if (danger) Red else Lime, spotColor = if (danger) Red else Lime)
                    .clip(CircleShape).background(if (danger) Red.copy(alpha = .18f + .28f * pulse) else Panel2)
            ) {
                Box(
                    Modifier.fillMaxWidth((game.remaining / rule.capSeconds).toFloat().coerceIn(0f, 1f))
                        .fillMaxHeight()
                        .background(
                            Brush.horizontalGradient(
                                if (danger) listOf(Color(0xFFFF1744), Color.White.copy(alpha = pulse), Color(0xFFFF1744))
                                else listOf(Color(0xFF67FF54), Lime, Color.White)
                            )
                        )
                )
            }
            Column(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                Eyebrow(rule.skill.uppercase())
                Text(game.question.text, fontSize = if (wide) 96.sp else 72.sp, fontWeight = FontWeight.Black)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(if (wide) 34.dp else 16.dp)) {
                game.question.choices.forEachIndexed { index, choice ->
                    ArcadeAnswerButton(
                        choice = choice,
                        shortcut = index + 1,
                        selectedChoice = game.selectedChoice,
                        correctChoice = game.question.answer,
                        modifier = Modifier.weight(1f).height(answerHeight)
                    ) { viewModel.answer(choice) }
                }
            }
            Row(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("✓ +${rule.gainSeconds} s  ·  ✕ −${rule.lossSeconds} s", color = Muted)
                Text(if (game.streak >= 3) "⚡ ${game.streak} aciertos seguidos" else "⚡ Cada acierto cuenta", color = Purple)
                Text("Terminar partida", color = Purple, modifier = Modifier.clickable { viewModel.finishBattle() })
            }
        }
    }
}

@Composable
private fun ArcadeAnswerButton(
    choice: Int,
    shortcut: Int,
    selectedChoice: Int?,
    correctChoice: Int,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val revealed = selectedChoice != null
    val correct = revealed && choice == correctChoice
    val wrong = revealed && selectedChoice == choice && choice != correctChoice
    val topColor by animateColorAsState(
        when {
            correct -> Color.White
            wrong -> Color(0xFFFF1744)
            revealed -> Color(0xFF264130)
            else -> Color(0xFF16E650)
        },
        tween(160),
        label = "arcadeColor"
    )
    val glow by animateFloatAsState(if (correct || wrong) 1f else if (pressed) .7f else .18f, tween(120), label = "arcadeGlow")
    val travel by animateDpAsState(if (pressed) 10.dp else 1.dp, tween(70), label = "arcadeTravel")
    Box(modifier, contentAlignment = Alignment.Center) {
        Box(
            Modifier.fillMaxHeight(.88f).aspectRatio(1f)
                .shadow(22.dp * glow, CircleShape, ambientColor = if (wrong) Red else Color.White, spotColor = if (wrong) Red else Lime)
                .clip(CircleShape)
                .background(Color(0xFF063B1B))
                .border(4.dp, Color(0xFF061B10), CircleShape)
        )
        Box(
            Modifier.fillMaxHeight(.78f).aspectRatio(1f)
                .graphicsLayer { translationY = travel.toPx(); scaleX = if (pressed) .96f else 1f; scaleY = if (pressed) .96f else 1f }
                .shadow(12.dp, CircleShape)
                .clip(CircleShape)
                .background(Brush.radialGradient(listOf(topColor.copy(alpha = 1f), topColor.copy(alpha = .68f), Color(0xFF054C20))))
                .border(3.dp, if (correct) Color.White else topColor.copy(alpha = .9f), CircleShape)
                .clickable(interactionSource = interaction, indication = null, enabled = selectedChoice == null, onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            Text(choice.toString(), color = if (correct) Ink else Color.White, fontSize = 48.sp, fontWeight = FontWeight.Black)
            Text(shortcut.toString(), color = Color.White.copy(alpha = .7f), fontSize = 11.sp, modifier = Modifier.align(Alignment.TopStart).padding(13.dp))
            Box(Modifier.align(Alignment.TopStart).padding(18.dp).size(22.dp).clip(CircleShape).background(Color.White.copy(alpha = .42f)))
        }
    }
}

@Composable
private fun LevelUpScreen(state: UiState, viewModel: MathBattleViewModel) {
    val level = state.game.level
    val rule = GameEngine.levels[level - 1]
    CenterCard {
        Image(painterResource(R.drawable.rival), null, Modifier.size(170.dp).clip(CircleShape), contentScale = ContentScale.Crop)
        Eyebrow("NIVEL ${level - 1} SUPERADO")
        Text(rule.name, fontSize = 46.sp, fontWeight = FontWeight.Black)
        Text(if (level == 2) "Has vencido al nivel uno. Ahora empieza el verdadero desafío." else "Has llegado a la batalla infinita. ¿Cuántos puntos podrás conseguir?", color = Muted)
        BattleButton("¡ESTOY LISTO! ↗", viewModel::continueLevel)
    }
}

@Composable
private fun ResultScreen(state: UiState, viewModel: MathBattleViewModel) {
    val g = state.game
    val accuracy = g.correct * 100 / (g.correct + g.wrong).coerceAtLeast(1)
    CenterCard(width = 760.dp) {
        Eyebrow("BATALLA COMPLETADA")
        Text("¡Buena batalla, ${state.profile?.publicName.orEmpty()}!", fontSize = 36.sp, fontWeight = FontWeight.Black, textAlign = TextAlign.Center)
        Text(g.score.toString(), color = Lime, fontSize = 105.sp, fontWeight = FontWeight.Black)
        Text("PUNTOS", color = Muted, letterSpacing = 3.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(40.dp)) {
            ResultStat(g.level.toString(), "NIVEL")
            ResultStat("$accuracy%", "PRECISIÓN")
            ResultStat(g.bestStreak.toString(), "MEJOR RACHA")
        }
        Text(
            "${formatDuration(state.lastDurationMs)} · ${formatClock(g.startedAt)}–${formatClock(state.lastEndedAtMs)}",
            color = Muted
        )
        Text(state.sectionRank?.let { "Puesto en tu sección: $it" } ?: "Guardando posición…", color = Purple)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            BattleButton("¡UNA MÁS!", viewModel::startBattle)
            OutlinedButton(onClick = viewModel::goLobby) { Text("VOLVER") }
            OutlinedButton(onClick = { viewModel.showRanking() }) { Text("🏆 RANKING") }
        }
    }
}

@Composable private fun ResultStat(value: String, label: String) { Column(horizontalAlignment = Alignment.CenterHorizontally) { Text(value, color = Lime, fontSize = 30.sp, fontWeight = FontWeight.Black); Text(label, color = Muted, fontSize = 10.sp) } }

@Composable
private fun RankingScreen(state: UiState, viewModel: MathBattleViewModel) {
    var pendingDelete by remember { mutableStateOf<String?>(null) }
    var confirmClear by remember { mutableStateOf(false) }
    BackHandler { viewModel.goLobby() }
    Column(Modifier.fillMaxSize().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Eyebrow("CLASIFICACIÓN ONLINE")
        Text("Ranking en vivo", fontSize = 42.sp, fontWeight = FontWeight.Black)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(12.dp)) { listOf("2A", "2B", "5A", "5B").forEach { section -> OutlinedButton(onClick = { viewModel.showRanking(section) }, colors = ButtonDefaults.outlinedButtonColors(contentColor = if (section == state.section) Lime else Color.White)) { Text(section) } } }
        if (state.isAdmin) {
            OutlinedButton(onClick = { confirmClear = true }, colors = ButtonDefaults.outlinedButtonColors(contentColor = Red)) {
                Text("REINICIAR RANKING ${state.section}")
            }
        }
        state.message?.let { Message(it) }
        LazyColumn(Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(18.dp)).background(Panel).padding(12.dp)) {
            items(state.ranking) { entry ->
                Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${state.ranking.indexOf(entry) + 1}", color = Muted, modifier = Modifier.width(40.dp))
                    Text(avatarGlyph(entry.avatarId), fontSize = 30.sp)
                    Column(Modifier.padding(start = 12.dp).weight(1f)) {
                        Text(entry.publicName, fontWeight = FontWeight.Bold)
                        Text(
                            "${entry.section} · ${formatDuration(entry.durationMs)} · ${formatDateTime(entry.startedAtMs)}–${formatClock(entry.endedAtMs)}",
                            color = Muted,
                            fontSize = 11.sp
                        )
                    }
                    Text("${entry.bestScore} pts", color = Lime, fontSize = 25.sp, fontWeight = FontWeight.Black)
                    if (state.isAdmin) {
                        TextButton(onClick = { pendingDelete = entry.uid }) { Text("ELIMINAR", color = Red) }
                    }
                }
            }
        }
        OutlinedButton(onClick = viewModel::goLobby, modifier = Modifier.padding(top = 10.dp)) { Text("VOLVER AL JUEGO") }
    }
    pendingDelete?.let { uid ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Eliminar participante") },
            text = { Text("Se eliminará este resultado del ranking ${state.section}.") },
            confirmButton = {
                TextButton(onClick = { pendingDelete = null; viewModel.deleteRankingEntry(uid) }) {
                    Text("ELIMINAR", color = Red)
                }
            },
            dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("CANCELAR") } }
        )
    }
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text("Reiniciar ranking ${state.section}") },
            text = { Text("Se borrarán todos los resultados visibles de esta aula. Los estudiantes podrán volver a jugar y aparecer nuevamente.") },
            confirmButton = {
                TextButton(onClick = { confirmClear = false; viewModel.clearRanking() }) {
                    Text("REINICIAR", color = Red)
                }
            },
            dismissButton = { TextButton(onClick = { confirmClear = false }) { Text("CANCELAR") } }
        )
    }
}

private fun formatDuration(milliseconds: Long): String {
    val totalSeconds = (milliseconds.coerceAtLeast(0) + 500) / 1000
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return if (minutes == 0L) "${seconds} s" else "${minutes} min ${seconds.toString().padStart(2, '0')} s"
}

private fun formatClock(milliseconds: Long): String =
    if (milliseconds <= 0) "--:--:--" else SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(milliseconds))

private fun formatDateTime(milliseconds: Long): String =
    if (milliseconds <= 0) "--/-- --:--:--" else SimpleDateFormat("dd/MM HH:mm:ss", Locale.getDefault()).format(Date(milliseconds))

@Suppress("UNUSED_PARAMETER")
@Composable private fun CenterCard(width: androidx.compose.ui.unit.Dp = 620.dp, content: @Composable ColumnScope.() -> Unit) {
    BoxWithConstraints(
        Modifier.fillMaxSize().background(Brush.radialGradient(listOf(Color(0xFF29203C), Ink), radius = 1600f)),
        contentAlignment = Alignment.Center
    ) {
        val tablet = maxWidth >= 700.dp
        val outerHorizontal = if (tablet) 44.dp else 16.dp
        val outerVertical = if (maxHeight >= 650.dp) 30.dp else 10.dp
        val innerPadding = if (tablet) 42.dp else 24.dp
        Column(
            Modifier.fillMaxSize()
                .padding(horizontal = outerHorizontal, vertical = outerVertical)
                .clip(RoundedCornerShape(if (tablet) 30.dp else 22.dp))
                .background(Panel.copy(alpha = .94f))
                .border(1.dp, Purple.copy(alpha = .35f), RoundedCornerShape(if (tablet) 30.dp else 22.dp))
                .padding(innerPadding),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(if (tablet) 14.dp else 9.dp, Alignment.CenterVertically),
            content = content
        )
    }
}

@Composable private fun ColumnScope.Message(text: String) { Text(text, color = Red, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 10.dp)) }
@Composable private fun Eyebrow(text: String) { Text(text, color = Purple, fontSize = 11.sp, fontWeight = FontWeight.Black, letterSpacing = 2.sp) }
@Composable private fun BattleButton(text: String, action: () -> Unit) { Button(onClick = action, colors = ButtonDefaults.buttonColors(containerColor = Lime, contentColor = Ink), shape = RoundedCornerShape(12.dp)) { Text(text, fontWeight = FontWeight.Black) } }
@Composable private fun LoadingOverlay() { Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .55f)), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Lime) } }

@Composable
private fun BattleAudio(state: UiState) {
    val context = LocalContext.current
    DisposableEffect(state.screen) {
        val music = if (state.screen == Screen.GAME) MediaPlayer.create(context, R.raw.suspenso_10min)?.apply {
            isLooping = true
            setVolume(.22f, .22f)
            start()
        } else null
        onDispose { music?.stop(); music?.release() }
    }
    LaunchedEffect(state.game.selectedChoice) {
        val selected = state.game.selectedChoice ?: return@LaunchedEffect
        val sound = if (selected == state.game.question.answer) R.raw.buena else R.raw.no
        MediaPlayer.create(context, sound)?.apply {
            setOnCompletionListener { it.release() }
            start()
        }
    }
}
