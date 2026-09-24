from pathlib import Path

p = Path("profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt")
s = p.read_text(encoding="utf-8")
s = s.replace(
    'Text(message.text, color = Color(0xFF172018), fontSize = 15.sp)',
    'Text(message.text.replace("**", ""), color = Color(0xFF172018), fontSize = 15.sp, lineHeight = 20.sp)'
)
p.write_text(s, encoding="utf-8")
