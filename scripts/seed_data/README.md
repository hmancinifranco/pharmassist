# Seed Data — Simulación de Fuentes Externas

Scripts para crear schemas y generar datos sintéticos en el RDS PostgreSQL
que simula los 3 warehouses externos del laboratorio.

## Prerequisitos

1. **AWS CLI** configurado con tu profile
2. **Session Manager Plugin** instalado:
   ```bash
   # macOS
   brew install --cask session-manager-plugin
   ```
3. **Stack desplegado**: `DataSourcesStack` debe estar deployed
4. **Variables en `.env`**: completar con los outputs del stack

## Deploy del stack

```bash
cd infrastructure
source .venv/bin/activate
source ../.env

# Ver qué se va a crear
cdk diff DataSourcesStack --profile $AWS_PROFILE

# Deploy
cdk deploy DataSourcesStack --profile $AWS_PROFILE
```

Después del deploy, copiar los outputs a tu `.env`:
- `RdsEndpoint` → `DATASOURCES_RDS_ENDPOINT`
- `RdsSecretArn` → `DATASOURCES_RDS_SECRET_ARN`
- `BastionInstanceId` → `DATASOURCES_BASTION_INSTANCE_ID`

## Obtener credenciales del RDS

Las credenciales se guardan en Secrets Manager (nunca en código):

```bash
# Obtener el password del RDS
aws secretsmanager get-secret-value \
    --secret-id $DATASOURCES_RDS_SECRET_ARN \
    --profile $AWS_PROFILE \
    --query 'SecretString' --output text | python3 -c "
import sys, json
secret = json.load(sys.stdin)
print(f'Host: {secret[\"host\"]}')
print(f'Port: {secret[\"port\"]}')
print(f'User: {secret[\"username\"]}')
print(f'Password: {secret[\"password\"]}')
print(f'Database: {secret[\"dbname\"]}')
"
```

Guardar el user y password en tu `.env`:
- `DATASOURCES_DB_USER` ← username del secret
- `DATASOURCES_DB_PASSWORD` ← password del secret

## Conectarse al RDS via SSM Port Forwarding

El RDS está en subnets privadas (sin acceso público). Para conectarte
desde tu máquina local, usás SSM port forwarding a través del bastion:

```bash
# Terminal 1: abrir túnel (deja corriendo)
aws ssm start-session \
    --target $DATASOURCES_BASTION_INSTANCE_ID \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "{\"host\":[\"$DATASOURCES_RDS_ENDPOINT\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}" \
    --profile $AWS_PROFILE
```

Con el túnel abierto, en otra terminal podés conectarte como si fuera local:

```bash
# Terminal 2: conectar con psql
psql -h localhost -p 5432 -U $DATASOURCES_DB_USER -d $DATASOURCES_DB_NAME
```

O ejecutar los scripts de seed:

```bash
# Terminal 2: ejecutar seed (con el túnel abierto)
cd scripts/seed_data

# Asegurar que .env tiene DATASOURCES_RDS_ENDPOINT=localhost (porque el túnel redirige)
# O setear temporalmente:
export DATASOURCES_RDS_ENDPOINT=localhost

pip install -r requirements.txt
python main.py --fresh
```

## Scripts disponibles

| Script | Qué hace |
|--------|----------|
| `main.py --fresh` | Crea schemas + genera todos los datos (~8M rows, ~5 min) |
| `main.py --schema-only` | Solo crea schemas sin datos |
| `init_schemas.py --fresh` | Solo DDL (drop + create schemas) |
| `validate.py` | Ejecuta 4 queries de validación cross-source |

## Volúmenes generados

| Schema | Tabla principal | Rows aprox |
|--------|----------------|-----------|
| crm_interno | agenda | ~80,000 |
| crm_interno | agenda_producto | ~240,000 |
| crm_interno | doctor | 3,000 |
| closeup | prescripcion | ~3,000,000 |
| iqvia | fact_mercado_valor | ~2,500,000 |
| maestros | maestro_medicos | 3,000 |

## Costos estimados

| Recurso | Costo mensual aprox |
|---------|-------------------|
| RDS db.t4g.micro | ~$12 |
| EC2 t4g.nano (bastion) | ~$3 |
| VPC Endpoints (4) | ~$30 |
| Storage (20GB gp3) | ~$2 |
| **Total** | **~$47/mes** |

> Tip: podés destruir el stack cuando no lo uses (`cdk destroy DataSourcesStack`)
> y recrearlo cuando lo necesites. Los datos se regeneran en ~5 min.

## Troubleshooting

### "Unable to start session" al hacer port forwarding
- Verificar que el Session Manager Plugin está instalado
- Verificar que el bastion está running: `aws ec2 describe-instances --instance-ids $DATASOURCES_BASTION_INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name'`
- Verificar que tu IAM user/role tiene permiso `ssm:StartSession`

### "Connection refused" al conectar a PostgreSQL
- Verificar que el túnel SSM está activo (Terminal 1)
- Verificar que usás `localhost` como host (no el endpoint de RDS)
- Verificar que el port 5432 no está ocupado localmente

### Timeout en la generación de datos
- La fact table de prescripciones (3M rows) puede tardar 2-3 minutos
- La fact table de IQVIA (2.5M rows) puede tardar 1-2 minutos
- Total esperado: ~5 minutos para toda la generación
