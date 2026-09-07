# SIEROOM Desktop Agent — Architecture v0.1

## Objetivo
Crear un agente local para Windows que automatice de forma verificable los flujos docentes de Google Classroom y SIEweb, reutilizando la lógica estable del proyecto actual y reduciendo la dependencia del Classroom Bridge.

## Principios
- API oficial cuando exista y cubra la acción.
- Navegador automatizado para acciones no disponibles por API.
- DOM/accesibilidad antes que coordenadas de pantalla.
- Visión de pantalla como mecanismo de respaldo.
- Toda escritura debe tener verificación posterior.
- Nunca declarar éxito si no existe evidencia verificable.
- Mantener separadas la decisión pedagógica y la ejecución técnica.

## Fase 1 — solo lectura
1. Iniciar navegador con perfil persistente dedicado.
2. Detectar Classroom, SIEweb u otro sitio.
3. Leer URL, título y elementos semánticos básicos sin modificar nada.
4. Generar un reporte estructurado.
5. Guardar evidencia local de la lectura.
6. No realizar ninguna escritura.

## Capas previstas
1. Skill docente/CNEB.
2. Orquestador local.
3. Adaptadores Classroom API, Classroom Browser y SIEweb Browser.
4. Browser Controller con perfil persistente.
5. Fallback visual.
6. Verificador posterior a cada escritura.
7. Audit Log.

## Seguridad
- Credenciales y cookies nunca se guardan en Git.
- Perfil de navegador exclusivo para automatización docente.
- Toda escritura futura deberá ser verificable.
