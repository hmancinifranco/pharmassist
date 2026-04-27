# Security Policy

## Supported versions

Este es un proyecto MVP publicado con fines de referencia y aprendizaje. No se
publican versiones etiquetadas; los issues y parches se aplican contra `main`.

## Reportar una vulnerabilidad

Si encontrás una vulnerabilidad de seguridad:

1. **No abras un issue público**. Los issues públicos no son el canal apropiado
   para vulnerabilidades sin parchar.
2. Abrí un [security advisory privado en GitHub](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
   o mandá un correo al mantenedor del repositorio.
3. Incluí pasos de reproducción, impacto estimado y (si es posible) un parche
   sugerido.

Vamos a responder en menos de 7 días y a coordinar la publicación del fix.

## Buenas prácticas para quien forkea o deploya este repo

Este proyecto es un MVP — si lo usás como base para algo productivo, revisá al
menos los siguientes puntos antes de ir a producción:

### Secretos y configuración

- Nunca commitees `.env` ni `.bedrock_agentcore.yaml` (ya están en `.gitignore`).
- Usá valores fuertes y únicos para `DEMO_USER_PASSWORD`, `DEMO_USER_2_PASSWORD`
  y `PECCY_PASSWORD`. Rotá estas credenciales tras cada demo.
- Rotá regularmente el pool de usuarios Cognito o habilitá MFA.
- No reutilices el mismo password entre usuarios demo.

### AWS

- Habilitá MFA obligatorio en el usuario root y en usuarios IAM con permisos
  elevados.
- Usá `cdk diff` y `cdk synth` antes de cada deploy para revisar cambios.
- Restringí los permisos de ejecución del agente al mínimo necesario (acceso
  de lectura a las tablas DynamoDB y `bedrock:InvokeModel` al modelo configurado).
- Habilitá CloudTrail, GuardDuty y AWS Config en la cuenta de producción.
- Los buckets S3 del frontend deben bloquear acceso público salvo por la
  distribución CloudFront configurada.

### Cognito y auth

- Habilitá Advanced Security Features en Cognito User Pool para detección de
  credenciales comprometidas.
- Configurá una política de contraseñas fuerte (mínimo 12 caracteres, mayúsculas,
  minúsculas, dígitos y símbolos).
- Revisá regularmente los User Pool users y borrá usuarios de demo que no
  estén en uso.

### Datos

- Los CSVs incluidos en este repo (`crm_medicos.csv`, `apm_visitas.csv`,
  `ventas_reportadas.csv`) contienen **datos sintéticos**. No contienen
  información de médicos o pacientes reales.
- Si reemplazás estos CSVs con datos reales, asegurate de cumplir con las
  regulaciones locales de protección de datos (en Argentina: Ley 25.326).
  Evaluá encriptación en reposo y control de acceso a nivel de fila.

### Dependencias

- Ejecutá `npm audit` en `frontend/` y `pip list --outdated` en `backend/`,
  `infrastructure/`, `agentcore/` y `bidiagent/` regularmente.
- Pineá versiones concretas en `requirements.txt` cuando sea crítico.

### Web search (DDGS)

- `ddgs` hace requests no autenticados contra motores de búsqueda públicos.
  No se envían datos sensibles de médicos, solo consultas por nombre y
  especialidad. Revisá este flujo si manejás datos regulados.
