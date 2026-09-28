from pathlib import Path

p = Path("profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt")
s = p.read_text(encoding="utf-8")

old = '''            LazyColumn(
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
'''

new = '''            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
            ) {
                Image(
                    painter = painterResource(R.drawable.chat_fondo),
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Crop
                )
                Box(
                    Modifier
                        .fillMaxSize()
                        .background(Color(0x18003D2D))
                )
                LazyColumn(
                    state = listState,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 14.dp, vertical = 10.dp),
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
                                        if (message.fromUser) Color(0xF2DFF1E7) else Color(0xF5FFFFFF),
                                        RoundedCornerShape(18.dp)
                                    )
                                    .padding(horizontal = 14.dp, vertical = 11.dp)
                            ) {
                                Text(message.text, color = Color(0xFF172018), fontSize = 15.sp)
                            }
                        }
                    }
                }
            }
'''

if old not in s:
    raise SystemExit("Chat message list anchor not found")

s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
