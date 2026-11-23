"""Utilidades de los tests: consultas independientes del motor (SQLite o PostgreSQL)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import text

from reportes import db


def _normalizar(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (dt.date, dt.datetime)):
        return valor.isoformat()[:10]
    return valor


def consulta(cfg, sql: str) -> list[tuple]:
    """Ejecuta SQL contra la base de `cfg` y devuelve tuplas con tipos simples (float, str)."""
    engine = db.crear_engine(cfg.url_db)
    try:
        with engine.connect() as conn:
            return [tuple(_normalizar(v) for v in fila) for fila in conn.execute(text(sql)).fetchall()]
    finally:
        engine.dispose()
