# Configuración Firebase

## Servicios requeridos

1. Crear o elegir un proyecto Firebase.
2. Registrar la app Android `pe.profejohnny.mathbattle` con SHA-1 y SHA-256 del keystore oficial.
3. Activar Authentication → Google.
4. Crear Firestore en ubicación cercana a Perú (según disponibilidad del proyecto).
5. Habilitar App Check para Android con Play Integrity. Durante pruebas, registrar únicamente los tokens debug autorizados. Como la primera distribución será por APK lateral y no por Google Play, las funciones aceptan temporalmente solicitudes sin atestación, pero siguen exigiendo Google Auth verificado. Activa `enforceAppCheck: true` al publicar mediante Play Console.
6. Habilitar Cloud Functions y vincular una cuenta de facturación si Firebase lo solicita.

## Despliegue

Desde la raíz del proyecto:

```bash
npm install -g firebase-tools
firebase login
firebase use <PROJECT_ID>
cd functions && npm ci && npm run build && cd ..
firebase deploy --only functions,firestore
```

## Importación de matrícula

El CSV debe usar las columnas `externalCode,fullName,publicName,section,email`. Nunca se debe almacenar en Git.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/ruta/segura/firebase-admin-key.json
node scripts/import-roster.mjs private/roster.csv
```

Antes de importar, verifica que todos los correos correspondan a cuentas institucionales y que haya exactamente 107 estudiantes activos: 28 en 2A, 28 en 2B, 25 en 5A y 26 en 5B.

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
