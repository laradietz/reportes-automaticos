"""L — Carga. Upserts idempotentes (SQLite o PostgreSQL): re-ejecutar el ETL no duplica datos."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from . import db

log = logging.getLogger(__name__)


def inicializar(engine: Engine, sql_dir: Path) -> None:
    """Crea las tablas si no existen, con el esquema del motor en uso."""
    archivo = "schema_postgres.sql" if db.es_postgres(engine) else "schema_sqlite.sql"
    with engine.begin() as conn:
        db.ejecutar_script(conn, (sql_dir / archivo).read_text(encoding="utf-8"))


def _filas(df: pd.DataFrame, cols: list[str]) -> list[list]:
    sub = df[cols].astype(object)
    return sub.where(sub.notna(), None).values.tolist()


def upsert(conn: Connection, tabla: str, df: pd.DataFrame, cols: list[str], pk: str) -> int:
    """INSERT ... ON CONFLICT DO UPDATE: sintaxis común a SQLite y PostgreSQL."""
    if df.empty:
        return 0
    actualiza = ", ".join(f"{c} = excluded.{c}" for c in cols if c != pk)
    sql = text(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
               f"ON CONFLICT ({pk}) DO UPDATE SET {actualiza}")
    conn.execute(sql, [dict(zip(cols, fila)) for fila in _filas(df, cols)])
    return len(df)


def marca_de_agua(engine: Engine) -> str | None:
    """Última fecha de venta cargada, como 'yyyy-mm-dd' (None si el warehouse está vacío)."""
    with engine.connect() as conn:
        ultima = conn.execute(text("SELECT MAX(fecha) FROM fact_ventas")).scalar()
    return None if ultima is None else str(ultima)


def ids_ventas_rechazadas(engine: Engine) -> set[str]:
    """id_venta rechazados en corridas anteriores (no se reprocesan en modo incremental)."""
    with engine.connect() as conn:
        filas = conn.execute(text("SELECT DISTINCT clave FROM etl_rechazos WHERE tabla = 'ventas' AND clave IS NOT NULL"))
        return {f[0] for f in filas}


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def iniciar_run(engine: Engine, leidas: int) -> str:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO etl_runs (run_id, inicio, filas_leidas, estado) "
                          "VALUES (:run_id, :inicio, :leidas, 'EN_CURSO')"),
                     {"run_id": run_id, "inicio": _ahora(), "leidas": leidas})
    return run_id


def cargar(engine: Engine, datos: dict, run_id: str) -> dict:
    """Carga todo en UNA transacción: o entra completo o no entra nada."""
    try:
        with engine.begin() as conn:  # commit al salir; rollback ante cualquier excepción
            n_cli = upsert(conn, "dim_cliente", datos["clientes"], ["id_cliente", "nombre", "email", "region", "segmento"], "id_cliente")
            n_prod = upsert(conn, "dim_producto", datos["productos"], ["id_producto", "nombre", "categoria", "precio_lista"], "id_producto")
            upsert(conn, "dim_fecha", datos["fechas"], ["fecha", "anio", "mes", "anio_mes", "trimestre", "dia_semana"], "fecha")
            n_cot = upsert(conn, "dim_cotizacion", datos["cotizaciones"], ["fecha", "compra", "venta"], "fecha")
            n_ven = upsert(conn, "fact_ventas", datos["ventas"],
                           ["id_venta", "fecha", "id_cliente", "id_producto", "vendedor", "cantidad",
                            "precio_unitario", "descuento", "importe_bruto", "importe_neto"], "id_venta")
            rech = datos["rechazos"]
            if not rech.empty:
                filas = [dict(zip(("run_id", "tabla", "clave", "motivo", "registro"), (run_id, *r)))
                         for r in _filas(rech, ["tabla", "clave", "motivo", "registro"])]
                conn.execute(text("INSERT INTO etl_rechazos (run_id, tabla, clave, motivo, registro) "
                                  "VALUES (:run_id, :tabla, :clave, :motivo, :registro)"), filas)
            conn.execute(text("UPDATE etl_runs SET fin = :fin, filas_cargadas = :cargadas, "
                              "filas_rechazadas = :rechazadas, estado = 'OK' WHERE run_id = :run_id"),
                         {"fin": _ahora(), "cargadas": n_cli + n_prod + n_ven + n_cot,
                          "rechazadas": len(rech), "run_id": run_id})
    except Exception:
        with engine.begin() as conn:
            conn.execute(text("UPDATE etl_runs SET fin = :fin, estado = 'ERROR' WHERE run_id = :run_id"),
                         {"fin": _ahora(), "run_id": run_id})
        raise
    log.info("Cargado: clientes=%d productos=%d ventas=%d cotizaciones=%d rechazos=%d",
             n_cli, n_prod, n_ven, n_cot, len(rech))
    return {"clientes": n_cli, "productos": n_prod, "ventas": n_ven, "cotizaciones": n_cot, "rechazos": len(rech)}
