"""
CSV → DynamoDB loader for PharmAssist.

Parses crm_medicos.csv, apm_visitas.csv, ventas_reportadas.csv,
transforms to DynamoDB item format, and batch-writes to tables.
Also generates visitas_planificadas from CRM cadence data.

Usage:
    python -m data.loader --medicos-table crm_medicos --visitas-table apm_visitas \
        --ventas-table ventas_reportadas --planificadas-table visitas_planificadas
"""

import argparse
import math
import os
import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import boto3
import pandas as pd
from dotenv import load_dotenv

from data.product_catalog import CADENCIA_DIAS, ESPECIALIDAD_PRODUCTOS

load_dotenv()

# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def parse_medicos(csv_path: str) -> list[dict[str, Any]]:
    """Parse crm_medicos.csv into a list of DynamoDB-ready items."""
    df = pd.read_csv(csv_path)
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        item: dict[str, Any] = {
            "Medico_MN": int(row["Medico_MN"]),
            "Nombre": str(row["Nombre"]),
            "Apellido": str(row["Apellido"]),
            "Especialidad_Medica": str(row["Especialidad_Medica"]),
            "Zona": str(row["Zona"]),
            "APM": str(row["APM"]),
            "Cadencia": str(row["Cadencia"]),
        }
        # Optional string fields
        for col in [
            "Mail", "Telefono_Consultorio", "Telefono_Celular",
            "Calle", "Altura", "Barrio", "Fecha_Ultima_Visita",
            "Fecha_Nacimiento", "Hobby_Intereses", "Religion",
            "Hospital", "Facultad",
        ]:
            val = row.get(col)
            if pd.notna(val) and str(val).strip():
                item[col] = str(val).strip()
        # Optional numeric fields
        if pd.notna(row.get("Anio_Egresado")):
            item["Anio_Egresado"] = int(row["Anio_Egresado"])
        if pd.notna(row.get("Latitud")):
            item["Latitud"] = Decimal(str(row["Latitud"]))
        if pd.notna(row.get("Longitud")):
            item["Longitud"] = Decimal(str(row["Longitud"]))
        items.append(item)
    return items


def parse_visitas(csv_path: str) -> list[dict[str, Any]]:
    """Parse apm_visitas.csv into a list of DynamoDB-ready items."""
    df = pd.read_csv(csv_path)
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        item: dict[str, Any] = {
            "Visita_ID": int(row["Visita_ID"]),
            "APM": str(row["APM"]),
            "Medico_MN": int(row["Medico_MN"]),
            "Fecha_Visita": str(row["Fecha_Visita"]),
            "Zona": str(row["Zona"]),
            "Tipo_Visita": str(row["Tipo_Visita"]),
        }
        if pd.notna(row.get("Productos_Presentados")):
            item["Productos_Presentados"] = str(row["Productos_Presentados"])
        if pd.notna(row.get("Notas")):
            item["Notas"] = str(row["Notas"])
        items.append(item)
    return items


def parse_ventas(csv_path: str) -> list[dict[str, Any]]:
    """Parse ventas_reportadas.csv into DynamoDB items with composite keys."""
    df = pd.read_csv(csv_path)
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        zona = str(row["Zona"])
        producto = str(row["Producto"])
        anio = int(row["Anio"])
        mes = int(row["Mes"])
        presentacion = str(row["Presentacion"])
        farmacia = str(row.get("Farmacia", "")) if pd.notna(row.get("Farmacia")) else ""
        # Make sort key unique by appending Presentacion and Farmacia
        anio_mes_key = f"{anio}#{mes:02d}#{presentacion}"
        if farmacia:
            anio_mes_key += f"#{farmacia}"
        item: dict[str, Any] = {
            "Zona_Producto": f"{zona}#{producto}",
            "Anio_Mes": anio_mes_key,
            "Zona": zona,
            "Producto": producto,
            "Anio": anio,
            "Mes": mes,
            "Presentacion": str(row["Presentacion"]),
            "Tipo_OTC_RX": str(row["Tipo_OTC_RX"]),
            "Unidades_Vendidas": int(row["Unidades_Vendidas"]),
            "Valor_Venta_ARS": Decimal(str(round(float(row["Valor_Venta_ARS"]), 2))),
        }
        if pd.notna(row.get("Crecimiento_YoY_Pct")):
            item["Crecimiento_YoY_Pct"] = Decimal(
                str(round(float(row["Crecimiento_YoY_Pct"]), 2))
            )
        if pd.notna(row.get("Farmacia")):
            item["Farmacia"] = str(row["Farmacia"])
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# DynamoDB batch writer
# ---------------------------------------------------------------------------


def batch_write(table_name: str, items: list[dict[str, Any]], region: str, pk_name: str = "", sk_name: str = "") -> int:
    """Write items to a DynamoDB table using batch_write_item. Returns count written.
    
    If pk_name and sk_name are provided, deduplicates items by those keys
    (last occurrence wins) to avoid BatchWriteItem duplicate key errors.
    """
    if pk_name and sk_name:
        seen: dict[tuple, dict[str, Any]] = {}
        for item in items:
            key = (item.get(pk_name), item.get(sk_name))
            seen[key] = item
        items = list(seen.values())

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    written = 0
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Visit generation algorithm
# ---------------------------------------------------------------------------

# Visits per period for each cadencia type
_VISITS_PER_YEAR: dict[str, int] = {
    "Mensual": 12,      # 1 per month
    "Trimestral": 4,    # 1 every 3 months
    "Semestral": 2,     # 1 every 6 months
    "Anual": 1,         # 1 per year
    "Digital": 6,       # 1 every 2 months
}


def _working_days_in_month(year: int, month: int) -> list[date]:
    """Return all Mon-Fri dates in a given month."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    days: list[date] = []
    current = first
    while current <= last:
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            days.append(current)
        current += timedelta(days=1)
    return days


def _months_for_cadencia(cadencia: str, year: int) -> list[int]:
    """Return which months of the year a médico should be visited based on cadencia."""
    if cadencia == "Mensual":
        return list(range(1, 13))
    elif cadencia == "Trimestral":
        return [1, 4, 7, 10]
    elif cadencia == "Semestral":
        return [1, 7]
    elif cadencia == "Anual":
        return [6]  # mid-year
    elif cadencia == "Digital":
        return [1, 3, 5, 7, 9, 11]
    return []


def generate_planned_visits(
    medicos: list[dict[str, Any]],
    year: int,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """
    Generate visitas_planificadas from CRM cadence data.

    For each médico, creates visits in the appropriate months based on Cadencia.
    Distributes visits across working days targeting 3-5 visits/day per APM.
    Digital cadencia → Tipo_Visita = "Virtual" or "Telefónica".
    Populates Productos_Sugeridos from ESPECIALIDAD_PRODUCTOS mapping.

    Returns list of DynamoDB-ready items with composite key APM_Fecha + SK Medico_MN.
    """
    rng = random.Random(seed)

    # Group médicos by APM
    apm_medicos: dict[str, list[dict[str, Any]]] = {}
    for m in medicos:
        apm = m["APM"]
        apm_medicos.setdefault(apm, []).append(m)

    all_visits: list[dict[str, Any]] = []

    for apm, medico_list in apm_medicos.items():
        # Collect all (medico, month) pairs that need a visit this year
        visit_requests: list[tuple[dict[str, Any], int]] = []
        for m in medico_list:
            cadencia = m.get("Cadencia", "Trimestral")
            months = _months_for_cadencia(cadencia, year)
            for month in months:
                visit_requests.append((m, month))

        # Group by month and distribute across working days
        month_requests: dict[int, list[dict[str, Any]]] = {}
        for m, month in visit_requests:
            month_requests.setdefault(month, []).append(m)

        # Pre-pass: merge thin months (< min_per_day) into the nearest
        # adjacent month so no working day ends up below 3 visits.
        min_per_day = 3
        sorted_months = sorted(month_requests.keys())
        merged: dict[int, list[dict[str, Any]]] = {}
        for month in sorted_months:
            medicos_in_month = month_requests[month]
            if len(medicos_in_month) < min_per_day:
                # Find the nearest month that already has >= min_per_day
                best_target: int | None = None
                best_dist = 13
                for other in sorted_months:
                    if other == month:
                        continue
                    target_list = merged.get(other, month_requests[other])
                    if len(target_list) >= min_per_day:
                        dist = abs(other - month)
                        if dist < best_dist:
                            best_dist = dist
                            best_target = other
                if best_target is not None:
                    merged.setdefault(best_target, list(month_requests[best_target]))
                    merged[best_target].extend(medicos_in_month)
                    continue  # skip adding this month standalone
            merged.setdefault(month, list(medicos_in_month))

        for month, month_medicos in merged.items():
            work_days = _working_days_in_month(year, month)
            if not work_days:
                continue

            # Shuffle médicos for even distribution
            rng.shuffle(month_medicos)

            # Target: 3-5 visits per day. Calculate how many days we need.
            max_per_day = 5
            total = len(month_medicos)

            # Use ceiling division to ensure at least min_per_day visits per day
            # days_needed = ceil(total / max_per_day), but also ensure
            # we don't spread so thin that days have < min_per_day
            days_needed_max = max(1, math.ceil(total / min_per_day))
            days_needed_min = max(1, math.ceil(total / max_per_day))
            # Use the fewest days that still keeps each day <= max_per_day
            # but also ensures each day gets >= min_per_day
            days_needed = min(days_needed_max, max(days_needed_min, math.ceil(total / max_per_day)))
            # Clamp: don't use more days than we have visits / min_per_day
            days_needed = min(days_needed, total // min_per_day)
            days_needed = max(1, days_needed)

            # Pick evenly spaced working days
            if days_needed >= len(work_days):
                selected_days = work_days[:]
            else:
                step = len(work_days) / days_needed
                selected_days = [
                    work_days[min(int(i * step), len(work_days) - 1)]
                    for i in range(days_needed)
                ]

            # Distribute médicos across selected days round-robin
            day_idx = 0
            day_counts: dict[int, int] = {i: 0 for i in range(len(selected_days))}

            for m in month_medicos:
                # Find next day that hasn't exceeded max_per_day
                attempts = 0
                while day_counts[day_idx] >= max_per_day and attempts < len(selected_days):
                    day_idx = (day_idx + 1) % len(selected_days)
                    attempts += 1

                visit_date = selected_days[day_idx]
                cadencia = m.get("Cadencia", "Trimestral")
                especialidad = m.get("Especialidad_Medica", "")

                # Determine visit type
                if cadencia == "Digital":
                    tipo = rng.choice(["Virtual", "Telefónica"])
                else:
                    tipo = "Presencial"

                # Get suggested products from specialty mapping
                productos = ESPECIALIDAD_PRODUCTOS.get(especialidad, [])

                visit_item: dict[str, Any] = {
                    "APM_Fecha": f"{apm}#{visit_date.isoformat()}",
                    "Medico_MN": int(m["Medico_MN"]),
                    "APM": apm,
                    "Fecha_Planificada": visit_date.isoformat(),
                    "Zona": m.get("Zona", ""),
                    "Tipo_Visita": tipo,
                    "Productos_Sugeridos": "|".join(productos) if productos else "",
                }
                all_visits.append(visit_item)

                day_counts[day_idx] += 1
                day_idx = (day_idx + 1) % len(selected_days)

    # Deduplicate by (APM_Fecha, Medico_MN) composite key
    seen: set[tuple[str, int]] = set()
    unique_visits: list[dict[str, Any]] = []
    for v in all_visits:
        key = (v["APM_Fecha"], v["Medico_MN"])
        if key not in seen:
            seen.add(key)
            unique_visits.append(v)

    return unique_visits


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load PharmAssist CSVs into DynamoDB and generate planned visits."
    )
    parser.add_argument(
        "--medicos-table",
        default=os.getenv("MEDICOS_TABLE_NAME", "crm_medicos"),
        help="DynamoDB table name for médicos",
    )
    parser.add_argument(
        "--visitas-table",
        default=os.getenv("VISITAS_TABLE_NAME", "apm_visitas"),
        help="DynamoDB table name for visitas",
    )
    parser.add_argument(
        "--ventas-table",
        default=os.getenv("VENTAS_TABLE_NAME", "ventas_reportadas"),
        help="DynamoDB table name for ventas",
    )
    parser.add_argument(
        "--planificadas-table",
        default=os.getenv("PLANIFICADAS_TABLE_NAME", "visitas_planificadas"),
        help="DynamoDB table name for visitas planificadas",
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_DIR", "../data"),
        help="Directory containing CSV files",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", "us-east-1"),
        help="AWS region",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year for visit generation (default: current year)",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Skip CSV loading, only generate planned visits",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip visit generation, only load CSVs",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    region = args.region

    if not args.skip_load:
        # Load médicos
        medicos_path = os.path.join(data_dir, "crm_medicos.csv")
        print(f"Parsing {medicos_path}...")
        medicos_items = parse_medicos(medicos_path)
        print(f"  → {len(medicos_items)} médicos parsed")
        count = batch_write(args.medicos_table, medicos_items, region)
        print(f"  → {count} items written to {args.medicos_table}")

        # Load visitas
        visitas_path = os.path.join(data_dir, "apm_visitas.csv")
        print(f"Parsing {visitas_path}...")
        visitas_items = parse_visitas(visitas_path)
        print(f"  → {len(visitas_items)} visitas parsed")
        count = batch_write(args.visitas_table, visitas_items, region)
        print(f"  → {count} items written to {args.visitas_table}")

        # Load ventas
        ventas_path = os.path.join(data_dir, "ventas_reportadas.csv")
        print(f"Parsing {ventas_path}...")
        ventas_items = parse_ventas(ventas_path)
        print(f"  → {len(ventas_items)} ventas parsed")
        count = batch_write(args.ventas_table, ventas_items, region,
                           pk_name="Zona_Producto", sk_name="Anio_Mes")
        print(f"  → {count} items written to {args.ventas_table}")
    else:
        # Still need medicos for visit generation
        medicos_path = os.path.join(data_dir, "crm_medicos.csv")
        medicos_items = parse_medicos(medicos_path)

    if not args.skip_generate:
        # Generate planned visits
        if args.skip_load:
            medicos_path = os.path.join(data_dir, "crm_medicos.csv")
            medicos_items = parse_medicos(medicos_path)

        print(f"Generating planned visits for {args.year}...")
        planned = generate_planned_visits(medicos_items, args.year)
        print(f"  → {len(planned)} visitas planificadas generated")
        count = batch_write(args.planificadas_table, planned, region,
                           pk_name="APM_Fecha", sk_name="Medico_MN")
        print(f"  → {count} items written to {args.planificadas_table}")

    print("Done.")


if __name__ == "__main__":
    main()
