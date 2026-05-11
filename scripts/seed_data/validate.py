"""Validate synthetic data with cross-source queries.

Runs the 4 validation queries from the design document to confirm
data coherence across all schemas and maestros.
"""
import psycopg2
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


QUERIES = {
    "1. CRM: médicos de un APM con productos foco": """
        SELECT d.nombre, d.apellido, fp.nombre as producto_foco, c.nombre as categoria
        FROM crm_interno.cartera_medica cm
        JOIN crm_interno.doctor d ON d.id = cm.doctor_id
        JOIN crm_interno.linea_apm la ON la.apm_id = cm.apm_id
        JOIN crm_interno.grilla g ON g.linea_id = la.linea_id
        JOIN crm_interno.detalle_promocion_producto dpp ON dpp.grilla_id = g.id
        JOIN crm_interno.categoria c ON c.id = dpp.categoria_id
        JOIN crm_interno.ciclo ci ON ci.id = dpp.ciclo_id
        JOIN crm_interno.familia_producto fp ON fp.id = dpp.familia_producto_id
        WHERE cm.apm_id = 1 AND cm.activa = true
          AND c.nombre IN ('foco', 'hiperfoco') AND ci.activo = true
        LIMIT 10;
    """,
    "2. CloseUp: top 5 productos prescritos por un médico": """
        SELECT m.codigo_marca, m.nombre_marca, SUM(p.cantidad) as total_px
        FROM closeup.prescripcion p
        JOIN closeup.marca m ON m.codigo_marca = p.CDGPRO
        WHERE p.CDGMED = 'CUP-000001'
        GROUP BY m.codigo_marca, m.nombre_marca
        ORDER BY total_px DESC
        LIMIT 5;
    """,
    "3. IQVIA: ventas de un producto por período": """
        SELECT dp.descripcion as producto, dper.anio, dper.mes, f.unidades, f.valor
        FROM iqvia.fact_mercado_valor f
        JOIN iqvia.dim_presentacion dp ON dp.idProducto = f.idProducto
        JOIN iqvia.dim_periodo dper ON dper.idPeriodo = f.idPeriodo
        WHERE f.idProducto = 'IQV-000001'
        ORDER BY dper.anio, dper.mes
        LIMIT 12;
    """,
    "4. Cross-source: prescripciones de productos foco de un APM": """
        SELECT d.nombre || ' ' || d.apellido as medico,
               mk.nombre_marca,
               SUM(p.cantidad) as total_px
        FROM crm_interno.cartera_medica cm
        JOIN maestros.maestro_medicos mm ON mm.cod_interno = cm.doctor_id
        JOIN closeup.prescripcion p ON p.CDGMED = mm.cod_closeup
        JOIN maestros.familia_interno_a_marca_cup fimc ON fimc.codigo_marca = p.CDGPRO
        JOIN closeup.marca mk ON mk.codigo_marca = p.CDGPRO
        JOIN crm_interno.doctor d ON d.id = cm.doctor_id
        WHERE cm.apm_id = 1 AND cm.activa = true
        GROUP BY d.nombre, d.apellido, mk.nombre_marca
        ORDER BY total_px DESC
        LIMIT 10;
    """,
}


def main():
    """Run all validation queries."""
    print("Connecting to database...")
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )

    all_passed = True

    with conn.cursor() as cur:
        for name, query in QUERIES.items():
            print(f"\n{'='*60}")
            print(f"Query: {name}")
            print(f"{'='*60}")
            try:
                cur.execute(query)
                rows = cur.fetchall()
                if rows:
                    # Print column headers
                    cols = [desc[0] for desc in cur.description]
                    print(f"  Columns: {cols}")
                    print(f"  Rows returned: {len(rows)}")
                    for row in rows[:5]:
                        print(f"    {row}")
                    if len(rows) > 5:
                        print(f"    ... ({len(rows) - 5} more)")
                    print(f"  ✅ PASS")
                else:
                    print(f"  ❌ FAIL — no rows returned")
                    all_passed = False
            except Exception as e:
                print(f"  ❌ ERROR — {e}")
                all_passed = False
                conn.rollback()

    # Also print row counts
    print(f"\n{'='*60}")
    print("Table row counts:")
    print(f"{'='*60}")
    with conn.cursor() as cur:
        tables = [
            ("crm_interno", "doctor"),
            ("crm_interno", "cartera_medica"),
            ("crm_interno", "agenda"),
            ("crm_interno", "agenda_producto"),
            ("crm_interno", "ultima_milla_medico"),
            ("closeup", "medico"),
            ("closeup", "prescripcion"),
            ("closeup", "marca"),
            ("iqvia", "dim_presentacion"),
            ("iqvia", "fact_mercado_valor"),
            ("maestros", "maestro_medicos"),
            ("maestros", "maestro_integrador_producto"),
            ("maestros", "familia_interno_a_marca_cup"),
        ]
        for schema, table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
                count = cur.fetchone()[0]
                print(f"  {schema}.{table}: {count:,}")
            except Exception as e:
                print(f"  {schema}.{table}: ERROR — {e}")
                conn.rollback()

    conn.close()

    print(f"\n{'='*60}")
    if all_passed:
        print("✅ ALL VALIDATION QUERIES PASSED")
    else:
        print("❌ SOME QUERIES FAILED — check output above")
    print(f"{'='*60}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
