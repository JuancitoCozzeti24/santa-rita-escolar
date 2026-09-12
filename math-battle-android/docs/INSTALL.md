# Instalación y futuras actualizaciones

## Primera instalación oficial

La nueva aplicación usa el paquete `pe.profejohnny.mathbattle` y una firma nueva.

1. Desinstala **Batalla Matemática** anterior.
2. Descarga `Math-Battle-v1.0.0-release.apk` desde la entrega oficial del profesor.
3. En Android, autoriza temporalmente **Instalar apps desconocidas** para el navegador o gestor de archivos usado.
4. Abre el APK, pulsa **Instalar** y luego revoca ese permiso si ya no lo necesitas.
5. Abre **Math Battle** e inicia sesión con la cuenta institucional.

La desinstalación borra los perfiles locales de la versión anterior; los nuevos récords quedan en Firebase y reaparecen al iniciar sesión.

## Futuras actualizaciones

No vuelvas a desinstalar Math Battle. Instala la nueva APK encima de la versión actual. Esto funciona siempre que:

- `applicationId` siga siendo `pe.profejohnny.mathbattle`;
- `versionCode` aumente en cada publicación;
- todas las APK se firmen con el mismo archivo `math-battle-release.jks` y el mismo alias.

Guarda dos copias cifradas del keystore y sus contraseñas en ubicaciones separadas. Si se pierde la clave, Android no permitirá actualizar la app instalada y habrá que desinstalarla nuevamente.

## Comprobación rápida antes de distribuir

- Instalar en un dispositivo sin la versión anterior.
- Entrar con una cuenta de prueba de cada sección.
- Confirmar que un correo no puede escoger el nombre de otro alumno.
- Jugar hasta enviar un resultado y comprobar el ranking.
- Apagar la pantalla durante una partida y confirmar que esta termina.
- Probar actualización sobre una compilación anterior firmada con el mismo keystore.
