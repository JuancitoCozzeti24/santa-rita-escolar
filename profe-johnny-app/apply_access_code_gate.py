from pathlib import Path

p = Path("profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt")
s = p.read_text(encoding="utf-8")

if "private data class AccessSession" not in s:
    s = s.replace(
        "private data class ChatMessage(val text: String, val fromUser: Boolean)\n",
        "private data class ChatMessage(val text: String, val fromUser: Boolean)\n"
        "private data class AccessSession(val token: String, val role: String, val displayName: String)\n",
        1,
    )

start = s.index("@Composable\nprivate fun ChatScreen")
end = s.index("@Composable\nprivate fun NoticesScreen", start)

new_block = r'''@Composable
private fun ChatScreen(onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    val messages = remember {
        mutableStateListOf(
            ChatMessage("Hola, soy el Profe Johnny. ¿En qué puedo ayudarte?", false)
        )
    }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }

    var accessSession by remember { mutableStateOf<AccessSession?>(null) }
    var accessCode by remember { mutableStateOf("") }
    var accessError by remember { mutableStateOf<String?>(null) }
    var authenticating by remember { mutableStateOf(false) }

    if (accessSession == null) {
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
                        Text("Acceso personal", color = Color(0xFFF0D671), fontSize = 13.sp)
                    }
                    Spacer(Modifier.weight(1f))
                    Button(
                        onClick = onBack,
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDBB73A))
                    ) {
                        Text("Inicio", color = Color(0xFF172018))
                    }
                }

                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 26.dp, vertical = 30.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center
                ) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color.White, RoundedCornerShape(24.dp))
                            .shadow(10.dp, RoundedCornerShape(24.dp))
                            .padding(horizontal = 22.dp, vertical = 26.dp)
                    ) {
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Text(
                                "Bienvenido a Profe Johnny",
                                color = Color(0xFF004934),
                                fontSize = 24.sp,
                                fontWeight = FontWeight.Bold,
                                textAlign = TextAlign.Center
                            )
                            Text(
                                "Ingresa tu código de acceso",
                                color = Color(0xFF17362D),
                                fontSize = 18.sp,
                                fontWeight = FontWeight.SemiBold
                            )
                            Text(
                                "El código identifica automáticamente si el acceso corresponde al docente, a un estudiante o a una familia.",
                                color = Color(0xFF5A6862),
                                fontSize = 14.sp,
                                textAlign = TextAlign.Center,
                                lineHeight = 20.sp
                            )

                            OutlinedTextField(
                                value = accessCode,
                                onValueChange = {
                                    accessCode = it
                                    accessError = null
                                },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("Código de acceso") },
                                visualTransformation = PasswordVisualTransformation(),
                                singleLine = true,
                                enabled = !authenticating
                            )

                            accessError?.let {
                                Text(
                                    it,
                                    color = Color(0xFFB3261E),
                                    fontSize = 13.sp,
                                    textAlign = TextAlign.Center
                                )
                            }

                            Button(
                                enabled = accessCode.isNotBlank() && !authenticating,
                                onClick = {
                                    val code = accessCode.trim()
                                    authenticating = true
                                    accessError = null
                                    scope.launch {
                                        val verified = withContext(Dispatchers.IO) { authenticateAccess(code) }
                                        authenticating = false
                                        if (verified == null) {
                                            accessError = "No pude validar el código. Verifica que esté escrito correctamente."
                                        } else {
                                            accessSession = verified
                                            accessCode = ""
                                            messages.clear()
                                            val welcome = when (verified.role) {
                                                "owner" -> "Bienvenido, Profe Johnny. El modo docente está activo y puedes realizar tus pruebas."
                                                "student" -> "Hola, ${verified.displayName}. Ya puedes consultar tus notas, entregas y avance académico."
                                                "family" -> "Bienvenidos. El acceso familiar está verificado y pueden consultar el avance académico autorizado."
                                                else -> "Acceso verificado. ¿En qué puedo ayudarte?"
                                            }
                                            messages += ChatMessage(welcome, false)
                                        }
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF006C4F))
                            ) {
                                Text(if (authenticating) "Verificando…" else "INGRESAR")
                            }

                            Text(
                                "Tu código no se muestra en pantalla ni se envía dentro de tus mensajes.",
                                color = Color(0xFF6C756F),
                                fontSize = 12.sp,
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                }
            }
        }
        return
    }

    val verifiedSession = accessSession!!

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
                    Text(
                        when (verifiedSession.role) {
                            "owner" -> "Modo docente · Profe Johnny"
                            "student" -> "Acceso estudiante · ${verifiedSession.displayName}"
                            "family" -> "Acceso familiar"
                            else -> "Acceso verificado"
                        },
                        color = Color(0xFFF0D671),
                        fontSize = 12.sp
                    )
                }
                Spacer(Modifier.weight(1f))
                Button(
                    onClick = {
                        accessSession = null
                        messages.clear()
                        messages += ChatMessage("Hola, soy el Profe Johnny. ¿En qué puedo ayudarte?", false)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF5A6862))
                ) {
                    Text("Cambiar acceso", color = Color.White, fontSize = 12.sp)
                }
            }

            if (verifiedSession.role == "owner") {
                Text(
                    "Modo docente activo · puedes consultar cualquier estudiante por nombre.",
                    color = Color(0xFF006C4F),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
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
                        input = ""
                        messages += ChatMessage(question, true)
                        sending = true
                        scope.launch {
                            val answer = withContext(Dispatchers.IO) {
                                askBackend(question, verifiedSession.token)
                            }
                            messages += ChatMessage(answer, false)
                            sending = false
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF006C4F))
                ) {
                    Text(if (sending) "Consultando…" else "Enviar")
                }
            }
        }
    }
}

private fun authenticateAccess(code: String): AccessSession? {
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
            .put("role", "auto")
            .put("code", code)
            .toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val httpCode = connection.responseCode
        val stream = if (httpCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (httpCode !in 200..299) {
            null
        } else {
            val data = JSONObject(body)
            val token = data.optString("token")
            val profile = data.optJSONObject("profile") ?: JSONObject()
            val role = profile.optString("role")
            val displayName = when (role) {
                "owner" -> profile.optString("display_name", "Profe Johnny")
                "student" -> profile.optString("display_name", "Estudiante")
                "family" -> {
                    val children = profile.optJSONArray("children")
                    if (children != null && children.length() == 1) {
                        "Familia de " + children.optJSONObject(0)?.optString("display_name", "estudiante")
                    } else {
                        "Familia verificada"
                    }
                }
                else -> "Usuario verificado"
            }
            if (token.isBlank() || role.isBlank()) null else AccessSession(token, role, displayName)
        }
    } catch (_: Exception) {
        null
    }
}

private fun askBackend(message: String, sessionToken: String): String {
    val base = BuildConfig.API_BASE_URL.trim().trimEnd('/')
    if (base.isBlank()) {
        return "No pude atender tu consulta en este momento. Inténtalo nuevamente en unos segundos."
    }
    return try {
        val connection = (URL("$base/secure-chat").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 60_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Authorization", "Bearer $sessionToken")
        }
        val payload = JSONObject().put("message", message).toString()
        connection.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
        val httpCode = connection.responseCode
        val stream = if (httpCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()

        if (httpCode == 401) {
            "Tu sesión de acceso venció o ya no es válida. Pulsa “Cambiar acceso” e ingresa nuevamente tu código."
        } else if (httpCode !in 200..299) {
            "No pude conectar con el servicio en este momento."
        } else {
            JSONObject(body).optString("reply").ifBlank { "No recibí una respuesta válida del servidor." }
        }
    } catch (_: Exception) {
        "No pude conectar con el servicio en este momento. Inténtalo nuevamente en unos minutos."
    }
}

'''

s = s[:start] + new_block + s[end:]
p.write_text(s, encoding="utf-8")
