"""Table definitions for the CRM domain (pharmassist_crm).

Contains 25 tables representing the pharmaceutical CRM system:
APMs, doctors, zones, specialties, medical portfolios, product lines,
promotional cycles, visit agendas, samples, tags, and last-mile metrics.
"""

from table_definitions import ColumnDef, TableDef

CRM_TABLES: list[TableDef] = [
    # 1. apm — APM (visitador médico)
    TableDef(
        name="apm",
        description="APM (Agente de Propaganda Médica) - visitador médico",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único del APM"),
            ColumnDef(name="nombre", type="string", comment="Nombre del APM"),
            ColumnDef(name="apellido", type="string", comment="Apellido del APM"),
            ColumnDef(name="email", type="string", comment="Email corporativo"),
            ColumnDef(name="telefono", type="string", comment="Teléfono de contacto"),
            ColumnDef(name="zona_id", type="int", comment="FK a zona asignada"),
            ColumnDef(name="activo", type="boolean", comment="Si el APM está activo"),
            ColumnDef(name="fecha_alta", type="date", comment="Fecha de alta en el sistema"),
        ],
        partition_keys=[],
    ),
    # 2. doctor — Médico
    TableDef(
        name="doctor",
        description="Médico registrado en el CRM",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único del médico"),
            ColumnDef(name="nombre", type="string", comment="Nombre del médico"),
            ColumnDef(name="apellido", type="string", comment="Apellido del médico"),
            ColumnDef(name="matricula_nacional", type="string", comment="Matrícula nacional"),
            ColumnDef(name="especialidad_id", type="int", comment="FK a especialidad"),
            ColumnDef(name="zona_id", type="int", comment="FK a zona geográfica"),
            ColumnDef(name="email", type="string", comment="Email del médico"),
            ColumnDef(name="telefono", type="string", comment="Teléfono del médico"),
            ColumnDef(name="direccion", type="string", comment="Dirección del consultorio"),
            ColumnDef(name="localidad", type="string", comment="Localidad"),
            ColumnDef(name="provincia", type="string", comment="Provincia"),
            ColumnDef(name="codigo_postal", type="string", comment="Código postal"),
            ColumnDef(name="latitud", type="decimal(10,7)", comment="Latitud geográfica"),
            ColumnDef(name="longitud", type="decimal(10,7)", comment="Longitud geográfica"),
            ColumnDef(name="cadencia", type="string", comment="Cadencia de visita esperada"),
            ColumnDef(name="activo", type="boolean", comment="Si el médico está activo"),
            ColumnDef(name="fecha_alta", type="date", comment="Fecha de alta en el sistema"),
        ],
        partition_keys=[],
    ),
    # 3. zona — Zona geográfica
    TableDef(
        name="zona",
        description="Zona geográfica de cobertura",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único de la zona"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la zona"),
            ColumnDef(name="region", type="string", comment="Región a la que pertenece"),
            ColumnDef(name="provincia", type="string", comment="Provincia"),
            ColumnDef(name="activo", type="boolean", comment="Si la zona está activa"),
        ],
        partition_keys=[],
    ),
    # 4. especialidad — Especialidad médica
    TableDef(
        name="especialidad",
        description="Especialidad médica",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la especialidad"),
            ColumnDef(name="descripcion", type="string", comment="Descripción de la especialidad"),
            ColumnDef(name="activo", type="boolean", comment="Si está activa"),
        ],
        partition_keys=[],
    ),
    # 5. cartera_medica — Asignación médico-APM
    TableDef(
        name="cartera_medica",
        description="Asignación de médicos a APMs por línea",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="doctor_id", type="int", comment="FK al médico"),
            ColumnDef(name="apm_id", type="int", comment="FK al APM"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea de productos"),
            ColumnDef(name="fecha_asignacion", type="date", comment="Fecha de asignación"),
            ColumnDef(name="activo", type="boolean", comment="Si la asignación está activa"),
        ],
        partition_keys=[],
    ),
    # 6. cartera_medica_estado — Estado de cartera
    TableDef(
        name="cartera_medica_estado",
        description="Historial de estados de la cartera médica",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="cartera_medica_id", type="int", comment="FK a cartera_medica"),
            ColumnDef(name="estado", type="string", comment="Estado actual de la cartera"),
            ColumnDef(name="fecha_cambio", type="timestamp", comment="Fecha y hora del cambio"),
            ColumnDef(name="motivo", type="string", comment="Motivo del cambio de estado"),
        ],
        partition_keys=[],
    ),
    # 7. linea — Línea de productos
    TableDef(
        name="linea",
        description="Línea de productos del laboratorio",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la línea"),
            ColumnDef(name="descripcion", type="string", comment="Descripción de la línea"),
            ColumnDef(name="activo", type="boolean", comment="Si la línea está activa"),
        ],
        partition_keys=[],
    ),
    # 8. linea_apm — Asignación línea-APM
    TableDef(
        name="linea_apm",
        description="Asignación de líneas de producto a APMs",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="apm_id", type="int", comment="FK al APM"),
            ColumnDef(name="fecha_asignacion", type="date", comment="Fecha de asignación"),
            ColumnDef(name="activo", type="boolean", comment="Si la asignación está activa"),
        ],
        partition_keys=[],
    ),
    # 9. familia_producto — Familia de producto
    TableDef(
        name="familia_producto",
        description="Familia de producto dentro de una línea",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la familia"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="descripcion", type="string", comment="Descripción"),
            ColumnDef(name="activo", type="boolean", comment="Si está activa"),
        ],
        partition_keys=[],
    ),
    # 10. catalogo_productos — Catálogo de productos
    TableDef(
        name="catalogo_productos",
        description="Catálogo de productos del laboratorio",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre comercial del producto"),
            ColumnDef(name="familia_producto_id", type="int", comment="FK a familia_producto"),
            ColumnDef(name="presentacion", type="string", comment="Presentación del producto"),
            ColumnDef(name="tipo", type="string", comment="Tipo: OTC o RX"),
            ColumnDef(name="activo", type="boolean", comment="Si el producto está activo"),
            ColumnDef(name="codigo_barras", type="string", comment="Código de barras EAN"),
        ],
        partition_keys=[],
    ),
    # 11. ciclo — Ciclo promocional
    TableDef(
        name="ciclo",
        description="Ciclo promocional del laboratorio",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre del ciclo"),
            ColumnDef(name="fecha_inicio", type="date", comment="Fecha de inicio del ciclo"),
            ColumnDef(name="fecha_fin", type="date", comment="Fecha de fin del ciclo"),
            ColumnDef(name="anio", type="int", comment="Año del ciclo"),
            ColumnDef(name="mes", type="int", comment="Mes del ciclo"),
            ColumnDef(name="activo", type="boolean", comment="Si el ciclo está activo"),
        ],
        partition_keys=[],
    ),
    # 12. grilla — Grilla de visitas
    TableDef(
        name="grilla",
        description="Grilla de visitas planificadas por ciclo",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="doctor_id", type="int", comment="FK al médico"),
            ColumnDef(name="apm_id", type="int", comment="FK al APM"),
            ColumnDef(name="orden", type="int", comment="Orden de visita en la grilla"),
            ColumnDef(name="activo", type="boolean", comment="Si está activa"),
        ],
        partition_keys=[],
    ),
    # 13. categoria — Categoría de médico
    TableDef(
        name="categoria",
        description="Categoría de clasificación de médicos",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre de la categoría"),
            ColumnDef(name="descripcion", type="string", comment="Descripción"),
            ColumnDef(name="peso", type="int", comment="Peso para priorización"),
            ColumnDef(name="activo", type="boolean", comment="Si está activa"),
        ],
        partition_keys=[],
    ),
    # 14. detalle_promocion_producto — Detalle de promoción
    TableDef(
        name="detalle_promocion_producto",
        description="Detalle de productos en promoción por ciclo",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="producto_id", type="int", comment="FK al producto"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="orden_presentacion", type="int", comment="Orden de presentación"),
            ColumnDef(name="material_apoyo", type="string", comment="Material de apoyo asociado"),
            ColumnDef(name="activo", type="boolean", comment="Si está activo"),
        ],
        partition_keys=[],
    ),
    # 15. agenda — Agenda de visitas (PARTITIONED by fecha_inicio)
    TableDef(
        name="agenda",
        description="Agenda de visitas médicas realizadas y programadas",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="apm_id", type="int", comment="FK al APM"),
            ColumnDef(name="doctor_id", type="int", comment="FK al médico"),
            ColumnDef(name="fecha_inicio", type="timestamp", comment="Fecha y hora de inicio"),
            ColumnDef(name="fecha_fin", type="timestamp", comment="Fecha y hora de fin"),
            ColumnDef(name="tipo_visita", type="string", comment="Tipo: Presencial, Virtual, Telefónica"),
            ColumnDef(name="estado", type="string", comment="Estado: Planificada, Realizada, Cancelada"),
            ColumnDef(name="notas", type="string", comment="Notas de la visita"),
            ColumnDef(name="zona_id", type="int", comment="FK a la zona"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="creado_en", type="timestamp", comment="Fecha de creación del registro"),
        ],
        partition_keys=["fecha_inicio"],
    ),
    # 16. agenda_producto — Productos en agenda
    TableDef(
        name="agenda_producto",
        description="Productos presentados en cada visita de la agenda",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="agenda_id", type="int", comment="FK a la agenda"),
            ColumnDef(name="producto_id", type="int", comment="FK al producto"),
            ColumnDef(name="orden", type="int", comment="Orden de presentación"),
            ColumnDef(name="presentado", type="boolean", comment="Si fue efectivamente presentado"),
            ColumnDef(name="comentario", type="string", comment="Comentario sobre la presentación"),
        ],
        partition_keys=[],
    ),
    # 17. agenda_muestra — Muestras entregadas
    TableDef(
        name="agenda_muestra",
        description="Muestras médicas entregadas en visitas",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="agenda_id", type="int", comment="FK a la agenda"),
            ColumnDef(name="producto_id", type="int", comment="FK al producto"),
            ColumnDef(name="cantidad", type="int", comment="Cantidad de muestras entregadas"),
            ColumnDef(name="lote", type="string", comment="Número de lote"),
            ColumnDef(name="fecha_vencimiento", type="date", comment="Fecha de vencimiento del lote"),
        ],
        partition_keys=[],
    ),
    # 18. datos_visita — Datos adicionales de visita
    TableDef(
        name="datos_visita",
        description="Datos adicionales registrados durante la visita",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="agenda_id", type="int", comment="FK a la agenda"),
            ColumnDef(name="duracion_minutos", type="int", comment="Duración en minutos"),
            ColumnDef(name="acompanante", type="string", comment="Acompañante en la visita"),
            ColumnDef(name="lugar", type="string", comment="Lugar de la visita"),
            ColumnDef(name="resultado", type="string", comment="Resultado de la visita"),
            ColumnDef(name="seguimiento", type="string", comment="Acciones de seguimiento"),
        ],
        partition_keys=[],
    ),
    # 19. visita_planificada — Visitas planificadas
    TableDef(
        name="visita_planificada",
        description="Visitas planificadas pendientes de ejecución",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="apm_id", type="int", comment="FK al APM"),
            ColumnDef(name="doctor_id", type="int", comment="FK al médico"),
            ColumnDef(name="fecha_planificada", type="date", comment="Fecha planificada"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="prioridad", type="int", comment="Prioridad de la visita"),
            ColumnDef(name="estado", type="string", comment="Estado: Pendiente, Completada, Cancelada"),
            ColumnDef(name="motivo", type="string", comment="Motivo de la visita"),
        ],
        partition_keys=[],
    ),
    # 20. tag — Tags/etiquetas
    TableDef(
        name="tag",
        description="Tags para clasificación de médicos",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="nombre", type="string", comment="Nombre del tag"),
            ColumnDef(name="color", type="string", comment="Color hexadecimal del tag"),
            ColumnDef(name="activo", type="boolean", comment="Si el tag está activo"),
        ],
        partition_keys=[],
    ),
    # 21. tag_doctor — Tags asignados a médicos
    TableDef(
        name="tag_doctor",
        description="Asignación de tags a médicos",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="tag_id", type="int", comment="FK al tag"),
            ColumnDef(name="doctor_id", type="int", comment="FK al médico"),
            ColumnDef(name="fecha_asignacion", type="date", comment="Fecha de asignación del tag"),
        ],
        partition_keys=[],
    ),
    # 22. ultima_milla_medico — Última milla por médico
    TableDef(
        name="ultima_milla_medico",
        description="Métricas de última milla por médico y línea",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="doctor_id", type="int", comment="FK al médico"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="cobertura", type="decimal(5,2)", comment="Porcentaje de cobertura"),
            ColumnDef(name="frecuencia_real", type="int", comment="Frecuencia real de visitas"),
            ColumnDef(name="frecuencia_objetivo", type="int", comment="Frecuencia objetivo"),
            ColumnDef(name="fecha_calculo", type="date", comment="Fecha del cálculo"),
        ],
        partition_keys=[],
    ),
    # 23. ultima_milla_marca — Última milla por marca
    TableDef(
        name="ultima_milla_marca",
        description="Métricas de última milla por marca y zona",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="producto_id", type="int", comment="FK al producto"),
            ColumnDef(name="zona_id", type="int", comment="FK a la zona"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="penetracion", type="decimal(5,2)", comment="Porcentaje de penetración"),
            ColumnDef(name="market_share", type="decimal(5,2)", comment="Participación de mercado"),
            ColumnDef(name="tendencia", type="string", comment="Tendencia: Creciente, Estable, Decreciente"),
            ColumnDef(name="fecha_calculo", type="date", comment="Fecha del cálculo"),
        ],
        partition_keys=[],
    ),
    # 24. ultima_milla_objetivo — Objetivos última milla
    TableDef(
        name="ultima_milla_objetivo",
        description="Objetivos de última milla por línea y zona",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="zona_id", type="int", comment="FK a la zona"),
            ColumnDef(name="ciclo_id", type="int", comment="FK al ciclo"),
            ColumnDef(name="objetivo_cobertura", type="decimal(5,2)", comment="Objetivo de cobertura %"),
            ColumnDef(name="objetivo_frecuencia", type="int", comment="Objetivo de frecuencia"),
            ColumnDef(name="activo", type="boolean", comment="Si el objetivo está activo"),
        ],
        partition_keys=[],
    ),
    # 25. linea_especializacion — Línea por especialización
    TableDef(
        name="linea_especializacion",
        description="Relación entre líneas de producto y especialidades médicas",
        columns=[
            ColumnDef(name="id", type="int", comment="Identificador único"),
            ColumnDef(name="linea_id", type="int", comment="FK a la línea"),
            ColumnDef(name="especialidad_id", type="int", comment="FK a la especialidad"),
            ColumnDef(name="prioridad", type="int", comment="Prioridad de la línea para la especialidad"),
            ColumnDef(name="activo", type="boolean", comment="Si la relación está activa"),
        ],
        partition_keys=[],
    ),
]
