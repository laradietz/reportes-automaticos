-- Modelo dimensional (esquema en estrella) sobre PostgreSQL.
-- Mismo modelo que schema_sqlite.sql, con tipos nativos: DATE, NUMERIC (sin errores de redondeo) y TIMESTAMP.

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
    precio_lista NUMERIC(12, 2) NOT NULL CHECK (precio_lista > 0)
);

CREATE TABLE IF NOT EXISTS dim_fecha (
    fecha      DATE PRIMARY KEY,
    anio       INTEGER NOT NULL,
    mes        INTEGER NOT NULL,
    anio_mes   TEXT NOT NULL,               -- yyyy-mm
    trimestre  INTEGER NOT NULL,
    dia_semana TEXT NOT NULL
);

-- Cotización diaria del dólar oficial (fuente: API REST)
CREATE TABLE IF NOT EXISTS dim_cotizacion (
    fecha  DATE PRIMARY KEY,
    compra NUMERIC(12, 2) NOT NULL,
    venta  NUMERIC(12, 2) NOT NULL CHECK (venta > 0)
);

CREATE TABLE IF NOT EXISTS fact_ventas (
    id_venta        TEXT PRIMARY KEY,
    fecha           DATE NOT NULL REFERENCES dim_fecha(fecha),
    id_cliente      TEXT NOT NULL REFERENCES dim_cliente(id_cliente),
    id_producto     TEXT NOT NULL REFERENCES dim_producto(id_producto),
    vendedor        TEXT NOT NULL,
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(12, 2) NOT NULL CHECK (precio_unitario > 0),
    descuento       NUMERIC(5, 4)  NOT NULL CHECK (descuento BETWEEN 0 AND 1),
    importe_bruto   NUMERIC(16, 2) NOT NULL,
    importe_neto    NUMERIC(16, 2) NOT NULL
);

-- Auditoría del proceso
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id            TEXT PRIMARY KEY,
    inicio            TIMESTAMP NOT NULL,
    fin               TIMESTAMP,
    filas_leidas      INTEGER,
    filas_cargadas    INTEGER,
    filas_rechazadas  INTEGER,
    estado            TEXT NOT NULL            -- EN_CURSO | OK | ERROR
);

CREATE TABLE IF NOT EXISTS etl_rechazos (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
