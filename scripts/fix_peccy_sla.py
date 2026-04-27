"""Atrasa Fecha_Ultima_Visita de algunos médicos de Peccy para generar alertas SLA."""

import os
import sys
from datetime import date, timedelta
from dotenv import load_dotenv
import boto3

load_dotenv()

REGION = os.environ["AWS_REGION"]
PROFILE = os.environ.get("AWS_PROFILE")
MEDICOS_TABLE = os.environ["MEDICOS_TABLE_NAME"]
VISITAS_TABLE = os.environ["VISITAS_TABLE_NAME"]

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
ddb = session.resource("dynamodb")
medicos_table = ddb.Table(MEDICOS_TABLE)
visitas_table = ddb.Table(VISITAS_TABLE)

CADENCIA_DIAS = {"Mensual": 30, "Trimestral": 90, "Semestral": 180, "Anual": 365}

today = date.today()

# (MN, cadencia, dias_extra_vencido)
MEDICOS_TO_BREACH = [
    (550101, "Mensual", 45),    # Kreutzer, Gastro
    (550103, "Mensual", 25),    # Estévez, Neuro
    (550106, "Mensual", 12),    # Quiroga, Pediatría
    (550109, "Mensual", 35),    # Ibáñez, Urología
    (550102, "Trimestral", 20), # Vidal, Dermato
    (550104, "Trimestral", 15), # Paz, Psiquiatría
    (550107, "Trimestral", 8),  # Rivas, Endocrino
    (550105, "Semestral", 30),  # Mansilla, Clínica Médica
]

print(f"Fecha de referencia: {today}")
print(f"Atrasando Fecha_Ultima_Visita de {len(MEDICOS_TO_BREACH)} médicos...\n")

breached_mns = set()
for mn, cadencia, dias_vencido in MEDICOS_TO_BREACH:
    intervalo = CADENCIA_DIAS[cadencia]
    nueva_fecha = today - timedelta(days=intervalo + dias_vencido)
    fecha_str = nueva_fecha.isoformat()

    medicos_table.update_item(
        Key={"Medico_MN": mn},
        UpdateExpression="SET Fecha_Ultima_Visita = :f",
        ExpressionAttributeValues={":f": fecha_str},
    )
    breached_mns.add(mn)

    dias_desde = (today - nueva_fecha).days
    print(f"  MN {mn} ({cadencia}): Fecha_Ultima_Visita -> {fecha_str} "
          f"({dias_desde}d atras, {dias_vencido}d vencido)")

# Eliminar visitas recientes de estos médicos para no contradecir
cutoff = (today - timedelta(days=60)).isoformat()
print(f"\nEliminando visitas recientes (despues de {cutoff}) de medicos con SLA breach...")

resp = visitas_table.scan(
    FilterExpression="APM = :apm",
    ExpressionAttributeValues={":apm": "Peccy"},
)
items = resp["Items"]
while "LastEvaluatedKey" in resp:
    resp = visitas_table.scan(
        FilterExpression="APM = :apm",
        ExpressionAttributeValues={":apm": "Peccy"},
        ExclusiveStartKey=resp["LastEvaluatedKey"],
    )
    items.extend(resp["Items"])

deleted = 0
for item in items:
    mn = item.get("Medico_MN")
    fecha = item.get("Fecha_Visita", "")
    if mn in breached_mns and fecha >= cutoff:
        visitas_table.delete_item(Key={"Visita_ID": item["Visita_ID"]})
        deleted += 1

print(f"  Eliminadas {deleted} visitas recientes")
print("\nListo. Las alertas SLA deberian aparecer en el dashboard de Peccy.")
