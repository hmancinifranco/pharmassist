"""Generate synthetic data for the maestros (integration) schema.

This generator runs AFTER crm and closeup generators because it needs
to reference existing IDs from both sources to create coherent mappings.
"""
import random

import numpy as np
from psycopg2.extras import execute_values

from config import (
    NUM_DOCTORS, NUM_CUP_DOCTORS, NUM_PRODUCTS, NUM_CUP_BRANDS,
    NUM_IQVIA_PRODUCTS, NUM_MAESTRO_MEDICOS, NUM_MAESTRO_PRODUCTOS,
    NUM_CUP_MARKETS, NUM_SPECIALTIES, RANDOM_SEED,
)

random.seed(RANDOM_SEED + 100)  # offset seed to avoid correlation
np.random.seed(RANDOM_SEED + 100)


def generate_maestro_medicos(cur):
    """Map CRM doctors to CloseUp doctors.

    Rules:
    - All CRM doctors that are in the lab's portfolio get a CloseUp mapping
    - Some CloseUp doctors don't have a CRM mapping (lab doesn't visit them)
    - cod_interno = crm_interno.doctor.id
    - cod_closeup = closeup.medico.CDGMED
    """
    print("    Generating maestro_medicos...")

    # Map first NUM_MAESTRO_MEDICOS CRM doctors to CloseUp doctors
    # CRM doctors are 1..NUM_DOCTORS, CloseUp doctors are CUP-000001..CUP-{NUM_CUP_DOCTORS}
    # We map CRM doctor i to CloseUp doctor i (1:1 for simplicity)
    batch = []
    for i in range(1, min(NUM_MAESTRO_MEDICOS, NUM_DOCTORS) + 1):
        batch.append((
            i,                      # cod_interno (CRM doctor.id)
            f"CUP-{i:06d}",        # cod_closeup (CloseUp medico.CDGMED)
            None,                   # nombre_verificado
            None,                   # fecha_mapeo
            random.choice(["alta", "alta", "alta", "media"]),  # mostly high confidence
        ))

    execute_values(
        cur,
        """INSERT INTO maestros.maestro_medicos
        (cod_interno, cod_closeup, nombre_verificado, fecha_mapeo, confianza)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_maestro_integrador_producto(cur):
    """Map products across CRM, CloseUp, and IQVIA.

    Rules:
    - Lab's own products have all 3 codes (CRM + CUP + IQVIA)
    - Some products only have CUP (competitor products with prescriptions)
    - Some products only have IQVIA (competitor products with sales only)
    - If no cod_closeup → no prescriptions recorded
    - If no cod_iqvia → no sales recorded
    """
    print("    Generating maestro_integrador_producto...")

    batch = []

    # Lab's own products: have all 3 codes (first NUM_PRODUCTS mapped)
    num_lab_products = min(NUM_PRODUCTS, NUM_MAESTRO_PRODUCTOS)
    for i in range(1, num_lab_products + 1):
        batch.append((
            f"SKU-{i:04d}",        # cod_interno (CRM familia_producto.codigo)
            f"MK-{i:05d}",         # cod_closeup (CloseUp marca.codigo_marca)
            f"IQV-{i:06d}",        # cod_iqvia (IQVIA dim_presentacion.idProducto)
            f"EAN-{i:011d}" if random.random() > 0.2 else None,
            f"Producto Lab {i}",
            None,                   # principio_activo
            None,                   # fecha_mapeo
        ))

    # Competitor products with CUP only (prescriptions but no internal code)
    num_cup_only = min(50, NUM_MAESTRO_PRODUCTOS - num_lab_products)
    for i in range(num_lab_products + 1, num_lab_products + num_cup_only + 1):
        batch.append((
            None,                   # no cod_interno (not our product)
            f"MK-{i:05d}",         # cod_closeup
            f"IQV-{i:06d}",        # cod_iqvia
            None,
            f"Competidor {i}",
            None,
            None,
        ))

    execute_values(
        cur,
        """INSERT INTO maestros.maestro_integrador_producto
        (cod_interno, cod_closeup, cod_iqvia, codigo_barras_ean11,
         nombre_unificado, principio_activo, fecha_mapeo)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_familia_interno_a_marca_cup(cur):
    """Map CRM product families to CloseUp brand codes (N:M).

    A single familia_producto can map to multiple CloseUp brands
    (different presentations of the same product).
    Uses DISTINCT when querying to avoid duplicates.
    """
    print("    Generating familia_interno_a_marca_cup...")

    batch = []
    for i in range(1, min(NUM_PRODUCTS, 150) + 1):
        # Each product maps to 1-3 CloseUp brands
        num_mappings = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15], k=1)[0]
        # Map to nearby brand IDs (simulating same product family)
        base_brand = i
        for j in range(num_mappings):
            brand_idx = base_brand + j * random.randint(0, 2)
            if brand_idx > NUM_CUP_BRANDS:
                brand_idx = base_brand
            relacion = "exacta" if j == 0 else random.choice(["parcial", "generico"])
            batch.append((
                f"SKU-{i:04d}",
                f"MK-{brand_idx:05d}",
                relacion,
            ))

    execute_values(
        cur,
        """INSERT INTO maestros.familia_interno_a_marca_cup
        (cod_interno, codigo_marca, relacion)
        VALUES %s""",
        batch,
        page_size=1000,
    )
    return len(batch)


def generate_ultima_milla(cur):
    """Generate UltimaMilla tables in CRM schema (pre-computed cross-source views).

    These live in crm_interno but contain data derived from CloseUp.
    """
    print("    Generating ultima_milla tables...")

    # ultima_milla_medico: one row per doctor with EVO and shares
    batch_medico = []
    for i in range(1, min(NUM_DOCTORS, 3000) + 1):
        batch_medico.append((
            f"CUP-{i:06d}",        # id_medico_cup
            i,                      # id_medico_crm
            round(random.uniform(-30, 50), 2),   # evo_trimestral
            round(random.uniform(0, 0.4), 4),    # share_lab_ytd
            round(random.uniform(0, 0.5), 4),    # share_lab_mensual
            round(random.uniform(0, 0.35), 4),   # share_lab_mat
            str(random.randint(1, 5)),           # categoria_medico (1=highest potential)
        ))
    execute_values(
        cur,
        """INSERT INTO crm_interno.ultima_milla_medico
        (id_medico_cup, id_medico_crm, evo_trimestral, share_lab_ytd,
         share_lab_mensual, share_lab_mat, categoria_medico)
        VALUES %s""",
        batch_medico,
        page_size=1000,
    )

    # ultima_milla_marca: ~10 brands per doctor
    batch_marca = []
    for doc_i in range(1, min(NUM_DOCTORS, 3000) + 1):
        num_brands = random.randint(5, 15)
        for _ in range(num_brands):
            brand_idx = random.randint(1, min(500, NUM_CUP_BRANDS))
            market_idx = random.randint(1, 60)
            batch_marca.append((
                f"CUP-{doc_i:06d}",
                f"MK-{brand_idx:05d}",
                f"MER-{market_idx:03d}",
                round(random.uniform(0, 0.3), 4),
                round(random.uniform(0, 0.15), 4),
                str(random.randint(1, 5)),
            ))
    execute_values(
        cur,
        """INSERT INTO crm_interno.ultima_milla_marca
        (id_medico_cup, id_marca, id_mercado, share_marca_mercado,
         share_marca_total, categoria_medico)
        VALUES %s""",
        batch_marca,
        page_size=1000,
    )

    # ultima_milla_objetivo: market → brand → specialty
    batch_obj = []
    for mkt_i in range(1, NUM_CUP_MARKETS + 1):
        num_brands = random.randint(3, 8)
        for _ in range(num_brands):
            brand_idx = random.randint(1, min(200, NUM_CUP_BRANDS))
            esp_id = random.randint(1, NUM_SPECIALTIES)
            batch_obj.append((
                f"MER-{mkt_i:03d}",
                f"Marca Objetivo {brand_idx}",
                esp_id,
            ))
    execute_values(
        cur,
        """INSERT INTO crm_interno.ultima_milla_objetivo
        (id_mercado, nombre_marca, id_especialidad)
        VALUES %s""",
        batch_obj,
        page_size=1000,
    )

    return {
        "ultima_milla_medico": len(batch_medico),
        "ultima_milla_marca": len(batch_marca),
        "ultima_milla_objetivo": len(batch_obj),
    }


def generate_all(conn):
    """Generate all maestros data + UltimaMilla."""
    summary = {}
    with conn.cursor() as cur:
        print("  Generating Maestros + UltimaMilla data...")
        summary["maestro_medicos"] = generate_maestro_medicos(cur)
        conn.commit()
        summary["maestro_integrador_producto"] = generate_maestro_integrador_producto(cur)
        conn.commit()
        summary["familia_interno_a_marca_cup"] = generate_familia_interno_a_marca_cup(cur)
        conn.commit()
        um = generate_ultima_milla(cur)
        summary.update(um)
        conn.commit()

    return summary
