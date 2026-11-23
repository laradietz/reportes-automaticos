"""L — Carga. Upserts idempotentes en SQLite: re-ejecutar el ETL no duplica datos."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def conectar(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar(conn: sqlite3.Connection, sql_dir: Path) -> None:
    conn.executescript((sql_dir / "schema.sql").read_text(encoding="utf-8"))


def _filas(df: pd.DataFrame, cols: list[str]) -> list[list]:
    sub = df[cols].astype(object)
    return sub.where(sub.notna(), None).values.tolist()


def upsert(conn: sqlite3.Connection, tabla: str, df: pd.DataFrame, cols: list[str], pk: str) -> int:
    if df.empty:
        return 0
    marcas = ",".join("?" * len(cols))
    actualiza = ",".join(f"{c}=excluded.{c}" for c in cols if c != pk)
    sql = (f"INSERT INTO {tabla} ({','.join(cols)}) VALUES ({marcas}) "
           f"ON CONFLICT({pk}) DO UPDATE SET {actualiza}")
    conn.executemany(sql, _filas(df, cols))
    return len(df)


def marca_de_agua(conn: sqlite3.Connection) -> str | None:
    """Última fecha de venta cargada (None si el warehouse está vacío)."""
    return conn.execute("SELECT MAX(fecha) FROM fact_ventas").fetchone()[0]


def ids_ventas_rechazadas(conn: sqlite3.Connection) -> set[str]:
    """id_venta rechazados en corridas anteriores (no se reprocesan en modo incremental)."""
    filas = conn.execute("SELECT DISTINCT clave FROM etl_rechazos WHERE tabla = 'ventas' AND clave IS NOT NULL")
    return {f[0] for f in filas}


def iniciar_run(conn: sqlite3.Connection, leidas: int) -> str:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    conn.execute("INSERT INTO etl_runs(run_id, inicio, filas_leidas, estado) VALUES (?,?,?, 'EN_CURSO')",
                 (run_id, datetime.now().isoformat(timespec="seconds"), leidas))
    conn.commit()
    return run_id


def cargar(conn: sqlite3.Connection, datos: dict, run_id: str) -> dict:
    """Carga todo en UNA transacción: o entra completo o no entra nada."""
    try:
        with conn:  # commit/rollback automático
            n_cli = upsert(conn, "dim_cliente", datos["clientes"], ["id_cliente", "nombre", "email", "region", "segmento"], "id_cliente")
            n_prod = upsert(conn, "dim_producto", datos["productos"], ["id_producto", "nombre", "categoria", "precio_lista"], "id_producto")
            upsert(conn, "dim_fecha", datos["fechas"], ["fecha", "anio", "mes", "anio_mes", "trimestre", "dia_semana"], "fecha")
            n_ven = upsert(conn, "fact_ventas", datos["ventas"],
                           ["id_venta", "fecha", "id_cliente", "id_producto", "vendedor", "cantidad",
                            "precio_unitario", "descuento", "importe_bruto", "importe_neto"], "id_venta")
            rech = datos["rechazos"]
            if not rech.empty:
                filas = [(run_id, *r) for r in _filas(rech, ["tabla", "clave", "motivo", "registro"])]
                conn.executemany("INSERT INTO etl_rechazos(run_id,tabla,clave,motivo,registro) VALUES (?,?,?,?,?)", filas)
            conn.execute("UPDATE etl_runs SET fin=?, filas_cargadas=?, filas_rechazadas=?, estado='OK' WHERE run_id=?",
                         (datetime.now().isoformat(timespec="seconds"), n_cli + n_prod + n_ven, len(rech), run_id))
    except Exception:
        conn.execute("UPDATE etl_runs SET fin=?, estado='ERROR' WHERE run_id=?",
                     (datetime.now().isoformat(timespec="seconds"), run_id))
        conn.commit()
        raise
    log.info("Cargado: clientes=%d productos=%d ventas=%d rechazos=%d", n_cli, n_prod, n_ven, len(rech))
    return {"clientes": n_cli, "productos": n_prod, "ventas": n_ven, "rechazos": len(rech)}
