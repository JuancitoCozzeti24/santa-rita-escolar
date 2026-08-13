# Auditoría de cobertura Classroom — v0.5.0

## Recursos de la API oficial cubiertos directamente

- courses + aliases + gradingPeriodSettings
- announcements
- courseWork
- courseWork.rubrics
- courseWork.studentSubmissions (lectura, patch de notas y return docente)
- courseWorkMaterials
- studentGroups + studentGroupMembers
- students
- teachers
- topics
- invitations
- userProfiles
- userProfiles.guardianInvitations
- userProfiles.guardians

## Recursos deliberadamente no activados

### registrations (Push notifications)
La API los soporta, pero necesitan Google Cloud Pub/Sub, permiso de publicación para el servicio de Classroom y un consumidor. No aportan control interactivo inmediato hasta configurar esa infraestructura.

### AddOnAttachments
Son la arquitectura de Classroom Add-ons, no los adjuntos normales Drive/link que ya usa este MCP. Requieren scopes específicos (`classroom.addons.teacher/student`), tokens y configuración de add-on/Marketplace. No se mezclan con este conector general para no introducir permisos y complejidad innecesarios.

### turnIn / reclaim / modifyAttachments de StudentSubmission
Son operaciones del flujo del estudiante o de propiedad de la entrega. El MCP docente no las presenta como acciones normales para evitar actuar como el estudiante. Se pueden evaluar en un módulo separado si existe un caso de uso legítimo.

## Límites no solucionables solo con API oficial

- Comentarios privados de entregas: no expuestos.
- Escritura de puntajes por criterio de rúbrica: no expuesta.
- Nota global calculada del curso: no expuesta como valor general editable.
- Restricción por `associatedWithDeveloper`: CourseWork creado manualmente o por otro proyecto puede ser de solo lectura para ciertas escrituras.

## Decisión de diseño MCP

Las operaciones de Classroom están agrupadas por familia de recursos para reducir el número de herramientas y mejorar la selección por parte del modelo. Se mantienen aliases explícitos para las operaciones más frecuentes.
