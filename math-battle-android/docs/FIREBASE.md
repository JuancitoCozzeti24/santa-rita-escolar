# Configuración Firebase

## Servicios requeridos

1. Crear o elegir un proyecto Firebase.
2. Registrar la app Android `pe.profejohnny.mathbattle` con SHA-1 y SHA-256 del keystore oficial.
3. Activar Authentication → Google.
4. Crear Firestore en ubicación cercana a Perú (según disponibilidad del proyecto).
5. Mantener el plan Spark. La aplicación trabaja directamente con Firestore y sus reglas de seguridad.

## Despliegue

Desde la raíz del proyecto:

```bash
npm install -g firebase-tools
firebase login
firebase use <PROJECT_ID>
firebase deploy --only firestore
```

## Importación de matrícula

El CSV usa las columnas `externalCode,fullName,publicName,section`. Puede contener una columna `email`, pero el importador no la sube a Firestore. Nunca se debe almacenar el CSV real en Git.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/ruta/segura/firebase-admin-key.json
node scripts/import-roster.mjs private/roster.csv
```

Antes de importar, verifica que haya exactamente 107 estudiantes activos: 28 en 2A, 28 en 2B, 25 en 5A y 26 en 5B.

## Administración del ranking

La cuenta `profejohnnyb@gmail.com` es la propietaria. Cuando ingresa a la app puede eliminar un participante o reiniciar el ranking del aula seleccionada. Estas acciones requieren confirmación.

El ranking conserva el mejor puntaje de cada estudiante. Si dos resultados tienen el mismo puntaje, queda primero el de menor duración. También almacena la hora de inicio, la hora final y el tiempo transcurrido informado por Android.

## Secretos de GitHub Actions

- `FIREBASE_APPLICATION_ID`
- `FIREBASE_API_KEY`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_STORAGE_BUCKET`
- `WEB_CLIENT_ID`
- `MATH_BATTLE_KEYSTORE_BASE64`
- `MATH_BATTLE_STORE_PASSWORD`
- `MATH_BATTLE_KEY_ALIAS`
- `MATH_BATTLE_KEY_PASSWORD`

El keystore se convierte una sola vez con `base64 -w0 math-battle-release.jks`. No publiques esa cadena en issues, logs ni archivos.
