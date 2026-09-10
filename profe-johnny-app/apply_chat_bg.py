from pathlib import Path
import base64
import re

root = Path(__file__).resolve().parent
b64 = root / "chat_fondo_optimized.b64"
drawable = root / "app/src/main/res/drawable/chat_fondo.jpg"
drawable.parent.mkdir(parents=True, exist_ok=True)
drawable.write_bytes(base64.b64decode(b64.read_text(encoding="utf-8")))

p = root / "app/src/main/java/pe/profejohnny/app/MainActivity.kt"
s = p.read_text(encoding="utf-8")
start = s.index("@Composable\nprivate fun ChatScreen(onBack: () -> Unit) {")
end = s.index("\nprivate fun askBackend(message: String, grade: String): String {", start)
new_fn = '''@Composable
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

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.lastIndex)
        }
    }

    Box(Modifier.fillMaxSize().imePadding()) {
        Image(
            painter = painterResource(R.drawable.chat_fondo),
            contentDescription = "Fondo matemático del chat",
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize()
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(Color.White.copy(alpha = 0.74f))
        )

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
                            val answer = withContext(Dispatchers.IO) { askBackend(question, grade) }
                            messages += ChatMessage(answer, false)
                            sending = false
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF006C4F))
                ) { Text(if (sending) "Consultando…" else "Enviar") }
            }
        }
    }
}
'''
p.write_text(s[:start] + new_fn + s[end:], encoding="utf-8")

g = root / "app/build.gradle.kts"
text = g.read_text(encoding="utf-8")
text = re.sub(r"versionCode = \d+", "versionCode = 4", text, count=1)
text = re.sub(r'versionName = "[^"]+"', 'versionName = "0.2.2"', text, count=1)
g.write_text(text, encoding="utf-8")
