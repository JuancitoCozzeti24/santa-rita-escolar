from pathlib import Path

main = Path('profe-johnny-app/app/src/main/java/pe/profejohnny/app/MainActivity.kt')
s = main.read_text(encoding='utf-8')
old = '''    LaunchedEffect(messages.size) {
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
'''
new = '''    LaunchedEffect(messages.size) {
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
'''
if old not in s:
    raise SystemExit('Expected ChatScreen block was not found')
main.write_text(s.replace(old, new), encoding='utf-8')

gradle = Path('profe-johnny-app/app/build.gradle.kts')
g = gradle.read_text(encoding='utf-8')
g = g.replace('versionCode = 4', 'versionCode = 5')
g = g.replace('versionName = "0.2.2"', 'versionName = "0.2.3"')
gradle.write_text(g, encoding='utf-8')
