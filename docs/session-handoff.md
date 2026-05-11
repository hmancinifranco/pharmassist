# Session Handoff — PharmAssist Road to Prod

> Estado actual del proyecto y prompt para retomar la próxima sesión.
> Actualizar este archivo al finalizar cada spec.

---

## Último spec completado

**Spec #1: `data-sources-simulation`** — 🟢 Completado

### Qué se hizo
- CDK `DataSourcesStack` desplegado en AWS (26 recursos: VPC, RDS PostgreSQL 16, EC2 Bastion SSM, 4 VPC Endpoints)
- 4 schemas creados: `crm_interno` (25 tablas), `closeup` (10 tablas), `iqvia` (13 tablas), `maestros` (3 tablas)
- Datos sintéticos generados en modo light (~200K rows, 77 segundos)
- 4 queries de validación cross-source pasando correctamente
- Acceso via SSM port forwarding documentado en `scripts/seed_data/README.md`

### Recursos AWS activos
- **RDS**: `datasourcesstack-simulationdb9560a620-diqktfbdpi8c.cklwkim2wac0.us-east-1.rds.amazonaws.com`
- **Bastion**: `i-0119c771904f9fab1`
- **VPC**: `vpc-0a5b25a15e99ddc8d` (CIDR 10.100.0.0/16)
- **Secret**: `SimulationDbSecret0E6814AB-bV1DNRjY9REg`
- **Costo**: ~$47/mes (destruible con `cdk destroy DataSourcesStack`)

### Archivos clave creados
```
infrastructure/stacks/data_sources_stack.py    ← CDK stack
infrastructure/app_datasources.py              ← Entry point solo para este stack
scripts/seed_data/                             ← Scripts de seed completos
  ├── run_seed.py                              ← Ejecutar: python run_seed.py
  ├── validate.py                              ← Validar: python validate.py
  ├── schemas/*.sql                            ← DDL de los 4 schemas
  └── generators/*.py                          ← Generadores con execute_values
```

### Lecciones aprendidas
- `executemany` es 50x más lento que `execute_values` a través de túnel SSM
- CDK no puede sintetizar stacks con Lambda bundling si `pip` no está en PATH → usar `app_datasources.py` separado
- SSM tunnel tiene idle timeout → mantener conexión activa durante seeds largos
- Modo `light` en config.py para validación rápida, modo `full` para volúmenes productivos

---

## Próximo spec

**Spec #2: `data-lake-foundation`** — 🔴 Not started

### Scope
- S3 bucket `pharmassist-lake` con estructura de prefijos (crm/, closeup/, iqvia/, maestros/)
- Glue Database registrada en Data Catalog
- Configuración base para tablas Iceberg
- CDK: nuevo stack `DataLakeStack` o constructs dentro del existente
- Lifecycle rules, encryption, tags

### Dependencias
- Requiere: Spec #1 ✅ (los datos en RDS que DMS va a replicar)
- Bloquea: Spec #3 (ingestion-dms), Spec #4 (maestros-integration)

---
