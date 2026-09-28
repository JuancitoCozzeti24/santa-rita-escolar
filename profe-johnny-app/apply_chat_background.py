from pathlib import Path

p = Path("profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt")
s = p.read_text(encoding="utf-8")

marker = "                items(messages) { message ->"
idx = s.find(marker)
if idx < 0:
    raise SystemExit("Chat messages marker not found")

start = s.rfind("            LazyColumn(", 0, idx)
if start < 0:
    raise SystemExit("Chat LazyColumn start not found")

end_marker = "\n\n            Row(\n                Modifier.fillMaxWidth().background(Color.White.copy(alpha = 0.94f)).padding(10.dp),"
end = s.find(end_marker, idx)
if end < 0:
    raise SystemExit("Chat input row marker not found")

original = s[start:end]
original = original.replace(
    "modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp)",
    "modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 10.dp)",
    1,
)
if ".weight(1f)" in original:
    original = original.replace(".weight(1f)", "", 1)

indented = "\n".join(("    " + line) if line else line for line in original.split("\n"))

wrapper = '''            Box(
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
''' + indented + '''
            }'''

s = s[:start] + wrapper + s[end:]
p.write_text(s, encoding="utf-8")
