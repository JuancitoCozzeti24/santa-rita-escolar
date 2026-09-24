from pathlib import Path

p = Path("profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt")
s = p.read_text(encoding="utf-8")

old = 'Text(message.text, color = Color(0xFF172018), fontSize = 15.sp)'
new = '''Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                message.text.replace("**", "").split("\\n").forEach { raw ->
                                    val line = raw.trim()
                                    if (line.isNotBlank()) {
                                        val isHeading = line.endsWith(":") || (
                                            line.length <= 42 &&
                                            line.any { it.isLetter() } &&
                                            line.filter { it.isLetter() }.all { it.isUpperCase() }
                                        )
                                        Text(
                                            text = line,
                                            color = if (isHeading) Color(0xFF004934) else Color(0xFF172018),
                                            fontSize = if (isHeading) 16.sp else 15.sp,
                                            fontWeight = if (isHeading) FontWeight.Bold else FontWeight.Normal,
                                            lineHeight = 20.sp
                                        )
                                    } else {
                                        Spacer(Modifier.height(2.dp))
                                    }
                                }
                            }'''

if old in s:
    s = s.replace(old, new, 1)
elif "val isHeading = line.endsWith" not in s:
    raise SystemExit("Message renderer anchor missing")

p.write_text(s, encoding="utf-8")
