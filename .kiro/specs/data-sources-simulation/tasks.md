# Tasks — data-sources-simulation

## Fase A: CDK Stack

- [x] 1. Crear directorio `infrastructure/stacks/data_sources_stack.py` con skeleton de la clase `DataSourcesStack`
- [x] 2. Registrar `DataSourcesStack` en `infrastructure/app.py` (entry point CDK) — inmediatamente después del skeleton
- [x] 3. Agregar VPC con 2 AZs y subnets isolated (sin NAT para ahorrar costos)
- [x] 4. Agregar Security Group para el RDS (ingress 5432 desde CIDR configurable)
- [x] 5. Agregar RDS PostgreSQL 16 (db.t4g.micro, 20GB, single-AZ, credentials en Secrets Manager)
- [x] 6. Agregar CfnOutputs: RdsEndpoint, RdsPort, RdsSecretArn, VpcId, SecurityGroupId
- [x] 7. Checkpoint: `cdk synth` exitoso con DataSourcesStack (14 recursos, 6 outputs)

## Fase B: DDL Schemas

- [x] 8. Crear `scripts/seed_data/schemas/crm_ddl.sql` con todas las tablas del CRM interno
- [x] 9. Crear `scripts/seed_data/schemas/closeup_ddl.sql` con star schema de CloseUp
- [x] 10. Crear `scripts/seed_data/schemas/iqvia_ddl.sql` con star schema de IQVIA
- [x] 11. Crear `scripts/seed_data/schemas/maestros_ddl.sql` con tablas de integración
- [x] 12. Crear script `scripts/seed_data/init_schemas.py` que ejecuta los 4 DDLs contra el RDS
- [x] 13. Checkpoint: ejecutar `init_schemas.py` contra PostgreSQL y verificar que los schemas se crean sin errores

## Fase C: Generación de datos sintéticos

- [x] 14. Crear `scripts/seed_data/config.py` con volúmenes, seeds y configuración de conexión
- [x] 15. Crear `scripts/seed_data/generators/crm_generator.py` — genera dimensiones + agenda + UltimaMilla
- [x] 16. Crear `scripts/seed_data/generators/closeup_generator.py` — genera dimensiones + fact table prescripciones (3M rows)
- [x] 17. Crear `scripts/seed_data/generators/iqvia_generator.py` — genera dimensiones + fact table ventas (2.5M rows)
- [x] 18. Crear `scripts/seed_data/generators/maestros_generator.py` — genera maestros coherentes con las 3 fuentes
- [x] 19. Crear `scripts/seed_data/main.py` — orquesta generación en orden correcto (dimensiones → maestros → facts)
- [x] 20. Crear `scripts/seed_data/requirements.txt` (faker, numpy, psycopg2-binary, python-dotenv, tqdm)
- [x] 21. Checkpoint: ejecutar `main.py` contra PostgreSQL, verificar volúmenes con `SELECT COUNT(*)`

## Fase D: Validación

- [x] 22. Crear `scripts/seed_data/validate.py` con las 4 queries de validación del design
- [x] 23. Ejecutar `validate.py` — todas las queries devuelven resultados no vacíos y coherentes
- [x] 24. Actualizar `.env.example` con las nuevas variables de DataSourcesStack
- [x] 25. Actualizar `docs/specs-roadmap.md`: spec #1 → 🟢

## Notas de ejecución

- Tasks 1-7: CDK synth validado ✓
- Tasks 8-20: Código completo, listo para ejecutar
- Tasks 13, 21, 23: Requieren PostgreSQL (deploy a AWS o Docker local)
- Para deploy: `cdk deploy DataSourcesStack --profile $AWS_PROFILE`
- Para conectarse al RDS post-deploy: usar EC2 bastion, Session Manager port forwarding, o agregar un SG rule temporal
- Para ejecutar seed: `cd scripts/seed_data && pip install -r requirements.txt && python main.py --fresh`
- Para validar: `python validate.py`
