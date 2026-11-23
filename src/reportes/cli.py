"""Interfaz de línea de comandos: `reportes <comando>` o `python -m reportes <comando>`."""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys

from . import generate_data, pipeline
from .config import Config, configurar_logging

log = logging.getLogger("reportes")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reportes", description="Pipeline ETL de automatización de reportes")
    p.add_argument("--home", help="Carpeta raíz de datos/salidas (por defecto: REPORTES_HOME o la del proyecto)")
    p.add_argument("--umbral", type=float, help="Tasa máxima de rechazos tolerada (0-1). Si se supera, el código de salida es 2")
    sub = p.add_subparsers(dest="comando", required=True)
    g = sub.add_parser("generar-datos", help="Genera CSV sintéticos con errores intencionales")
    g.add_argument("--filas", type=int, default=12000)
    g.add_argument("--semilla", type=int, default=42)
    sub.add_parser("etl", help="Extrae, transforma y carga al warehouse SQLite")
    sub.add_parser("reportes", help="Genera los reportes Excel y HTML desde el warehouse")
    t = sub.add_parser("ejecutar", help="Corrida completa: (datos) + ETL + reportes")
    t.add_argument("--regenerar", action="store_true", help="Regenera los datos sintéticos antes de correr")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = Config.desde_entorno(args.home)
    if args.umbral is not None:
        cfg = dataclasses.replace(cfg, umbral_rechazos=args.umbral)
    configurar_logging(cfg)
    try:
        if args.comando == "generar-datos":
            res = generate_data.generar(cfg.data_dir, args.filas, args.semilla)
        elif args.comando == "etl":
            res = pipeline.ejecutar_etl(cfg)
        elif args.comando == "reportes":
            res = {k: str(v) for k, v in pipeline.ejecutar_reportes(cfg).items()}
        else:
            res = pipeline.ejecutar_todo(cfg, args.regenerar)
    except Exception as exc:  # código de salida != 0 para que el scheduler detecte el fallo
        log.exception("El pipeline falló: %s", exc)
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2))
    etl = res.get("etl", res)
    return 2 if isinstance(etl, dict) and etl.get("alerta") else 0


if __name__ == "__main__":
    sys.exit(main())
