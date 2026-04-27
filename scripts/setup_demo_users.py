"""Setup two demo APM users for PharmAssist.

This script bootstraps two Cognito users + DynamoDB data so you can log in
immediately after `cdk deploy`. All identifying data (names, emails, passwords)
is read from environment variables — nothing is hardcoded.

Steps:

1. Rename an existing "Valentina Pérez" APM (if present in DDB/Cognito) to
   ``DEMO_USER_APM_ID`` so the assigned médicos/visitas move to the new APM.
2. Create a second demo user (``DEMO_USER_2_*``) with 20 médicos reassigned
   from other APMs plus ~60 visitas spread across April–May 2026.

Usage:
    source .env
    python scripts/setup_demo_users.py

Required env vars:
    AWS_REGION, USER_POOL_ID,
    MEDICOS_TABLE_NAME, VISITAS_TABLE_NAME, PLANIFICADAS_TABLE_NAME,
    DEMO_USER_EMAIL, DEMO_USER_PASSWORD, DEMO_USER_APM_ID (default "Demo APM 1"),
    DEMO_USER_2_EMAIL, DEMO_USER_2_PASSWORD, DEMO_USER_2_APM_ID (default "Demo APM 2").

Optional:
    AWS_PROFILE, PREVIOUS_APM_NAME (default "Valentina Pérez").
"""

import os
import random
import sys
from datetime import datetime

import boto3
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"ERROR: {name} is required in the environment (.env).")
        sys.exit(1)
    return val


REGION = _required("AWS_REGION")
PROFILE = os.environ.get("AWS_PROFILE")
USER_POOL_ID = _required("USER_POOL_ID")
MEDICOS_TABLE = _required("MEDICOS_TABLE_NAME")
VISITAS_TABLE = _required("VISITAS_TABLE_NAME")
PLANIFICADAS_TABLE = _required("PLANIFICADAS_TABLE_NAME")

PREVIOUS_APM_NAME = os.environ.get("PREVIOUS_APM_NAME", "Valentina Pérez")

USER_1_EMAIL = _required("DEMO_USER_EMAIL")
USER_1_PASSWORD = _required("DEMO_USER_PASSWORD")
USER_1_APM_ID = os.environ.get("DEMO_USER_APM_ID", "Demo APM 1")

USER_2_EMAIL = _required("DEMO_USER_2_EMAIL")
USER_2_PASSWORD = _required("DEMO_USER_2_PASSWORD")
USER_2_APM_ID = os.environ.get("DEMO_USER_2_APM_ID", "Demo APM 2")


session = boto3.Session(profile_name=PROFILE, region_name=REGION)
cognito = session.client("cognito-idp")
ddb = session.resource("dynamodb")

medicos_table = ddb.Table(MEDICOS_TABLE)
visitas_table = ddb.Table(VISITAS_TABLE)
planificadas_table = ddb.Table(PLANIFICADAS_TABLE)


# ─── Step 1: Rename previous APM → USER_1_APM_ID in Cognito ─────────────

def rename_cognito_user() -> None:
    print(f"Updating Cognito user {USER_1_EMAIL}: apm_id → {USER_1_APM_ID}")
    try:
        cognito.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=USER_1_EMAIL,
            UserAttributes=[{"Name": "custom:apm_id", "Value": USER_1_APM_ID}],
        )
        print("  ✓ Cognito updated")
    except cognito.exceptions.UserNotFoundException:
        print(f"  ⚠ User {USER_1_EMAIL} not found, skipping Cognito rename")


# ─── Step 2: Rename previous APM → USER_1_APM_ID in DynamoDB ────────────

def rename_apm_in_medicos() -> None:
    print(f"Renaming APM in medicos table ({PREVIOUS_APM_NAME} → {USER_1_APM_ID})...")
    resp = medicos_table.scan(
        FilterExpression="APM = :apm",
        ExpressionAttributeValues={":apm": PREVIOUS_APM_NAME},
    )
    count = 0
    for item in resp["Items"]:
        medicos_table.update_item(
            Key={"Medico_MN": item["Medico_MN"]},
            UpdateExpression="SET APM = :new",
            ExpressionAttributeValues={":new": USER_1_APM_ID},
        )
        count += 1
    print(f"  ✓ Updated {count} medicos")


def rename_apm_in_visitas() -> None:
    print(f"Renaming APM in visitas table ({PREVIOUS_APM_NAME} → {USER_1_APM_ID})...")
    resp = visitas_table.scan(
        FilterExpression="APM = :apm",
        ExpressionAttributeValues={":apm": PREVIOUS_APM_NAME},
    )
    items = resp["Items"]
    count = 0
    for item in items:
        visitas_table.update_item(
            Key={"Visita_ID": item["Visita_ID"]},
            UpdateExpression="SET APM = :new",
            ExpressionAttributeValues={":new": USER_1_APM_ID},
        )
        count += 1
    while "LastEvaluatedKey" in resp:
        resp = visitas_table.scan(
            FilterExpression="APM = :apm",
            ExpressionAttributeValues={":apm": PREVIOUS_APM_NAME},
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        for item in resp["Items"]:
            visitas_table.update_item(
                Key={"Visita_ID": item["Visita_ID"]},
                UpdateExpression="SET APM = :new",
                ExpressionAttributeValues={":new": USER_1_APM_ID},
            )
            count += 1
    print(f"  ✓ Updated {count} visitas")


def rename_apm_in_planificadas() -> None:
    print(f"Renaming APM in planificadas table ({PREVIOUS_APM_NAME} → {USER_1_APM_ID})...")
    resp = planificadas_table.scan(
        FilterExpression="APM = :apm",
        ExpressionAttributeValues={":apm": PREVIOUS_APM_NAME},
    )
    count = 0
    for item in resp["Items"]:
        old_key = {"APM_Fecha": item["APM_Fecha"], "Medico_MN": item["Medico_MN"]}
        new_item = dict(item)
        new_item["APM"] = USER_1_APM_ID
        new_item["APM_Fecha"] = item["APM_Fecha"].replace(PREVIOUS_APM_NAME, USER_1_APM_ID)
        planificadas_table.delete_item(Key=old_key)
        planificadas_table.put_item(Item=new_item)
        count += 1
    print(f"  ✓ Updated {count} planificadas")


# ─── Step 3: Create second demo user in Cognito ─────────────────────────

def create_user_2_cognito() -> None:
    print(f"Creating Cognito user: {USER_2_EMAIL}")
    try:
        cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=USER_2_EMAIL,
            UserAttributes=[
                {"Name": "email", "Value": USER_2_EMAIL},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:apm_id", "Value": USER_2_APM_ID},
            ],
            TemporaryPassword=USER_2_PASSWORD,
            MessageAction="SUPPRESS",
        )
        cognito.admin_set_user_password(
            UserPoolId=USER_POOL_ID,
            Username=USER_2_EMAIL,
            Password=USER_2_PASSWORD,
            Permanent=True,
        )
        print("  ✓ Cognito user created with permanent password")
    except cognito.exceptions.UsernameExistsException:
        print("  ⚠ User already exists, updating apm_id")
        cognito.admin_update_user_attributes(
            UserPoolId=USER_POOL_ID,
            Username=USER_2_EMAIL,
            UserAttributes=[{"Name": "custom:apm_id", "Value": USER_2_APM_ID}],
        )


# ─── Step 4: Seed DynamoDB data for the second demo user ───────────────

def get_existing_medicos_sample() -> list:
    """Get medicos NOT assigned to USER_1_APM_ID to reassign to USER_2_APM_ID."""
    resp = medicos_table.scan(
        FilterExpression="APM <> :apm",
        ExpressionAttributeValues={":apm": USER_1_APM_ID},
        Limit=200,
    )
    return resp["Items"]


def assign_medicos_to_user_2() -> list:
    print(f"Assigning medicos to {USER_2_APM_ID}...")
    all_other = get_existing_medicos_sample()
    sample = random.sample(all_other, min(20, len(all_other)))

    count = 0
    for i, item in enumerate(sample):
        updates = "SET APM = :apm"
        values = {":apm": USER_2_APM_ID}

        # Give some medicos upcoming birthdays
        if i < 5:
            bday_day = random.randint(10, 28)
            bday_month = 4 if i < 3 else 5
            updates += ", Fecha_Nacimiento = :bday"
            values[":bday"] = f"1975-{bday_month:02d}-{bday_day:02d}"

        cadencias = ["Mensual", "Mensual", "Trimestral", "Trimestral", "Semestral"]
        if i < len(cadencias):
            updates += ", Cadencia = :cad"
            values[":cad"] = cadencias[i]

        medicos_table.update_item(
            Key={"Medico_MN": item["Medico_MN"]},
            UpdateExpression=updates,
            ExpressionAttributeValues=values,
        )
        count += 1
    print(f"  ✓ Assigned {count} medicos to {USER_2_APM_ID}")
    return [item["Medico_MN"] for item in sample]


def create_visitas_for_user_2(medico_mns: list) -> None:
    print(f"Creating visitas for {USER_2_APM_ID} (April + May 2026)...")
    next_id = 90000
    count = 0
    zonas = ["Palermo", "Belgrano", "Recoleta", "Caballito", "Flores"]
    tipos = ["Presencial", "Presencial", "Presencial", "Virtual", "Telefónica"]
    productos = [
        "PAMOXET 500mg", "CARDIOLEX 10mg", "DERMACORT Crema",
        "GASTROZOL 20mg", "NEUROFEN 400mg", "VITAMAX Complex",
    ]

    for mn in medico_mns:
        num_visitas = random.randint(2, 4)
        for v in range(num_visitas):
            month = random.choice([4, 5])
            day = random.randint(1, 28)
            if v == 0 and random.random() < 0.3:
                fecha = datetime.now().strftime("%Y-%m-%d")
            else:
                fecha = f"2026-{month:02d}-{day:02d}"

            visitas_table.put_item(Item={
                "Visita_ID": next_id,
                "APM": USER_2_APM_ID,
                "Medico_MN": mn,
                "Fecha_Visita": fecha,
                "Zona": random.choice(zonas),
                "Tipo_Visita": random.choice(tipos),
                "Productos_Presentados": ", ".join(random.sample(productos, random.randint(1, 3))),
                "Notas": "",
            })
            next_id += 1
            count += 1
    print(f"  ✓ Created {count} visitas for {USER_2_APM_ID}")


# ─── Main ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PharmAssist Demo Users Setup")
    print("=" * 60)

    print(f"\n--- Renaming {PREVIOUS_APM_NAME} → {USER_1_APM_ID} ---")
    rename_cognito_user()
    rename_apm_in_medicos()
    rename_apm_in_visitas()
    rename_apm_in_planificadas()

    print(f"\n--- Creating {USER_2_APM_ID} ---")
    create_user_2_cognito()
    medico_mns = assign_medicos_to_user_2()
    create_visitas_for_user_2(medico_mns)

    print("\n" + "=" * 60)
    print("Done! Demo users ready:")
    print(f"  1. {USER_1_APM_ID}  → {USER_1_EMAIL}")
    print(f"  2. {USER_2_APM_ID}  → {USER_2_EMAIL}")
    print("  (passwords from .env, not printed)")
    print("=" * 60)
