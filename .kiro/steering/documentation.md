---
inclusion: auto
description: Reglas para mantener la documentación sincronizada cuando se hacen cambios al proyecto
---

# Mantenimiento de Documentación

## Regla: Mantener documentación sincronizada con cambios

Cuando se hacen cambios funcionales al proyecto, actualizar la documentación afectada:

| Cambio | Documentos a revisar |
|--------|---------------------|
| Nuevo endpoint API / Lambda | `README.md`, steering `structure.md` |
| Nuevo componente React / página | steering `structure.md` |
| Nuevo agente Strands o tool | steering `structure.md`, steering `agent-development.md` |
| Nuevo servicio AWS usado | `README.md`, steering `tech.md`, steering `deployment.md` |
| Cambio en estructura de archivos | steering `structure.md` |
| Nuevo flujo de usuario | steering `product.md` |
| Cambio en proceso de build/deploy | steering `deployment.md` |
| Nueva dependencia importante | steering `tech.md` (dependencias) |
| Cambio en modelo de datos / tablas DynamoDB | steering `product.md`, steering `agent-development.md` |
| Nuevo producto o zona | steering `product.md`, steering `tech.md` |
| Cambio en CDK stack / constructs | steering `structure.md`, steering `deployment.md` |
| Nueva variable de entorno | steering `deployment.md` (tabla de variables) |
| Cambio en AgentCore config | steering `deployment.md`, steering `agent-development.md` |
| Cambio en módulos compartidos backend↔agentcore | steering `agent-development.md` (sincronización) |

## Consistencia

- Nombre del proyecto: siempre "PharmAssist" (PascalCase)
- Nombre del paquete frontend: `pharmassist-frontend`
- Nombre del paquete backend: `pharmassist-backend`
- Servicios AWS: referir por nombre oficial (Amazon Bedrock, Amazon DynamoDB, Amazon Bedrock AgentCore)
- Agentes: referir como "agentes Strands" o "Strands Agents"
- Usuarios: referir como "APM" o "visitador médico"
- Idioma de la UI y documentación de usuario: español argentino
- Idioma de código y comentarios técnicos: inglés (variables, funciones) con comentarios en español donde aclare dominio
- Variables de entorno: siempre documentadas en `.env.example` y en steering `deployment.md`
- Model IDs de Bedrock: siempre via `.env`, nunca hardcodeados
