"""E — Extracción. Lee las fuentes crudas y valida que tengan las columnas esperadas."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
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


def descargar_json(url: str, timeout: float = 20, reintentos: int = 3, espera: float = 1.0):
    """GET con timeout y reintentos con espera creciente. No envía ningún dato del usuario."""
    ultimo: Exception | None = None
    for intento in range(1, reintentos + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "reportes-etl/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            ultimo = exc
            log.warning("API: intento %d/%d falló (%s)", intento, reintentos, exc)
            if intento < reintentos:
                time.sleep(espera * intento)
    raise ConnectionError(f"No se pudo obtener la API tras {reintentos} intentos: {ultimo}")


def extraer_cotizaciones(data_dir: Path, url: str) -> pd.DataFrame | None:
    """Descarga las cotizaciones y deja una copia local (data/raw/cotizaciones.csv).

    Si la API no responde usa la última copia local; si tampoco hay copia devuelve None
    y el pipeline sigue sin conversión a dólares (la fuente es opcional)."""
    copia = data_dir / "cotizaciones.csv"
    try:
        datos = descargar_json(url)
        df = pd.DataFrame(datos)
        faltantes = {"fecha", "compra", "venta"} - set(df.columns)
        if faltantes:
            raise ValueError(f"La API no devolvió las columnas {sorted(faltantes)}")
        df = df[["fecha", "compra", "venta"]].astype(str)
        data_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(copia, index=False, encoding="utf-8")
        log.info("Extraído cotizaciones (API) %6d filas", len(df))
        return df
    except (ConnectionError, ValueError) as exc:
        if copia.exists():
            log.warning("API no disponible (%s): se usa la copia local %s", exc, copia.name)
            return pd.read_csv(copia, dtype=str, keep_default_na=False)
        log.warning("API no disponible y sin copia local (%s): se continúa sin cotizaciones", exc)
        return None
