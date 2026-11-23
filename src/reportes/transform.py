"""T — Transformación. Limpia, valida y calcula métricas.

Principio: ningún registro malo se pierde en silencio. Cada fila descartada
queda registrada con el motivo (tabla `etl_rechazos`) para poder auditarla.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

import pandas as pd

log = logging.getLogger(__name__)

COLUMNAS_RECHAZO = ["tabla", "clave", "motivo", "registro"]


def _vacio_a_na(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    return df


def _rechazos(df: pd.DataFrame, tabla: str, clave: str, motivo: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_RECHAZO)
    registros = [json.dumps({k: (None if pd.isna(v) else str(v)) for k, v in fila.items()}, ensure_ascii=False)
                 for fila in df.to_dict("records")]
    return pd.DataFrame({"tabla": tabla, "clave": df[clave].astype(object).where(df[clave].notna(), None),
                         "motivo": motivo, "registro": registros})


def _aplicar_reglas(df: pd.DataFrame, tabla: str, clave: str,
                    reglas: list[tuple[str, Callable[[pd.DataFrame], pd.Series]]]):
    """Aplica reglas en orden; cada regla devuelve una máscara de filas INVÁLIDAS."""
    descartes = []
    for motivo, invalida in reglas:
        mask = invalida(df).fillna(True).astype(bool)
        descartes.append(_rechazos(df[mask], tabla, clave, motivo))
        df = df[~mask]
    rechazos = pd.concat(descartes, ignore_index=True) if descartes else pd.DataFrame(columns=COLUMNAS_RECHAZO)
    return df.reset_index(drop=True), rechazos


def limpiar_clientes(raw: pd.DataFrame):
    df = _vacio_a_na(raw)
    df["region"] = df["region"].str.title().replace({"Amba": "AMBA", "Noa": "NOA", "Nea": "NEA"})
    df["email"] = df["email"].str.lower()
    df["segmento"] = df["segmento"].str.title()
    duplicado = df.duplicated("id_cliente", keep="last")
    rech_dup = _rechazos(df[duplicado], "clientes", "id_cliente", "id_cliente duplicado")
    df = df[~duplicado]
    df, rech = _aplicar_reglas(df, "clientes", "id_cliente", [
        ("id_cliente vacío", lambda d: d["id_cliente"].isna()),
        ("región vacía", lambda d: d["region"].isna()),
        ("nombre vacío", lambda d: d["nombre"].isna()),
    ])
    df["segmento"] = df["segmento"].fillna("Minorista")
    return df, pd.concat([rech_dup, rech], ignore_index=True)


def limpiar_productos(raw: pd.DataFrame):
    df = _vacio_a_na(raw)
    df["precio_lista"] = pd.to_numeric(df["precio_lista"], errors="coerce")
    duplicado = df.duplicated("id_producto", keep="last")
    rech_dup = _rechazos(df[duplicado], "productos", "id_producto", "id_producto duplicado")
    df = df[~duplicado]
    df, rech = _aplicar_reglas(df, "productos", "id_producto", [
        ("id_producto vacío", lambda d: d["id_producto"].isna()),
        ("precio_lista inválido", lambda d: ~(d["precio_lista"] > 0)),
    ])
    return df, pd.concat([rech_dup, rech], ignore_index=True)


def limpiar_ventas(raw: pd.DataFrame, clientes_ok: pd.DataFrame, productos_ok: pd.DataFrame,
                   desde: str | None = None, ignorar_ids: set[str] | None = None):
    """Limpia ventas. En modo incremental (`desde` / `ignorar_ids`) omite lo ya procesado:
    filas con fecha anterior a la marca de agua y filas ya rechazadas en corridas previas."""
    df = _vacio_a_na(raw)
    fecha = pd.to_datetime(df["fecha"], format="%Y-%m-%d", errors="coerce")
    omitidas = 0
    if desde or ignorar_ids:
        omitir = pd.Series(False, index=df.index)
        if desde:
            omitir |= fecha < pd.Timestamp(desde)  # fecha inválida (NaT) no cuenta como anterior
        if ignorar_ids:
            omitir |= df["id_venta"].isin(ignorar_ids)
        omitidas = int(omitir.sum())
        df, fecha = df[~omitir], fecha[~omitir]

    # Duplicados exactos del mismo id_venta: nos quedamos con la última aparición.
    duplicado = df.duplicated("id_venta", keep="last")
    rech_dup = _rechazos(df[duplicado], "ventas", "id_venta", "id_venta duplicado")
    df = df[~duplicado].copy()
    df["fecha"] = fecha[~duplicado]
    for col in ("cantidad", "precio_unitario", "descuento"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["descuento"] = df["descuento"].fillna(0.0)  # sin dato = sin descuento (regla de negocio)
    df["vendedor"] = df["vendedor"].fillna("Sin asignar")

    cli, prod = set(clientes_ok["id_cliente"]), set(productos_ok["id_producto"])
    df, rech = _aplicar_reglas(df, "ventas", "id_venta", [
        ("id_venta vacío", lambda d: d["id_venta"].isna()),
        ("fecha inválida o vacía", lambda d: d["fecha"].isna()),
        ("cantidad no positiva o inválida", lambda d: ~(d["cantidad"] > 0)),
        ("precio_unitario inválido", lambda d: ~(d["precio_unitario"] > 0)),
        ("descuento fuera de rango 0-1", lambda d: ~d["descuento"].between(0, 1)),
        ("cliente inexistente", lambda d: ~d["id_cliente"].isin(cli)),
        ("producto inexistente o vacío", lambda d: ~d["id_producto"].isin(prod)),
    ])

    df["cantidad"] = df["cantidad"].astype(int)
    df["importe_bruto"] = (df["cantidad"] * df["precio_unitario"]).round(2)
    df["importe_neto"] = (df["importe_bruto"] * (1 - df["descuento"])).round(2)
    df["fecha"] = df["fecha"].dt.strftime("%Y-%m-%d")
    df.attrs["omitidas"] = omitidas
    return df, pd.concat([rech_dup, rech], ignore_index=True)


def construir_dim_fecha(fechas: pd.Series) -> pd.DataFrame:
    """Dimensión calendario continua entre la primera y la última fecha."""
    f = pd.to_datetime(fechas)
    cal = pd.DataFrame({"fecha": pd.date_range(f.min(), f.max(), freq="D")})
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    cal["anio"] = cal["fecha"].dt.year
    cal["mes"] = cal["fecha"].dt.month
    cal["anio_mes"] = cal["fecha"].dt.strftime("%Y-%m")
    cal["trimestre"] = cal["fecha"].dt.quarter
    cal["dia_semana"] = cal["fecha"].dt.day_of_week.map(lambda i: dias[i])
    cal["fecha"] = cal["fecha"].dt.strftime("%Y-%m-%d")
    return cal


def transformar(raw: dict[str, pd.DataFrame], desde: str | None = None,
                ignorar_ids: set[str] | None = None) -> dict:
    clientes, r_cli = limpiar_clientes(raw["clientes"])
    productos, r_prod = limpiar_productos(raw["productos"])
    ventas, r_ven = limpiar_ventas(raw["ventas"], clientes, productos, desde, ignorar_ids)
    rechazos = pd.concat([r_cli, r_prod, r_ven], ignore_index=True)
    log.info("Transformado: clientes=%d productos=%d ventas=%d | rechazos=%d",
             len(clientes), len(productos), len(ventas), len(rechazos))
    return {"clientes": clientes, "productos": productos, "ventas": ventas,
            "omitidas": ventas.attrs.get("omitidas", 0),
            "fechas": construir_dim_fecha(ventas["fecha"]) if len(ventas) else pd.DataFrame(),
            "rechazos": rechazos}
