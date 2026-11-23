"""E — Extracción. Lee las fuentes crudas y valida que tengan las columnas esperadas."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

COLUMNAS = {
    "clientes": ["id_cliente", "nombre", "email", "region", "segmento"],
    "productos": ["id_producto", "nombre", "categoria", "precio_lista"],
    "ventas": ["id_venta", "fecha", "id_cliente", "id_producto", "vendedor", "cantidad", "precio_unitario", "descuento"],
}


def leer_fuente(data_dir: Path, nombre: str) -> pd.DataFrame:
    """Lee <nombre>.csv como texto (sin inferir tipos: la limpieza decide los tipos)."""
    ruta = data_dir / f"{nombre}.csv"
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró la fuente '{ruta}'. Ejecutá primero: reportes generar-datos")
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8")
    faltantes = set(COLUMNAS[nombre]) - set(df.columns)
    if faltantes:
        raise ValueError(f"A '{ruta.name}' le faltan columnas: {sorted(faltantes)}")
    log.info("Extraído %-9s %6d filas", nombre, len(df))
    return df[COLUMNAS[nombre]]


def extraer_todo(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {n: leer_fuente(data_dir, n) for n in COLUMNAS}
