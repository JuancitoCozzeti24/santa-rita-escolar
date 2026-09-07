# SIEROOM Desktop Agent — Windows build

La compilación del ejecutable se realiza automáticamente con GitHub Actions en Windows.

## Artefacto esperado

`SIEROOM-Desktop-Agent-Windows-v0.1`

Contenido:
- `SIEROOM-Desktop-Agent-v0.1.exe`
- `LEEME-PRIMERO.txt`

## Diseño de esta primera versión

- Python + Playwright empaquetados con PyInstaller.
- Usa el Google Chrome instalado en Windows mediante `channel="chrome"`.
- No descarga ni incluye un navegador Chromium adicional.
- El perfil persistente y las evidencias quedan en `%LOCALAPPDATA%\SIEROOM\DesktopAgent`.
- Fase 1 es exclusivamente de lectura.

## Validación automatizada

El workflow:
1. instala dependencias;
2. compila los módulos Python;
3. genera un `.exe` de un solo archivo;
4. verifica que el ejecutable exista;
5. publica el ejecutable como artefacto descargable de GitHub Actions.
