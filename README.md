# Automatización de reportes — Pipeline ETL con Python y SQL

Proceso que **obtiene datos (archivos y una API REST), los limpia y valida, los carga en un data warehouse
(SQLite o PostgreSQL) y genera reportes (Excel, HTML y un tablero de Power BI) de forma automática**,
sin intervención manual y programable a diario.

`Python · SQL · SQLite · PostgreSQL · SQLAlchemy · ETL · pandas · API REST · Power BI · DAX · pytest · GitHub Actions`

![Tablero de ventas en Power BI](docs/tablero_powerbi.jpg)

## El problema

Un equipo comercial arma cada semana su reporte de ventas a mano: exporta CSV de varios sistemas, corrige errores
en Excel, copia tablas y gráficos. Es lento, propenso a errores y no deja rastro de qué datos se descartaron.
Este proyecto automatiza todo el ciclo y agrega **auditoría de calidad de datos**.

## Arquitectura

```
 Fuentes                      Python (pandas)                  Warehouse (esquema en estrella)      Salidas
┌─────────────────┐   ┌─────────────────────────────┐   ┌─────────────────────────────────┐   ┌───────────────────┐
│ ventas.csv      │   │ EXTRACT   leer + validar    │   │ dim_cliente  dim_producto       │   │ reporte_ventas    │
│ clientes.csv    ├──►│           (API: reintentos) ├──►│ dim_fecha    dim_cotizacion     ├──►│  .xlsx · .html    │
│ productos.csv   │   │ TRANSFORM limpiar, validar  │   │ fact_ventas                     │   │ modelo para       │
│ API cotizaciones│   │ LOAD      upsert, 1 transac.│   │ etl_runs     etl_rechazos       │   │ Power BI          │
└─────────────────┘   └──────────────┬──────────────┘   └───────────────┬─────────────────┘   └───────────────────┘
                              alerta si hay demasiados            SQLite  o  PostgreSQL
                              rechazos (código de salida 2)       consultas SQL versionadas (sql/queries)
        Orquestación: CLI  ──►  Programador de tareas de Windows  /  GitHub Actions (cron)
```

## Qué demuestra

| Área | Implementación |
|---|---|
| **ETL** | Etapas separadas (`extract.py`, `transform.py`, `load.py`), orquestadas en `pipeline.py`. |
| **Fuentes múltiples** | CSV y una **API REST** pública (dólar oficial): timeout, reintentos con espera creciente, validación del contrato y copia local si la API cae. |
| **Calidad de datos** | Reglas de validación sobre ventas y cotizaciones, deduplicación y normalización de clientes. Cada fila descartada se guarda con su motivo en `etl_rechazos`. |
| **Alertas** | Si la tasa de rechazos supera un umbral (5 % por defecto, configurable) el proceso termina con **código de salida 2** y deja una advertencia en el log. |
| **Carga incremental** | `etl --incremental` procesa solo ventas posteriores a la última fecha cargada (marca de agua, con un día de solape para datos tardíos) y no reprocesa rechazos ya reportados. Un test verifica que el resultado coincide con recargar todo. |
| **Dos motores SQL** | El mismo código corre sobre **SQLite** (cero instalación) y **PostgreSQL**, con esquemas nativos (`DATE`, `NUMERIC`, `TIMESTAMP`) y una capa común con SQLAlchemy. |
| **Modelado SQL** | Esquema en estrella con PK/FK, `CHECK` e índices (`sql/schema_sqlite.sql`, `sql/schema_postgres.sql`). |
| **SQL analítico** | CTEs y funciones de ventana: `LAG` (variación mensual), `RANK`, acumulados (Pareto 80/20), participación con `SUM() OVER ()`, subconsultas correlacionadas (tipo de cambio vigente). |
| **Idempotencia** | `INSERT … ON CONFLICT DO UPDATE`: re-ejecutar no duplica datos (test incluido). |
| **Atomicidad** | La carga corre en una sola transacción; si algo falla hace rollback y la corrida queda marcada `ERROR`. |
| **Auditoría** | Tabla `etl_runs` con filas leídas / cargadas / rechazadas y estado por corrida. |
| **BI** | Modelo en estrella en Power BI con relaciones, tabla de fechas y medidas DAX (YTD, variación mensual, ticket promedio). |
| **Automatización** | Tarea programada de Windows (`scheduler/`) y workflow de GitHub Actions con cron, con un servicio PostgreSQL real. |
| **Calidad de software** | 46 tests que corren contra SQLite **y** PostgreSQL 16 (reglas, idempotencia, rollback, integridad referencial, incremental, API simulada sin red, paridad de resultados entre motores), logging a archivo y configuración por entorno. |

## Cómo ejecutarlo

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"

.\.venv\Scripts\python -m reportes ejecutar     # genera datos (si faltan) + ETL + reportes
.\.venv\Scripts\python -m pytest -q             # tests (incluye PostgreSQL: levanta uno descartable con pgserver)
```

Comandos y opciones principales:

| Comando | Qué hace |
|---|---|
| `generar-datos` | Genera CSV sintéticos con errores intencionales. |
| `etl` / `etl --incremental` | Carga completa o solo lo posterior a la última fecha cargada. |
| `agregar-novedades --filas 500` | Agrega ventas nuevas (noviembre) a los CSV para probar la carga incremental. |
| `reportes` | Genera Excel, HTML y el modelo para Power BI desde el warehouse. |
| `ejecutar [--regenerar] [--incremental]` | Corrida completa: (datos) + ETL + reportes. |

Opciones globales: `--db-url` (base de datos), `--umbral 0.05` (tasa máxima de rechazos), `--sin-api` (no consultar la API de cotizaciones),
`--home` (carpeta de trabajo). También por entorno: `REPORTES_DB_URL`, `REPORTES_UMBRAL_RECHAZOS`, `REPORTES_URL_COTIZACIONES`, `REPORTES_HOME`.
Códigos de salida: `0` correcto, `1` error, `2` correcto pero con alerta de calidad.

Resultados en `output/`, logs en `logs/pipeline.log`. Automatizarlo todos los días a las 07:00 en Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\registrar_tarea_windows.ps1 -Hora "07:00"
```

## PostgreSQL

Por defecto se usa SQLite (`data/warehouse.db`). Para PostgreSQL alcanza con indicar la base:

```powershell
.\.venv\Scripts\python -m reportes --db-url "postgresql://usuario:clave@localhost:5432/ventas" ejecutar
# o bien: $env:REPORTES_DB_URL = "postgresql://usuario:clave@localhost:5432/ventas"
```

- Las tablas se crean solas (`sql/schema_postgres.sql`). La base indicada debe existir y el usuario necesita permisos para crear tablas.
- Los importes son `NUMERIC` (sin errores de redondeo de punto flotante) y las fechas `DATE`.
- Las contraseñas no se escriben en el log (se muestra la URL con `***`).
- Power BI se conecta directo con el conector nativo de PostgreSQL (*Obtener datos → Base de datos PostgreSQL*).
- Las mismas consultas de `sql/queries/` se ejecutan en ambos motores; un test compara los resultados de cada una.
  Esa comparación detectó un caso real: PostgreSQL 16.2 ignoraba `WHERE ranking <= 15` cuando la consulta combinaba `RANK()` con otra función de ventana
  (SQLite lo respetaba), por eso el Top 15 usa `LIMIT`.

## Tablero de Power BI

El pipeline deja el modelo en estrella en `output/powerbi/` con **nombres de archivo fijos** (`modelo_ventas.xlsx` con las tablas,
más un CSV por tabla), pensado para conectarlo a Power BI y refrescarlo con un solo clic después de cada corrida.

1. Ejecutar el pipeline (`reportes ejecutar`) para generar `output/powerbi/`.
2. Power BI Desktop → **Obtener datos → Excel** → `output/powerbi/modelo_ventas.xlsx` → cargar las tablas.
3. Relaciones (muchos a uno): `fact_ventas[fecha]→dim_fecha[fecha]`, `fact_ventas[id_cliente]→dim_cliente[id_cliente]`,
   `fact_ventas[id_producto]→dim_producto[id_producto]`. Marcar `dim_fecha` como tabla de fechas.
4. Crear las medidas de [`docs/powerbi_medidas.dax`](docs/powerbi_medidas.dax).

El tablero de la captura incluye KPIs (ventas netas, órdenes, ticket promedio, clientes activos, variación contra el mes anterior,
descuento efectivo), evolución mensual con acumulado del año, top 10 de productos, ventas por región y por categoría.

Alternativas de conexión sin pasar por archivos: con SQLite, un script de Python (`output/powerbi/conectar_sqlite.py`, generado en cada corrida)
o el driver ODBC de SQLite; con PostgreSQL, el conector nativo.

## Resultados con el dataset de ejemplo

Datos **sintéticos** (semilla fija, reproducibles) con ~5 % de errores inyectados a propósito: duplicados, fechas
imposibles (`31/02`), cantidades negativas, clientes/productos inexistentes, descuentos > 100 %, textos inconsistentes.

- 12.466 filas leídas de los CSV → **370 rechazadas con motivo** (3,0 %, bajo el umbral de alerta; ninguna se pierde en silencio).
- Con la API activa se suman 314 cotizaciones del dólar dentro del rango de ventas, y los reportes incluyen las ventas en USD.
- ETL completo en 1–3 segundos; segunda corrida: mismos totales (idempotente) y una nueva fila de auditoría.
- Carga incremental sobre 400 ventas nuevas: procesa solo lo nuevo (~0,2 s) y deja el warehouse idéntico a una recarga completa.

## Estructura

```
src/reportes/   config · db · generate_data · extract · transform · load · reports · pipeline · cli
sql/            schema_sqlite.sql · schema_postgres.sql · queries/*.sql (un reporte = una consulta versionada)
tests/          transformaciones, pipeline, incremental, API simulada, alertas y PostgreSQL
docs/           captura del tablero y medidas DAX de Power BI
scheduler/      registro de tarea diaria en Windows
.github/        CI: tests + pipeline en SQLite y PostgreSQL + reportes como artefacto
```

## Decisiones de diseño

- **La lógica de negocio vive en SQL**, no en pandas: las consultas se pueden revisar y reutilizar desde cualquier herramienta de BI.
- **Todo se lee como texto** y la limpieza decide los tipos, para que un valor malo no rompa la lectura del archivo.
- **Dos motores, un solo código:** SQLAlchemy para la conexión y SQL estándar (`ON CONFLICT`, ventanas, CTEs); solo el DDL difiere.
- **Fuentes externas opcionales:** si la API no responde se usa la última copia local; sin copia, el pipeline sigue sin conversión a USD.
- **Rechazar con motivo > corregir en silencio**: la única imputación (descuento vacío = 0, vendedor vacío = "Sin asignar") está documentada en el código.
- **Incremental sin sorpresas:** lo ya rechazado no se reprocesa ni vuelve a contar para la alerta; para reevaluar una fuente corregida se hace una carga completa.

## Próximos pasos posibles

Envío del reporte por mail, orquestación con un scheduler dedicado (Airflow/Prefect), particionado de la tabla de hechos, publicación del tablero en Power BI Service con un gateway.

## Licencia

[MIT](LICENSE)
