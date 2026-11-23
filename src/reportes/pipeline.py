"""Orquestación del pipeline completo: extraer -> transformar -> cargar -> reportar."""
from __future__ import annotations

import logging
import time

from . import extract, generate_data, load, reports, transform
from .config import Config

log = logging.getLogger(__name__)


def ejecutar_etl(cfg: Config, incremental: bool = False) -> dict:
    """ETL completo o incremental.

    Incremental: procesa solo ventas con fecha >= última fecha cargada (marca de agua).
    Se solapa el último día a propósito (datos tardíos); el upsert evita duplicados.
    """
    t0 = time.perf_counter()
    conn = load.conectar(cfg.db_path)
    try:
        load.inicializar(conn, cfg.sql_dir)
        desde = load.marca_de_agua(conn) if incremental else None
        ignorar = load.ids_ventas_rechazadas(conn) if desde else None
        crudo = extract.extraer_todo(cfg.data_dir)
        cotizaciones = extract.extraer_cotizaciones(cfg.data_dir, cfg.url_cotizaciones) if cfg.url_cotizaciones else None
        datos = transform.transformar(crudo, desde, ignorar, cotizaciones)
        leidas = sum(len(d) for d in crudo.values()) - datos["omitidas"] + datos["cotizaciones_leidas"]
        run_id = load.iniciar_run(conn, leidas)
        stats = load.cargar(conn, datos, run_id)
    finally:
        conn.close()
    tasa = stats["rechazos"] / leidas if leidas else 0.0
    stats.update(run_id=run_id, modo="incremental" if desde else "completa", desde=desde,
                 omitidas=datos["omitidas"], segundos=round(time.perf_counter() - t0, 2),
                 tasa_rechazos=round(tasa, 4), alerta=tasa > cfg.umbral_rechazos)
    log.info("ETL %s OK en %.2fs (run %s)%s", stats["modo"], stats["segundos"], run_id,
             f" | desde {desde}, {datos['omitidas']} filas ya cargadas omitidas" if desde else "")
    if stats["alerta"]:
        log.warning("ALERTA DE CALIDAD: %.2f %% de filas rechazadas supera el umbral de %.2f %%",
                    tasa * 100, cfg.umbral_rechazos * 100)
    return stats


def ejecutar_reportes(cfg: Config) -> dict:
    conn = load.conectar(cfg.db_path)
    try:
        archivos = reports.generar_reportes(conn, cfg.sql_dir, cfg.out_dir)
        archivos["powerbi"] = reports.exportar_powerbi(conn, cfg.out_dir, cfg.db_path)
        return archivos
    finally:
        conn.close()


def ejecutar_todo(cfg: Config, regenerar: bool = False, incremental: bool = False) -> dict:
    """Corrida completa. Si no hay datos fuente (o se pide), genera los sintéticos."""
    if regenerar or not (cfg.data_dir / "ventas.csv").exists():
        generate_data.generar(cfg.data_dir)
    stats = ejecutar_etl(cfg, incremental)
    archivos = ejecutar_reportes(cfg)
    return {"etl": stats, "reportes": {k: str(v) for k, v in archivos.items()}}
