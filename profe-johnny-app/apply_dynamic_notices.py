from pathlib import Path

p = Path("profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt")
s = p.read_text(encoding="utf-8")

if "private data class NoticeItem" not in s:
    anchor = "private data class AccessSession(val token: String, val role: String, val displayName: String)\n"
    addition = """private data class NoticeItem(
    val id: String,
    val type: String,
    val grade: String,
    val section: String,
    val title: String,
    val description: String,
    val dueDate: String,
    val dueTime: String,
    val status: String,
    val topic: String,
    val note: String
)
private data class NoticeFeed(
    val items: List<NoticeItem>,
    val updatedAt: String,
    val error: String? = null
)
"""
    if anchor not in s:
        raise SystemExit("AccessSession anchor not found")
    s = s.replace(anchor, anchor + addition, 1)

start = s.index("@Composable\nprivate fun NoticesScreen")
new_block = r'''@Composable
private fun NoticesScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var selectedGrade by remember { mutableStateOf<String?>(null) }
    var selectedSection by remember { mutableStateOf<String?>(null) }
    var notices by remember { mutableStateOf<List<NoticeItem>>(emptyList()) }
    var updatedAt by remember { mutableStateOf("") }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun loadNotices(force: Boolean = false) {
        val grade = selectedGrade ?: return
        val section = selectedSection ?: return
        val cacheKey = "notices_${grade}_${section}"
        val prefs = context.getSharedPreferences("profe_johnny_notices", android.content.Context.MODE_PRIVATE)

        if (!force) {
            val cached = prefs.getString(cacheKey, null)
            if (!cached.isNullOrBlank()) {
                parseNoticeFeed(cached)?.let {
                    notices = it.items
                    updatedAt = it.updatedAt
                }
            }
        }

        loading = true
        error = null
        scope.launch {
            val result = withContext(Dispatchers.IO) { fetchNotices(grade, section) }
            loading = false
            if (result.error == null) {
                notices = result.items
                updatedAt = result.updatedAt
                val raw = noticeFeedToCache(result)
                prefs.edit().putString(cacheKey, raw).apply()
            } else {
                error = if (notices.isEmpty()) {
                    "No pude actualizar los avisos. Verifica tu conexión e inténtalo nuevamente."
                } else {
                    "No pude actualizar ahora. Se muestra la última información guardada."
                }
            }
        }
    }

    LaunchedEffect(selectedGrade, selectedSection) {
        if (selectedGrade != null && selectedSection != null) {
            loadNotices(force = false)
        }
    }

    Column(Modifier.fillMaxSize().background(Color(0xFFF7F2E7))) {
        Row(
            Modifier.fillMaxWidth().background(Color(0xFF004934)).padding(16.dp, 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("AVISOS", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold)
                Text("Itinerario oficial de Matemática", color = Color(0xFFF0D671), fontSize = 12.sp)
            }
            Spacer(Modifier.weight(1f))
            Button(onClick = onBack, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDBB73A))) {
                Text("Inicio", color = Color(0xFF172018))
            }
        }

        if (selectedGrade == null || selectedSection == null) {
            Column(
                Modifier.fillMaxSize().padding(horizontal = 26.dp, vertical = 28.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    "Selecciona tu sección",
                    color = Color(0xFF003F2E),
                    fontSize = 26.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    "Aquí se publican las actividades, evaluaciones y fechas que todos los estudiantes de la sección deben cumplir.",
                    color = Color(0xFF4C5A53),
                    textAlign = TextAlign.Center,
                    lineHeight = 20.sp,
                    modifier = Modifier.padding(top = 8.dp, bottom = 28.dp)
                )

                Metal3DButton("2.º A", {
                    selectedGrade = "2"
                    selectedSection = "A"
                })
                Spacer(Modifier.height(14.dp))
                Metal3DButton("2.º B", {
                    selectedGrade = "2"
                    selectedSection = "B"
                })
                Spacer(Modifier.height(14.dp))
                Metal3DButton("5.º A", {
                    selectedGrade = "5"
                    selectedSection = "A"
                })
                Spacer(Modifier.height(14.dp))
                Metal3DButton("5.º B", {
                    selectedGrade = "5"
                    selectedSection = "B"
                })
            }
        } else {
            val gradeLabel = if (selectedGrade == "2") "2.º" else "5.º"
            Column(Modifier.fillMaxSize()) {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "$gradeLabel ${selectedSection}",
                            color = Color(0xFF003F2E),
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Bold
                        )
                        if (updatedAt.isNotBlank()) {
                            Text(
                                "Última actualización: ${formatUpdatedAt(updatedAt)}",
                                color = Color(0xFF5A6862),
                                fontSize = 12.sp
                            )
                        }
                    }
                    Button(
                        enabled = !loading,
                        onClick = { loadNotices(force = true) },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF006C4F))
                    ) {
                        Text(if (loading) "Actualizando…" else "Actualizar")
                    }
                }

                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(
                        onClick = {
                            selectedGrade = null
                            selectedSection = null
                            notices = emptyList()
                            error = null
                        }
                    ) {
                        Text("Cambiar sección")
                    }
                    Spacer(Modifier.weight(1f))
                    Text(
                        "Información común para toda la sección",
                        color = Color(0xFF6C756F),
                        fontSize = 11.sp
                    )
                }

                error?.let {
                    Text(
                        it,
                        color = Color(0xFFB3261E),
                        fontSize = 12.sp,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                    )
                }

                if (loading && notices.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            "Actualizando avisos…",
                            color = Color(0xFF006C4F),
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                } else if (notices.isEmpty()) {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .padding(18.dp)
                            .background(Color.White, RoundedCornerShape(20.dp))
                            .padding(24.dp)
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                            Text(
                                "No hay actividades publicadas por ahora",
                                color = Color(0xFF17362D),
                                fontWeight = FontWeight.Bold,
                                fontSize = 18.sp,
                                textAlign = TextAlign.Center
                            )
                            Text(
                                "Pulsa Actualizar para verificar si hay novedades.",
                                color = Color(0xFF5A6862),
                                textAlign = TextAlign.Center,
                                modifier = Modifier.padding(top = 8.dp)
                            )
                        }
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        items(notices) { item ->
                            Box(
                                Modifier
                                    .fillMaxWidth()
                                    .background(Color.White, RoundedCornerShape(18.dp))
                                    .padding(16.dp)
                            ) {
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    val kind = when (item.type.lowercase()) {
                                        "exam", "evaluation", "evaluacion", "examen" -> "EVALUACIÓN"
                                        "material" -> "MATERIAL"
                                        else -> "ACTIVIDAD"
                                    }
                                    Text(
                                        kind,
                                        color = Color(0xFF006C4F),
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        letterSpacing = 1.sp
                                    )
                                    Text(
                                        item.title,
                                        color = Color(0xFF17362D),
                                        fontSize = 18.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                    if (item.description.isNotBlank()) {
                                        Text(
                                            "• ${item.description}",
                                            color = Color(0xFF34463F),
                                            fontSize = 14.sp,
                                            lineHeight = 20.sp
                                        )
                                    }
                                    if (item.topic.isNotBlank()) {
                                        Text(
                                            "• Tema: ${item.topic}",
                                            color = Color(0xFF34463F),
                                            fontSize = 14.sp
                                        )
                                    }
                                    if (item.dueDate.isNotBlank()) {
                                        Text(
                                            "• Fecha: ${formatNoticeDate(item.dueDate)}" +
                                                if (item.dueTime.isNotBlank()) " · ${item.dueTime}" else "",
                                            color = Color(0xFF34463F),
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.SemiBold
                                        )
                                    }
                                    if (item.note.isNotBlank()) {
                                        Text(
                                            "• ${item.note}",
                                            color = Color(0xFF5A4A18),
                                            fontSize = 13.sp,
                                            lineHeight = 18.sp
                                        )
                                    }
                                    if (item.status.isNotBlank() && item.status.lowercase() != "vigente") {
                                        Text(
                                            item.status.uppercase(),
                                            color = Color(0xFF8B3A2B),
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Bold
                                        )
                                    }
                                }
                            }
                        }
                        item {
                            Spacer(Modifier.height(16.dp))
                        }
                    }
                }
            }
        }
    }
}

private fun fetchNotices(grade: String, section: String): NoticeFeed {
    val base = BuildConfig.API_BASE_URL.trim().trimEnd('/')
    if (base.isBlank()) return NoticeFeed(emptyList(), "", "api_not_configured")
    return try {
        val endpoint = "$base/notices?grade=${java.net.URLEncoder.encode(grade, "UTF-8")}&section=${java.net.URLEncoder.encode(section, "UTF-8")}&limit=100"
        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 30_000
            setRequestProperty("Accept", "application/json")
        }
        val httpCode = connection.responseCode
        val stream = if (httpCode in 200..299) connection.inputStream else connection.errorStream
        val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (httpCode !in 200..299) {
            NoticeFeed(emptyList(), "", "http_$httpCode")
        } else {
            parseNoticeFeed(body) ?: NoticeFeed(emptyList(), "", "invalid_response")
        }
    } catch (_: Exception) {
        NoticeFeed(emptyList(), "", "network_error")
    }
}

private fun parseNoticeFeed(raw: String): NoticeFeed? {
    return try {
        val root = JSONObject(raw)
        val array = root.optJSONArray("items")
        val items = mutableListOf<NoticeItem>()
        if (array != null) {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                items += NoticeItem(
                    id = item.optString("id"),
                    type = item.optString("type", "activity"),
                    grade = item.optString("grade"),
                    section = item.optString("section"),
                    title = item.optString("title"),
                    description = item.optString("description"),
                    dueDate = item.optString("due_date"),
                    dueTime = item.optString("due_time"),
                    status = item.optString("status", "vigente"),
                    topic = item.optString("topic"),
                    note = item.optString("note")
                )
            }
        }
        NoticeFeed(items, root.optString("updated_at"))
    } catch (_: Exception) {
        null
    }
}

private fun noticeFeedToCache(feed: NoticeFeed): String {
    val root = JSONObject()
    root.put("updated_at", feed.updatedAt)
    val array = org.json.JSONArray()
    feed.items.forEach { item ->
        array.put(
            JSONObject()
                .put("id", item.id)
                .put("type", item.type)
                .put("grade", item.grade)
                .put("section", item.section)
                .put("title", item.title)
                .put("description", item.description)
                .put("due_date", item.dueDate)
                .put("due_time", item.dueTime)
                .put("status", item.status)
                .put("topic", item.topic)
                .put("note", item.note)
        )
    }
    root.put("items", array)
    return root.toString()
}

private fun formatNoticeDate(value: String): String {
    val parts = value.split("-")
    return if (parts.size == 3) "${parts[2]}/${parts[1]}/${parts[0]}" else value
}

private fun formatUpdatedAt(value: String): String {
    val date = value.take(10)
    val time = value.drop(11).take(5)
    val prettyDate = formatNoticeDate(date)
    return if (time.matches(Regex("\\d{2}:\\d{2}"))) "$prettyDate · $time" else prettyDate
}
'''

s = s[:start] + new_block
p.write_text(s, encoding="utf-8")
