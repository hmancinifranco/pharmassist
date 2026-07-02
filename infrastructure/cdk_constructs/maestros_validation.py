"""CDK Construct for Maestros validation named queries in Athena.

Creates 6 CfnNamedQuery resources in the pharmassist-validation workgroup
to monitor data quality of the maestros integration tables.
"""

from aws_cdk import aws_athena as athena
from constructs import Construct


class MaestrosValidationQueries(Construct):
    """Registra named queries de validación de maestros en Athena.

    Creates 6 named queries that validate referential integrity,
    coverage metrics, and constraint compliance for the maestros tables.

    Args:
        scope: CDK construct scope.
        id: Construct ID.
        workgroup_name: Athena workgroup name (e.g., 'pharmassist-validation').
        glue_databases: Dict with keys 'crm', 'cup', 'iqvia', 'maestros'
                        mapping to Glue database names.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        workgroup_name: str,
        glue_databases: dict,
    ) -> None:
        super().__init__(scope, id)

        db_crm = glue_databases["crm"]
        db_cup = glue_databases["cup"]
        db_iqvia = glue_databases["iqvia"]
        db_maestros = glue_databases["maestros"]

        # 1. Cobertura de médicos: % de doctores CRM con mapeo en maestro
        athena.CfnNamedQuery(
            self,
            "CoberturaMedicos",
            name="validacion_maestros_cobertura_medicos",
            description=(
                "Porcentaje de médicos activos en CRM que tienen mapeo "
                "a código CloseUp en el maestro de médicos."
            ),
            work_group=workgroup_name,
            database=db_maestros,
            query_string=(
                "SELECT\n"
                f"    (SELECT COUNT(*) FROM {db_crm}.doctor WHERE activo = true) AS total_medicos_crm,\n"
                f"    (SELECT COUNT(*) FROM {db_maestros}.maestro_medicos WHERE cdgmedico_cup IS NOT NULL) AS con_mapeo_closeup,\n"
                "    ROUND(\n"
                f"        CAST((SELECT COUNT(*) FROM {db_maestros}.maestro_medicos mm\n"
                f"              JOIN {db_crm}.doctor d ON mm.doctor_id_crm = d.id\n"
                "              WHERE d.activo = true AND mm.cdgmedico_cup IS NOT NULL) AS DOUBLE)\n"
                f"        / NULLIF(CAST((SELECT COUNT(*) FROM {db_crm}.doctor WHERE activo = true) AS DOUBLE), 0)\n"
                "        * 100, 2\n"
                "    ) AS porcentaje_cobertura"
            ),
        )

        # 2. Cobertura de productos: distribución por cantidad de códigos mapeados
        athena.CfnNamedQuery(
            self,
            "CoberturaProductos",
            name="validacion_maestros_cobertura_productos",
            description=(
                "Distribución de productos en maestro integrador agrupados "
                "por cantidad de códigos presentes (3, 2 o 1 código)."
            ),
            work_group=workgroup_name,
            database=db_maestros,
            query_string=(
                "SELECT\n"
                "    CASE\n"
                "        WHEN producto_id_crm IS NOT NULL AND cdgmarca_cup IS NOT NULL AND idpresentacion_iqvia IS NOT NULL THEN '3_codigos'\n"
                "        WHEN (CASE WHEN producto_id_crm IS NOT NULL THEN 1 ELSE 0 END\n"
                "            + CASE WHEN cdgmarca_cup IS NOT NULL THEN 1 ELSE 0 END\n"
                "            + CASE WHEN idpresentacion_iqvia IS NOT NULL THEN 1 ELSE 0 END) = 2 THEN '2_codigos'\n"
                "        ELSE '1_codigo'\n"
                "    END AS grupo,\n"
                "    COUNT(*) AS cantidad,\n"
                f"    ROUND(CAST(COUNT(*) AS DOUBLE) / CAST((SELECT COUNT(*) FROM {db_maestros}.maestro_integrador_producto) AS DOUBLE) * 100, 2) AS porcentaje\n"
                f"FROM {db_maestros}.maestro_integrador_producto\n"
                "GROUP BY 1\n"
                "ORDER BY 1 DESC"
            ),
        )

        # 3. Huérfanos médicos: IDs sin correspondencia en CRM o CloseUp
        athena.CfnNamedQuery(
            self,
            "HuerfanosMedicos",
            name="validacion_maestros_huerfanos_medicos",
            description=(
                "Detecta registros huérfanos en maestro_medicos: "
                "doctor_id_crm sin correspondencia en CRM y "
                "cdgmedico_cup sin correspondencia en CloseUp."
            ),
            work_group=workgroup_name,
            database=db_maestros,
            query_string=(
                "SELECT 'doctor_id_crm sin correspondencia en CRM' AS tipo_huerfano, COUNT(*) AS cantidad\n"
                f"FROM {db_maestros}.maestro_medicos mm\n"
                f"LEFT JOIN {db_crm}.doctor d ON mm.doctor_id_crm = d.id\n"
                "WHERE mm.doctor_id_crm IS NOT NULL AND d.id IS NULL\n"
                "\n"
                "UNION ALL\n"
                "\n"
                "SELECT 'cdgmedico_cup sin correspondencia en CloseUp' AS tipo_huerfano, COUNT(*) AS cantidad\n"
                f"FROM {db_maestros}.maestro_medicos mm\n"
                f"LEFT JOIN {db_cup}.medico m ON mm.cdgmedico_cup = m.cdgmedico\n"
                "WHERE mm.cdgmedico_cup IS NOT NULL AND m.cdgmedico IS NULL"
            ),
        )

        # 4. Huérfanos productos: IDs sin correspondencia en CRM, CloseUp o IQVIA
        athena.CfnNamedQuery(
            self,
            "HuerfanosProductos",
            name="validacion_maestros_huerfanos_productos",
            description=(
                "Detecta registros huérfanos en maestro_integrador_producto: "
                "producto_id_crm sin correspondencia en CRM, "
                "cdgmarca_cup sin correspondencia en CloseUp, y "
                "idpresentacion_iqvia sin correspondencia en IQVIA."
            ),
            work_group=workgroup_name,
            database=db_maestros,
            query_string=(
                "SELECT 'producto_id_crm sin correspondencia en CRM' AS tipo_huerfano, COUNT(*) AS cantidad\n"
                f"FROM {db_maestros}.maestro_integrador_producto mip\n"
                f"LEFT JOIN {db_crm}.familia_producto fp ON mip.producto_id_crm = fp.id\n"
                "WHERE mip.producto_id_crm IS NOT NULL AND fp.id IS NULL\n"
                "\n"
                "UNION ALL\n"
                "\n"
                "SELECT 'cdgmarca_cup sin correspondencia en CloseUp' AS tipo_huerfano, COUNT(*) AS cantidad\n"
                f"FROM {db_maestros}.maestro_integrador_producto mip\n"
                f"LEFT JOIN {db_cup}.marca m ON mip.cdgmarca_cup = m.cdgmarca\n"
                "WHERE mip.cdgmarca_cup IS NOT NULL AND m.cdgmarca IS NULL\n"
                "\n"
                "UNION ALL\n"
                "\n"
                "SELECT 'idpresentacion_iqvia sin correspondencia en IQVIA' AS tipo_huerfano, COUNT(*) AS cantidad\n"
                f"FROM {db_maestros}.maestro_integrador_producto mip\n"
                f"LEFT JOIN {db_iqvia}.dim_presentacion dp ON mip.idpresentacion_iqvia = dp.idpresentacion\n"
                "WHERE mip.idpresentacion_iqvia IS NOT NULL AND dp.idpresentacion IS NULL"
            ),
        )

        # 5. Constraint al_menos_un_codigo: registros que violan la constraint
        athena.CfnNamedQuery(
            self,
            "ConstraintAlMenosUnCodigo",
            name="validacion_maestros_constraint_al_menos_un_codigo",
            description=(
                "Registros en maestro_integrador_producto que violan la constraint "
                "al_menos_un_codigo (todos los códigos son NULL)."
            ),
            work_group=workgroup_name,
            database=db_maestros,
            query_string=(
                "SELECT id, producto_id_crm, cdgmarca_cup, idpresentacion_iqvia, nombre_interno\n"
                f"FROM {db_maestros}.maestro_integrador_producto\n"
                "WHERE producto_id_crm IS NULL\n"
                "  AND cdgmarca_cup IS NULL\n"
                "  AND idpresentacion_iqvia IS NULL"
            ),
        )

        # 6. Duplicados familia-marca: pares duplicados en familia_interno_a_marca_cup
        athena.CfnNamedQuery(
            self,
            "DuplicadosFamiliaMarca",
            name="validacion_maestros_duplicados_familia_marca",
            description=(
                "Pares duplicados (familia_producto_id, cdgmarca_cup) en "
                "familia_interno_a_marca_cup que aparecen más de una vez."
            ),
            work_group=workgroup_name,
            database=db_maestros,
            query_string=(
                "SELECT familia_producto_id, cdgmarca_cup, COUNT(*) AS ocurrencias\n"
                f"FROM {db_maestros}.familia_interno_a_marca_cup\n"
                "GROUP BY familia_producto_id, cdgmarca_cup\n"
                "HAVING COUNT(*) > 1\n"
                "ORDER BY ocurrencias DESC"
            ),
        )
