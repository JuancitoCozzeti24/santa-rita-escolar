# Math Battle

Aplicación Android nativa en Kotlin/Jetpack Compose para las competencias de cálculo mental del colegio Santa Rita de Casia. Reemplaza la antigua WebView y conserva la dinámica de tres niveles del APK v19.

## Flujo del estudiante

1. Pulsa **Entraré a la batalla** y mira la introducción.
2. Inicia sesión con su cuenta Google institucional.
3. Selecciona `2A`, `2B`, `5A` o `5B` y luego su nombre oficial.
4. Cada nombre puede vincularse una sola vez a una cuenta Google.
5. Elige avatar y juega.
6. El mejor resultado se guarda con hora de inicio, hora final y duración. Los empates se ordenan por menor tiempo.

No se muestran correos, códigos internos ni apellidos completos en el ranking.

## Componentes

- `app/`: aplicación Android nativa.
- `firestore.rules`: permisos para trabajar directamente con Firestore en el plan Spark.
- `scripts/import-roster.mjs`: importador administrativo de matrícula (el CSV real nunca se sube a Git).
- `docs/INSTALL.md`: instalación y futuras actualizaciones.
- `docs/FIREBASE.md`: configuración y despliegue.

## Compilación local

Requisitos: JDK 17, Android SDK 35 y Gradle 8.11.1.

```bash
gradle :app:testDebugUnitTest :app:assembleDebug
```

Las variables Firebase se leen del entorno o de `local.properties`:

```properties
FIREBASE_APPLICATION_ID=1:000000000000:android:0000000000000000
FIREBASE_API_KEY=...
FIREBASE_PROJECT_ID=...
FIREBASE_STORAGE_BUCKET=...
WEB_CLIENT_ID=...apps.googleusercontent.com
```

La firma de producción nunca se versiona. Para compilar `release`, define `MATH_BATTLE_KEYSTORE`, `MATH_BATTLE_STORE_PASSWORD`, `MATH_BATTLE_KEY_ALIAS` y `MATH_BATTLE_KEY_PASSWORD`.

## Reglas del juego portadas desde v19

| Nivel | Puntaje | Contenido | Tiempo | Acierto | Error |
|---|---:|---|---:|---:|---:|
| El despertar | 0–29 | Sumas y restas | 10 s | +1.5 s | −1 s |
| El desafío | 30–49 | Potencias de 2 | 12 s | +2 s | −1.5 s |
| Batalla infinita | 50+ | Operaciones combinadas | 15 s | +3 s | −2 s |

## Privacidad

El CSV de matrícula, las claves administrativas y el keystore están incluidos en `.gitignore`. La app exige inicio de sesión con Google. La matrícula publicada en Firestore contiene únicamente el nombre visible, la sección y el estado de vinculación; no contiene correos, códigos internos ni nombres completos.

## Alcance de seguridad

Esta edición está diseñada para práctica escolar y usa el plan Spark sin Cloud Functions. Las reglas impiden que un estudiante elimine registros ajenos y reservan la limpieza del ranking a la cuenta propietaria. Al ejecutarse la lógica de puntaje en el dispositivo, un usuario con conocimientos técnicos podría manipular su propio resultado; la validación final se realiza presencialmente en el aula.
