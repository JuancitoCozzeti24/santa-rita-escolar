package pe.profejohnny.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.VideoView
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private enum class Screen { HOME, CHAT, NOTICES }
private data class ChatMessage(val text: String, val fromUser: Boolean)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        createNotificationChannel()
        setContent { ProfeJohnnyApp() }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "profe_johnny_avisos",
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = getString(R.string.notification_channel_description)
                enableVibration(true)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }
}

@Composable
private fun ProfeJohnnyApp() {
    var screen by remember { mutableStateOf(Screen.HOME) }
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF00543D),
            secondary = Color(0xFFD7AD32),
            background = Color(0xFFF7F2E7),
            surface = Color.White
        )
    ) {
        when (screen) {
            Screen.HOME -> HomeScreen(
                onConsult = { screen = Screen.CHAT },
                onNotices = { screen = Screen.NOTICES }
            )
            Screen.CHAT -> ChatScreen(onBack = { screen = Screen.HOME })
            Screen.NOTICES -> NoticesScreen(onBack = { screen = Screen.HOME })
        }
    }
}

@Composable
private fun VideoBackground() {
    Box(Modifier.fillMaxSize()) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { context ->
                VideoView(context).apply {
                    setVideoURI(Uri.parse("android.resource://${context.packageName}/${R.raw.fondo_mate}"))
                    setOnPreparedListener { player ->
                        player.isLooping = true
                        player.setVolume(0f, 0f)
                        start()
                    }
                }
            },
            update = { view -> if (!view.isPlaying) view.start() }
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(
                            Color.Black.copy(alpha = 0.32f),
                            Color(0xFF003D2E).copy(alpha = 0.42f),
                            Color.Black.copy(alpha = 0.60f)
                        )
                    )
                )
        )
    }
}

@Composable
private fun Metal3DButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val y by animateDpAsState(if (pressed) 4.dp else 0.dp, label = "buttonY")
    val elevation by animateDpAsState(if (pressed) 2.dp else 12.dp, label = "buttonShadow")
    val shape = RoundedCornerShape(36.dp)

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(68.dp)
            .offset(y = y)
            .shadow(elevation, shape)
            .background(
                Brush.verticalGradient(
                    listOf(
                        Color(0xFFF6FCFB),
                        Color(0xFFC5D0CF),
                        Color(0xFF7D8B8C),
                        Color(0xFFDCE6E4)
                    )
                ),
                shape
            )
            .border(2.dp, Color(0xFF26383A), shape)
            .border(1.dp, Color(0xFFF0F8F6), RoundedCornerShape(34.dp))
            .clickable(interactionSource = interaction, indication = null, onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text,
            color = Color(0xFF081412),
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.3.sp
        )
    }
}

@Composable
private fun HomeScreen(onConsult: () -> Unit, onNotices: () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        VideoBackground()
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 28.dp, vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                "PROFE JOHNNY APP",
                color = Color.White,
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 2.sp,
                modifier = Modifier
                    .background(Color(0xA8003D2D), RoundedCornerShape(20.dp))
                    .border(1.dp, Color(0xFFD7AD32), RoundedCornerShape(20.dp))
                    .padding(horizontal = 18.dp, vertical = 8.dp)
            )
            Spacer(Modifier.height(18.dp))
            Image(
                painter = painterResource(R.drawable.profe_johnny_logo),
                contentDescription = "Profe Johnny",
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .size(250.dp)
                    .shadow(18.dp, CircleShape)
                    .clip(CircleShape)
                    .border(5.dp, Color(0xFFD7AD32), CircleShape)
            )
            Spacer(Modifier.height(22.dp))
            Text(
                "Información y acompañamiento escolar",
                color = Color.White,
                fontSize = 18.sp,
                fontWeight = FontWeight.Medium,
                textAlign = TextAlign.Center
            )
            Text(
                "Matemática · 2.º y 5.º de secundaria",
                color = Color(0xFFF6E8B7),
                fontSize = 14.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 4.dp)
            )
            Spacer(Modifier.height(28.dp))
            Metal3DButton("CONSULTAR", onConsult, Modifier.fillMaxWidth(0.88f))
            Spacer(Modifier.height(16.dp))
            Metal3DButton("AVISOS", onNotices, Modifier.fillMaxWidth(0.88f))
        }
    }
}

@Composable
private fun ChatScreen(onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    val messages = remember {
        mutableStateListOf(
            ChatMessage(
                "Hola, soy el Profe Johnny. ¿En qué puedo ayudarte?",
                false
            )
        )
    }
    var grade by remember { mutableStateOf("2.º") }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }

    // El código del docente nunca se almacena en el APK ni se persiste.
    // Solo conservamos el token temporal devuelto por el servidor durante esta sesión.
    var teacherToken by remember { mutableStateOf<String?>(null) }
    var showTeacherLogin by remember { mutableStateOf(false) }
    var teacherCode by remember { mutableStateOf("") }
    var teacherError by remember { mutableStateOf<String?>(null) }
    var authenticating by remember { mutableStateOf(false) }

    LaunchedEffect(messages.size) {
        if (messages.size > 1) {
            listState.scrollToItem(messages.lastIndex)
        }
    }

    Box(
        Modifier
            .fillMaxSize()
            .imePadding()
            .background(
                Brush.verticalGradient(
                    listOf(
                        Color(0xFFF7F3E8),
                        Color(0xFFEAF4EF),
                        Color(0xFFF7F3E8)
                    )
                )
            )
    ) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().background(Color(0xE6004934)).padding(16.dp, 14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("CONSULTAR", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 21.sp)
                    Text("Profe Johnny", color = Color(0xFFF0D671), fontSize = 13.sp)
                }
                Spacer(Modifier.weight(1f))
                Button(onClick = onBack, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDBB73A))) {
                    Text("Inicio", color = Color(0xFF172018))
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                FilterChip(selected = grade == "2.º", onClick = { grade = "2.º" }, label = { Text("2.º año") })
                FilterChip(selected = grade == "5.º", onClick = { grade = "5.º" }, label = { Text("5.º año") })
            }

            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Button(
                    onClick = {
                        if (teacherToken.isNullOrBlank()) {
                            teacherError = null
                            teacherCode = ""
                            showTeacherLogin = true
                        } else {
                            teacherToken = null
                        }
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (teacherToken.isNullOrBlank()) Color(0xFF5A6862) else Color(0xFF006C4F)
                    )
                ) {
                    Text(if (teacherToken.isNullOrBlank()) "Modo docente" else "Salir modo docente")
                }

                Text(
                    if (teacherToken.isNullOrBlank())
                        "Consulta general"
                    else
                        "Modo docente activo · Classroom privado habilitado",
                    color = if (teacherToken.isNullOrBlank()) Color(0xFF5A6862) else Color(0xFF006C4F),
                    fontSize = 12.sp,
                    fontWeight = if (teacherToken.isNullOrBlank()) FontWeight.Normal else FontWeight.SemiBold,
                    modifier = Modifier.weight(1f)
                )
            }

            if (!teacherToken.isNullOrBlank()) {
                Text(
                    "Puedes preguntar, por ejemplo: “¿Cómo va Claudio León en Classroom?”",
                    color = Color(0xFF315B4C),
                    fontSize = 12.sp,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 5.dp)
                )
            }

            if (sending) {
                Text(
                    "Consultando información…",
                    color = Color(0xFF006C4F),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .padding(horizontal = 16.dp, vertical = 4.dp)
                        .background(Color.White.copy(alpha = 0.82f), RoundedCornerShape(12.dp))
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                )
            }

            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(9.dp)
            ) {
                items(messages) { message ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = if (message.fromUser) Arrangement.End else Arrangement.Start
                    ) {
                        Box(
                            modifier = Modifier
                                .widthIn(max = 315.dp)
                                .background(
                                    if (message.fromUser) Color(0xEEDFF1E7) else Color(0xF2FFFFFF),
                                    RoundedCornerShape(18.dp)
                                )
                                .padding(horizontal = 14.dp, vertical = 11.dp)
                        ) {
                            Text(message.text, color = Color(0xFF172018), fontSize = 15.sp)
                        }
                    }
                }
            }

            Row(
                Modifier.fillMaxWidth().background(Color.White.copy(alpha = 0.94f)).padding(10.dp),
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("Escribe tu consulta…") },
                    enabled = !sending,
                    maxLines = 4
                )
                Button(
                    enabled = input.isNotBlank() && !sending,
                    onClick = {
                        val question = input.trim()
                        val activeTeacherToken = teacherToken
                        input = ""
                        messages += ChatMessage(question, true)
                        sending = true
                        scope.launch {
                            val answer = withContext(Dispatchers.IO) {
                                askBackend(question, grade, activeTeacherToken)
                            }
                            messages += ChatMessage(answer, false)
                            sending = false
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF006C4F))
                ) { Text(if (sending) "Consultando…" else "Enviar") }
            }
        }

        if (showTeacherLogin) {
            AlertDialog(
                onDismissRequest = {
                    if (!authenticating) {
                        showTeacherLogin = false
                        teacherCode = ""
                        teacherError = null
                    }
                },
                title = { Text("Activar modo docente") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Ingresa tu código de docente. El código no se guarda en el teléfono.")
                        OutlinedTextField(
                            value = teacherCode,
                            onValueChange = {
                                teacherCode = it
                                teacherError = null
                            },
                            label = { Text("Código") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            enabled = !authenticating
                        )
                        teacherError?.let {
                            Text(it, color = Color(0xFFB3261E), fontSize = 13.sp)
                        }
                    }
                },
                confirmButton = {
                    TextButton(
                        enabled = teacherCode.isNotBlank() && !authenticating,
                        onClick = {
                            val code = teacherCode
                            authenticating = true
                            teacherError = null
                            scope.launch {
                                val token = withContext(Dispatchers.IO) { authenticateOwner(code) }
                                authenticating = false
                                if (token.isNullOrBlank()) {
                                    teacherError = "No se pudo activar el modo docente. Verifica el código e inténtalo otra vez."
                                } else {
                                    teacherToken = token
                                    teacherCode = ""
                                    showTeacherLogin = false
                                    messages += ChatMessage(
                                        "Modo docente activado. Ahora puedo consultar de forma privada el avance de tus estudiantes en Classroom.",
                                        false
                                    )
                                }
                            }
                        }
                    ) {
                        Text(if (authenticating) "Verificando…" else "Activar")
                    }
                },
                dismissButton = {
                    TextButton(
                        enabled = !authenticating,
                        onClick = {
                            showTeacherLogin = false
                            teacherCode = ""
                            teacherError = null
                        }
                    ) { Text("Cancelar") }
                }
            )
        }
    }
}

private fun authenticateOwner(code: String): String? {
    val base = BuildConfig.API_BASE_URL.trim().trimEnd('/')
    if (base.isBlank() || code.isBlank()) return null
    return try {
        val connection = (URL("$base/auth").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 30_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        val payload = JSONObject()
            .put("role", "owner")
            .put("code", code)
            .toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val httpCode = connection.responseCode
        val stream = if (httpCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (httpCode !in 200..299) null
        else JSONObject(body).optString("token").takeIf { it.isNotBlank() }
    } catch (_: Exception) {
        null
    }
}

private fun askBackend(message: String, grade: String, teacherToken: String? = null): String {
    val base = BuildConfig.API_BASE_URL.trim().trimEnd('/')
    if (base.isBlank()) {
        return "No pude atender tu consulta en este momento. Inténtalo nuevamente en unos segundos."
    }
    return try {
        val secure = !teacherToken.isNullOrBlank()
        val endpoint = if (secure) "$base/secure-chat" else "$base/chat"
        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 60_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (secure) setRequestProperty("Authorization", "Bearer $teacherToken")
        }
        val payload = JSONObject().put("message", message).put("grade", grade).toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val httpCode = connection.responseCode
        val stream = if (httpCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()

        if (httpCode == 401 && secure) {
            "La sesión del modo docente venció o ya no es válida. Sal del modo docente y vuelve a activarlo."
        } else if (httpCode !in 200..299) {
            "No pude conectar con el asistente en este momento."
        } else {
            JSONObject(body).optString("reply").ifBlank { "No recibí una respuesta válida del servidor." }
        }
    } catch (_: Exception) {
        "No pude conectar con el asistente en este momento. Inténtalo nuevamente en unos minutos."
    }
}

@Composable
private fun NoticesScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    var selectedGrade by remember { mutableStateOf<String?>(null) }
    var permissionGranted by remember {
        mutableStateOf(
            Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        permissionGranted = it
    }

    Column(Modifier.fillMaxSize().background(Color(0xFFF7F2E7))) {
        Row(
            Modifier.fillMaxWidth().background(Color(0xFF004934)).padding(16.dp, 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("AVISOS", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Button(onClick = onBack, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDBB73A))) {
                Text("Inicio", color = Color(0xFF172018))
            }
        }

        Column(
            Modifier.fillMaxSize().padding(horizontal = 26.dp, vertical = 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            if (selectedGrade == null) {
                Text("Selecciona el grado", color = Color(0xFF003F2E), fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text(
                    "Los avisos se organizarán por grado para que cada familia reciba únicamente la información que le corresponde.",
                    color = Color(0xFF4C5A53),
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(top = 8.dp, bottom = 30.dp)
                )
                Metal3DButton("2DO AÑO", { selectedGrade = "2.º año" })
                Spacer(Modifier.height(18.dp))
                Metal3DButton("5TO AÑO", { selectedGrade = "5.º año" })
                Spacer(Modifier.height(34.dp))

                if (!permissionGranted && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    Button(
                        onClick = { permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF006C4F))
                    ) { Text("Activar notificaciones") }
                    Text(
                        "Actívalas para recibir avisos importantes en tu teléfono.",
                        color = Color(0xFF4C5A53),
                        fontSize = 13.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                } else {
                    Text("✓ Notificaciones permitidas", color = Color(0xFF006C4F), fontWeight = FontWeight.SemiBold)
                }
            } else {
                Text(selectedGrade!!, color = Color(0xFF003F2E), fontSize = 28.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(20.dp))
                Box(
                    Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(20.dp)).padding(22.dp)
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                        Text("Aún no hay avisos publicados", color = Color(0xFF17362D), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        Text(
                            "Los avisos aparecerán aquí cuando el Profe Johnny los publique.",
                            color = Color(0xFF5A6862),
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(top = 8.dp)
                        )
                    }
                }
                Spacer(Modifier.height(20.dp))
                Button(
                    onClick = { selectedGrade = null },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDBB73A))
                ) { Text("Cambiar de grado", color = Color(0xFF172018)) }
            }
        }
    }
}
