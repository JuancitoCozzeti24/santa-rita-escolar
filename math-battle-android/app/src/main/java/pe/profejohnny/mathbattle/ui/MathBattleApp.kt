package pe.profejohnny.mathbattle.ui

import android.app.Activity
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.ToneGenerator
import android.net.Uri
import android.speech.tts.TextToSpeech
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.material3.Typography
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
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.TimeoutCancellationException
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
private val ElectricBlue = Color(0xFF8EFFF6)
private val BattleDisplayFont = FontFamily(Font(R.font.barlow_condensed_bold, FontWeight.Bold))
private val BattleBodyFont = FontFamily(Font(R.font.manrope))
private val baseTypography = Typography()
private val BattleTypography = baseTypography.copy(
    displayLarge = baseTypography.displayLarge.copy(fontFamily = BattleDisplayFont),
    displayMedium = baseTypography.displayMedium.copy(fontFamily = BattleDisplayFont),
    displaySmall = baseTypography.displaySmall.copy(fontFamily = BattleDisplayFont),
    headlineLarge = baseTypography.headlineLarge.copy(fontFamily = BattleDisplayFont),
    headlineMedium = baseTypography.headlineMedium.copy(fontFamily = BattleDisplayFont),
    headlineSmall = baseTypography.headlineSmall.copy(fontFamily = BattleDisplayFont),
    titleLarge = baseTypography.titleLarge.copy(fontFamily = BattleDisplayFont),
    titleMedium = baseTypography.titleMedium.copy(fontFamily = BattleBodyFont),
    titleSmall = baseTypography.titleSmall.copy(fontFamily = BattleBodyFont),
    bodyLarge = baseTypography.bodyLarge.copy(fontFamily = BattleBodyFont),
    bodyMedium = baseTypography.bodyMedium.copy(fontFamily = BattleBodyFont),
    bodySmall = baseTypography.bodySmall.copy(fontFamily = BattleBodyFont),
    labelLarge = baseTypography.labelLarge.copy(fontFamily = BattleBodyFont),
    labelMedium = baseTypography.labelMedium.copy(fontFamily = BattleBodyFont),
    labelSmall = baseTypography.labelSmall.copy(fontFamily = BattleBodyFont)
)

@Composable
fun MathBattleApp(viewModel: MathBattleViewModel) {
    val state by viewModel.state.collectAsState()
    BattleAudio(state)
    MaterialTheme(colorScheme = darkColorScheme(primary = Lime, secondary = Purple, background = Ink, surface = Panel), typography = BattleTypography) {
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
    val flicker = rememberInfiniteTransition(label = "neonTitle").animateFloat(
        initialValue = .58f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(170), RepeatMode.Reverse),
        label = "neonFlicker"
    ).value
    val electricity = remember { ToneGenerator(AudioManager.STREAM_MUSIC, 16) }
    DisposableEffect(Unit) { onDispose { electricity.release() } }
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(2100)
            electricity.startTone(ToneGenerator.TONE_PROP_BEEP2, 55)
            kotlinx.coroutines.delay(95)
            electricity.startTone(ToneGenerator.TONE_PROP_BEEP, 35)
        }
    }
    BoxWithConstraints(
        Modifier.fillMaxSize().background(
            Brush.radialGradient(listOf(Color(0xFF321B3D), Ink), radius = 1100f)
        )
    ) {
        val screenWidth = maxWidth
        val screenHeight = maxHeight
        val short = screenHeight < 500.dp
        val portrait = screenHeight > screenWidth
        val phone = screenWidth < 700.dp
        val titleSize = when {
            short -> 31.sp
            portrait -> 30.sp
            phone -> 34.sp
            screenWidth > 1400.dp -> 58.sp
            else -> 46.sp
        }
        val actionWidth = if (screenWidth > 1100.dp) .62f else if (phone) .94f else .78f
        ElectricSparks(flicker, Modifier.fillMaxSize())
        Column(
            Modifier.align(Alignment.Center).fillMaxWidth().padding(horizontal = if (short) 14.dp else 26.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(if (short) 3.dp else 8.dp)
        ) {
            Eyebrow("MATH BATTLE")
            Text(
                "DEMUESTRA QUE PUEDES LUCHAR",
                color = ElectricBlue.copy(alpha = .78f + .22f * flicker),
                fontFamily = BattleDisplayFont,
                fontSize = titleSize,
                lineHeight = titleSize,
                fontWeight = FontWeight.Bold,
                maxLines = if (portrait) 2 else 1,
                textAlign = TextAlign.Center,
                style = TextStyle(shadow = Shadow(ElectricBlue.copy(alpha = flicker), Offset.Zero, 18f + 16f * flicker))
            )
            Text(
                "¿O te quedarás ahí demostrando qué serás en el futuro?",
                color = Color.White.copy(alpha = .76f),
                fontSize = if (short) 10.sp else if (screenWidth > 900.dp) 15.sp else 12.sp,
                maxLines = 1,
                modifier = Modifier.padding(vertical = if (short) 2.dp else 6.dp)
            )
            Row(horizontalArrangement = Arrangement.spacedBy(if (short) 10.dp else 18.dp), modifier = Modifier.fillMaxWidth(actionWidth)) {
                ImageAction(R.drawable.enter_battle, "Entraré a la batalla", Modifier.weight(1f), if (short) 88.dp else 150.dp) {
                    MediaPlayer.create(context, R.raw.evil_laugh)?.apply {
                        setOnCompletionListener { it.release() }
                        start()
                    }
                    onEnter()
                }
                ImageAction(R.drawable.leave_battle, "Tengo miedo, me voy", Modifier.weight(1f), if (short) 88.dp else 150.dp) { activity?.finish() }
            }
        }
    }
}

@Composable
private fun ElectricSparks(intensity: Float, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val sparks = listOf(.10f to .24f, .18f to .72f, .32f to .14f, .65f to .18f, .82f to .68f, .91f to .31f)
        sparks.forEachIndexed { index, (x, y) ->
            val start = Offset(size.width * x, size.height * y)
            val direction = if (index % 2 == 0) 1f else -1f
            drawLine(ElectricBlue.copy(alpha = (.12f + .38f * intensity)), start, start + Offset(18f * direction, 15f), strokeWidth = 2.4f)
            drawCircle(Color.White.copy(alpha = .18f + .55f * intensity), 2.5f + intensity * 2f, start)
        }
    }
}

@Composable
private fun ImageAction(resource: Int, label: String, modifier: Modifier = Modifier, maxHeight: androidx.compose.ui.unit.Dp, action: () -> Unit) {
    Image(painterResource(resource), label, modifier.heightIn(max = maxHeight).clickable(onClick = action), contentScale = ContentScale.Fit)
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
    val auth = remember(activity) { GoogleAuthManager(activity) }
    val googleLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        scope.launch {
            auth.completeSignIn(result.data)
                .onSuccess { viewModel.signedIn() }
                .onFailure { error ->
                    viewModel.authFailed(
                        if (error is TimeoutCancellationException) "Google tardó demasiado en responder. Revisa Internet y vuelve a intentarlo."
                        else "No se pudo completar el acceso de Google. Selecciona una cuenta e inténtalo nuevamente."
                    )
                }
        }
    }
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
                googleLauncher.launch(auth.signInIntent())
            }, modifier = Modifier.fillMaxWidth(.82f).heightIn(min = 48.dp)) {
                Text("CONTINUAR CON GOOGLE", fontWeight = FontWeight.Bold, fontSize = 13.sp, maxLines = 1)
            }
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
        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 14.dp)) {
            listOf(listOf("2A", "2B"), listOf("5A", "5B")).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    pair.forEach { section -> BattleButton(section.replace("A", ".º A").replace("B", ".º B")) { viewModel.chooseSection(section) } }
                }
            }
            BattleButton("🌍 BATALLA LIBRE") { viewModel.choosePublicBattle() }
        }
        Text("Para familiares y participantes que no pertenecen a un aula. Se usará el nombre de su cuenta de Google.", color = Muted, fontSize = 11.sp, textAlign = TextAlign.Center)
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
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val portrait = maxHeight > maxWidth
        val compact = maxHeight < 540.dp
        val padding = if (compact) 12.dp else 22.dp
        if (portrait) {
            Column(Modifier.fillMaxSize().padding(padding), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                LobbyHero(viewModel, Modifier.fillMaxWidth().weight(1.05f), compact = false)
                LobbyProfile(profile, viewModel, Modifier.fillMaxWidth().weight(.95f), compact = true)
            }
        } else {
            Row(Modifier.fillMaxSize().padding(padding), horizontalArrangement = Arrangement.spacedBy(if (compact) 12.dp else 22.dp)) {
                LobbyHero(viewModel, Modifier.fillMaxHeight().weight(1.35f), compact)
                LobbyProfile(profile, viewModel, Modifier.fillMaxHeight().weight(.8f), compact)
            }
        }
    }
}

@Composable
private fun LobbyHero(viewModel: MathBattleViewModel, modifier: Modifier, compact: Boolean) {
    Box(modifier.clip(RoundedCornerShape(22.dp)).background(Brush.horizontalGradient(listOf(Color(0xFF312345), Color(0xFF171523))))) {
        Image(painterResource(R.drawable.rival), null, Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(.56f), contentScale = ContentScale.Crop)
        val size = if (compact) 31.sp else 43.sp
        Column(Modifier.fillMaxHeight().fillMaxWidth(.67f).padding(if (compact) 16.dp else 26.dp), verticalArrangement = Arrangement.Center) {
            Eyebrow("CÁLCULO MENTAL · CONTRARRELOJ")
            Text("TU MENTE.\nTU MEJOR", color = Color.White, fontFamily = BattleDisplayFont, fontSize = size, lineHeight = size * .94f, fontWeight = FontWeight.Bold)
            Text("BATALLA.", color = Lime, fontFamily = BattleDisplayFont, fontSize = size, lineHeight = size, fontWeight = FontWeight.Bold)
            Text("Tres respuestas. Una oportunidad.", color = Muted, fontSize = if (compact) 10.sp else 12.sp, maxLines = 1, modifier = Modifier.padding(vertical = if (compact) 6.dp else 10.dp))
            Button(onClick = viewModel::startBattle, modifier = Modifier.heightIn(min = 42.dp)) { Text("¡A LA BATALLA! ↗", fontWeight = FontWeight.Black, fontSize = if (compact) 11.sp else 13.sp, maxLines = 1) }
        }
    }
}

@Composable
private fun LobbyProfile(profile: StudentProfile, viewModel: MathBattleViewModel, modifier: Modifier, compact: Boolean) {
    Column(modifier.clip(RoundedCornerShape(22.dp)).background(Panel).padding(if (compact) 14.dp else 24.dp), verticalArrangement = Arrangement.spacedBy(if (compact) 3.dp else 7.dp)) {
        Text(avatarGlyph(profile.avatarId), fontSize = if (compact) 32.sp else 46.sp)
        Text(profile.publicName, fontFamily = BattleDisplayFont, fontSize = if (compact) 22.sp else 29.sp, fontWeight = FontWeight.Bold, maxLines = 1)
        Text("${profile.section} · ${profile.bestScore} pts", color = Lime, fontSize = if (compact) 11.sp else 14.sp)
        Button(onClick = { viewModel.showRanking() }, modifier = Modifier.fillMaxWidth().heightIn(min = 40.dp)) { Text("🏆 VER RANKING", fontSize = 11.sp, maxLines = 1) }
        OutlinedButton(onClick = { viewModel.goSections() }, modifier = Modifier.fillMaxWidth().heightIn(min = 40.dp)) { Text("CAMBIAR AULA", fontSize = 11.sp, maxLines = 1) }
        OutlinedButton(onClick = viewModel::signOut, modifier = Modifier.fillMaxWidth().heightIn(min = 40.dp)) { Text("CERRAR SESIÓN", fontSize = 11.sp, maxLines = 1) }
        if (!compact) Text("11 niveles · Primera fase hasta 120 puntos", color = Muted, fontSize = 11.sp)
    }
}

@Composable
private fun CountdownScreen(state: UiState) {
    CenterCard {
        Eyebrow(state.countdownLabel)
        Text(avatarGlyph(state.profile?.avatarId.orEmpty()), fontSize = 68.sp)
        Text("¡Bienvenido, ${state.profile?.publicName.orEmpty()}!", fontSize = 34.sp, fontWeight = FontWeight.Black)
        Text(if (state.countdown == 0) "⚡" else state.countdown.toString(), color = Lime, fontSize = 112.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun GameScreen(state: UiState, viewModel: MathBattleViewModel) {
    val game = state.game
    val rule = GameEngine.levels[game.level - 1]
    val danger = game.remaining <= rule.capSeconds * .1
    val pulse = rememberInfiniteTransition(label = "neonTimer").animateFloat(
        initialValue = .35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(280), RepeatMode.Reverse),
        label = "dangerPulse"
    ).value
    BackHandler { viewModel.finishBattle() }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        // Orientation, rather than an arbitrary tablet width, decides the game layout.
        // This keeps every gameplay control in one screen on phones, tablets and panels.
        val landscape = maxWidth > maxHeight * 1.18f
        val compactLandscape = landscape && maxHeight < 500.dp
        val roomy = maxWidth >= 900.dp && maxHeight >= 500.dp
        val short = maxHeight < 420.dp
        val horizontalPadding = when { roomy -> 48.dp; landscape -> 20.dp; else -> 18.dp }
        Column(Modifier.fillMaxSize().padding(horizontal = horizontalPadding, vertical = if (short) 8.dp else 14.dp)) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("PUNTAJE: ${game.score}", color = Color.White, fontFamily = BattleDisplayFont, fontSize = if (roomy) 42.sp else 27.sp, fontWeight = FontWeight.Black)
                    Text("NIVEL ${game.level} · ${rule.name}", color = Purple, fontSize = if (roomy) 14.sp else 10.sp)
                }
                Text(state.profile?.publicName.orEmpty(), color = Muted, fontSize = if (roomy) 15.sp else 11.sp, maxLines = 1, modifier = Modifier.align(Alignment.CenterStart).widthIn(max = if (roomy) 250.dp else 120.dp))
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("TIEMPO RESTANTE", color = if (danger) Red.copy(alpha = pulse) else Muted, fontSize = 11.sp, modifier = Modifier.weight(1f))
                Text("%.1f s".format(game.remaining), color = if (danger) Red.copy(alpha = pulse) else Color.White, fontSize = if (roomy) 19.sp else 14.sp, fontWeight = FontWeight.Bold)
            }
            Box(
                Modifier.fillMaxWidth().height(if (roomy) 16.dp else 10.dp)
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
            val question: @Composable (Modifier) -> Unit = { modifier ->
                Column(modifier, verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                    Eyebrow(rule.skill.uppercase())
                    val questionSize = when {
                        compactLandscape && game.question.text.length > 55 -> 23.sp
                        compactLandscape && game.question.text.length > 28 -> 29.sp
                        compactLandscape && game.question.text.length > 16 -> 38.sp
                        compactLandscape -> 56.sp
                        game.question.text.length > 55 -> if (roomy) 56.sp else 32.sp
                        game.question.text.length > 28 -> if (roomy) 72.sp else 42.sp
                        else -> if (roomy) 118.sp else 88.sp
                    }
                    Text(game.question.text, color = Color.White, fontFamily = BattleDisplayFont, fontSize = questionSize, lineHeight = questionSize * 1.02f, fontWeight = FontWeight.Black, textAlign = TextAlign.Center, maxLines = 4)
                }
            }
            val answers: @Composable (Modifier) -> Unit = { modifier ->
                Row(modifier, horizontalArrangement = Arrangement.spacedBy(if (roomy) 20.dp else 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    game.question.choices.forEach { choice ->
                        ArcadeAnswerButton(choice, game.selectedChoice, game.question.answer, Modifier.weight(1f).fillMaxHeight()) { viewModel.answer(choice) }
                    }
                }
            }
            if (compactLandscape) {
                Row(Modifier.weight(1f).fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    question(Modifier.weight(.78f).fillMaxHeight())
                    answers(Modifier.weight(1.22f).fillMaxHeight().padding(start = 10.dp))
                }
            } else {
                question(Modifier.weight(.50f).fillMaxWidth())
                answers(Modifier.weight(.50f).fillMaxWidth())
            }
            Row(Modifier.fillMaxWidth().padding(top = if (short) 3.dp else 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("✓ +${rule.gainSeconds} s  ·  ✕ −${rule.lossSeconds} s", color = Muted)
                if (!short) Text(if (game.streak >= 3) "⚡ ${game.streak} aciertos seguidos" else "⚡ Cada acierto cuenta", color = Purple)
                Text("Terminar partida", color = Purple, modifier = Modifier.clickable { viewModel.finishBattle() })
            }
        }
    }
}

@Composable
private fun ArcadeAnswerButton(
    choice: String,
    selectedChoice: String?,
    correctChoice: String,
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
            revealed -> Color(0xFF526579)
            else -> Color(0xFF16BFFF)
        },
        tween(160),
        label = "arcadeColor"
    )
    val glow by animateFloatAsState(if (correct || wrong) 1f else if (pressed) .7f else .18f, tween(120), label = "arcadeGlow")
    val travel by animateDpAsState(if (pressed) 10.dp else 1.dp, tween(70), label = "arcadeTravel")
    Box(modifier, contentAlignment = Alignment.Center) {
        Box(Modifier.fillMaxHeight(.96f).aspectRatio(1f)
            .shadow(24.dp * glow, CircleShape, ambientColor = if (wrong) Red else topColor, spotColor = if (wrong) Red else topColor)
            .graphicsLayer { translationY = travel.toPx(); scaleX = if (pressed) .94f else 1f; scaleY = if (pressed) .92f else 1f }
            .clickable(interactionSource = interaction, indication = null, enabled = selectedChoice == null, onClick = onClick), contentAlignment = Alignment.Center) {
            Image(
                painterResource(R.drawable.arcade_button), null, Modifier.fillMaxSize(), contentScale = ContentScale.Fit,
                colorFilter = when { correct -> ColorFilter.tint(Color.White, BlendMode.Modulate); wrong -> ColorFilter.tint(Red, BlendMode.Modulate); revealed -> ColorFilter.tint(Color(0xFF718096), BlendMode.Modulate); else -> null }
            )
            Text(choice, color = if (correct) Ink else Color.White, fontFamily = BattleDisplayFont, fontSize = when { choice.length > 8 -> 24.sp; choice.length > 4 -> 32.sp; else -> 48.sp }, fontWeight = FontWeight.Black, textAlign = TextAlign.Center, modifier = Modifier.padding(bottom = 4.dp))
        }
    }
}

@Composable
private fun LevelUpScreen(state: UiState, viewModel: MathBattleViewModel) {
    val milestone = GameEngine.milestoneFor(state.game.score) ?: return
    CenterCard {
        Image(painterResource(R.drawable.rival), null, Modifier.size(170.dp).clip(CircleShape), contentScale = ContentScale.Crop)
        Eyebrow(milestone.eyebrow)
        Text(milestone.title, fontSize = 46.sp, fontWeight = FontWeight.Black, textAlign = TextAlign.Center)
        Text(milestone.message, color = Muted, textAlign = TextAlign.Center)
        BattleButton("${milestone.button} ↗", viewModel::continueLevel)
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
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
        Text(when { state.rankingSaving -> "Guardando posición…"; state.sectionRank != null -> "Puesto en ${if (state.profile?.section == "LIBRE") "Batalla Libre" else "tu sección"}: ${state.sectionRank}"; else -> "Resultado no incorporado al ranking" }, color = Purple)
        state.message?.let { Message(it) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            BattleButton("¡UNA MÁS!", viewModel::startBattle)
            OutlinedButton(onClick = viewModel::goLobby) { Text("VOLVER") }
            OutlinedButton(onClick = { viewModel.showRanking() }) { Text("🏆 RANKING") }
        }
    }
}

@Composable private fun ResultStat(value: String, label: String) { Column(horizontalAlignment = Alignment.CenterHorizontally) { Text(value, color = Lime, fontSize = 30.sp, fontWeight = FontWeight.Black); Text(label, color = Muted, fontSize = 10.sp) } }

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun RankingScreen(state: UiState, viewModel: MathBattleViewModel) {
    var pendingDelete by remember { mutableStateOf<String?>(null) }
    var confirmClear by remember { mutableStateOf(false) }
    BackHandler { viewModel.goLobby() }
    Column(Modifier.fillMaxSize().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Eyebrow("CLASIFICACIÓN ONLINE")
        Text("Ranking en vivo", fontSize = 42.sp, fontWeight = FontWeight.Black)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(12.dp)) { listOf("2A", "2B", "5A", "5B", "LIBRE").forEach { section -> OutlinedButton(onClick = { viewModel.showRanking(section) }, colors = ButtonDefaults.outlinedButtonColors(contentColor = if (section == state.section) Lime else Color.White)) { Text(if (section == "LIBRE") "BATALLA LIBRE" else section) } } }
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
        val compactHeight = maxHeight < 520.dp
        val outerHorizontal = if (tablet) 44.dp else 16.dp
        val outerVertical = if (maxHeight >= 650.dp) 30.dp else 6.dp
        val innerPadding = if (compactHeight) 14.dp else if (tablet) 34.dp else 20.dp
        Column(
            Modifier.fillMaxSize()
                .padding(horizontal = outerHorizontal, vertical = outerVertical)
                .clip(RoundedCornerShape(if (tablet) 30.dp else 22.dp))
                .background(Panel.copy(alpha = .94f))
                .border(1.dp, Purple.copy(alpha = .35f), RoundedCornerShape(if (tablet) 30.dp else 22.dp))
                .padding(innerPadding)
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(if (compactHeight) 6.dp else if (tablet) 12.dp else 9.dp, if (compactHeight) Alignment.Top else Alignment.CenterVertically),
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
    var speech by remember { mutableStateOf<TextToSpeech?>(null) }
    DisposableEffect(context) {
        var engine: TextToSpeech? = null
        engine = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                engine?.language = Locale("es", "PE")
                engine?.setSpeechRate(1.02f)
                speech = engine
            }
        }
        onDispose { engine?.stop(); engine?.shutdown(); speech = null }
    }
    LaunchedEffect(state.screen, speech) {
        if (state.screen == Screen.COUNTDOWN && state.countdownLabel.startsWith("¿ESTÁS LISTO")) {
            speech?.speak("¿Estás listo para la batalla? En tres, dos, uno.", TextToSpeech.QUEUE_FLUSH, null, "battle-countdown")
        }
    }
    DisposableEffect(state.screen) {
        val music = if (state.screen == Screen.GAME) MediaPlayer.create(context, R.raw.suspenso_10min)?.apply {
            isLooping = true
            setVolume(.22f, .22f)
            start()
        } else null
        onDispose { music?.stop(); music?.release() }
    }
    LaunchedEffect(state.game.score, state.game.sessionId) {
        if (state.game.score > 0 && state.game.score % 10 == 0) {
            MediaPlayer.create(context, R.raw.oneup)?.apply {
                setOnCompletionListener { it.release() }
                start()
            }
        }
    }
    val danger = state.screen == Screen.GAME &&
        state.game.remaining <= GameEngine.levels[state.game.level - 1].capSeconds * .1
    LaunchedEffect(danger, state.game.sessionId) {
        if (!danger) return@LaunchedEffect
        val tick = ToneGenerator(AudioManager.STREAM_MUSIC, 45)
        try {
            while (true) {
                tick.startTone(ToneGenerator.TONE_PROP_BEEP, 45)
                kotlinx.coroutines.delay(210)
            }
        } finally {
            tick.release()
        }
    }
    LaunchedEffect(state.game.selectedChoice) {
        val selected = state.game.selectedChoice ?: return@LaunchedEffect
        MediaPlayer.create(context, R.raw.coin)?.apply {
            setOnCompletionListener { it.release() }
            start()
        }
    }
}
