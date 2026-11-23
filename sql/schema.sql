-- Modelo dimensional (esquema en estrella) sobre SQLite.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_cliente (
    id_cliente TEXT PRIMARY KEY,
    nombre     TEXT NOT NULL,
    email      TEXT,
    region     TEXT NOT NULL,
    segmento   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_producto (
    id_producto  TEXT PRIMARY KEY,
    nombre       TEXT NOT NULL,
    categoria    TEXT,
    precio_lista REAL NOT NULL CHECK (precio_lista > 0)
);

CREATE TABLE IF NOT EXISTS dim_fecha (
    fecha      TEXT PRIMARY KEY,            -- ISO yyyy-mm-dd
    anio       INTEGER NOT NULL,
    mes        INTEGER NOT NULL,
    anio_mes   TEXT NOT NULL,               -- yyyy-mm
    trimestre  INTEGER NOT NULL,
    dia_semana TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_ventas (
    id_venta        TEXT PRIMARY KEY,
    fecha           TEXT NOT NULL REFERENCES dim_fecha(fecha),
    id_cliente      TEXT NOT NULL REFERENCES dim_cliente(id_cliente),
    id_producto     TEXT NOT NULL REFERENCES dim_producto(id_producto),
    vendedor        TEXT NOT NULL,
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario REAL    NOT NULL CHECK (precio_unitario > 0),
    descuento       REAL    NOT NULL CHECK (descuento BETWEEN 0 AND 1),
    importe_bruto   REAL    NOT NULL,
    importe_neto    REAL    NOT NULL
);

-- Auditoría del proceso
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id            TEXT PRIMARY KEY,
    inicio            TEXT NOT NULL,
    fin               TEXT,
    filas_leidas      INTEGER,
    filas_cargadas    INTEGER,
    filas_rechazadas  INTEGER,
    estado            TEXT NOT NULL            -- EN_CURSO | OK | ERROR
);

CREATE TABLE IF NOT EXISTS etl_rechazos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    TEXT NOT NULL REFERENCES etl_runs(run_id),
    tabla     TEXT NOT NULL,
    clave     TEXT,
    motivo    TEXT NOT NULL,
    registro  TEXT
);

CREATE INDEX IF NOT EXISTS ix_fact_fecha    ON fact_ventas(fecha);
CREATE INDEX IF NOT EXISTS ix_fact_cliente  ON fact_ventas(id_cliente);
CREATE INDEX IF NOT EXISTS ix_fact_producto ON fact_ventas(id_producto);
CREATE INDEX IF NOT EXISTS ix_fact_vendedor ON fact_ventas(vendedor);
CREATE INDEX IF NOT EXISTS ix_rech_run      ON etl_rechazos(run_id);
