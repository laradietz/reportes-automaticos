"""Configuración centralizada. Todas las rutas cuelgan de una raíz configurable."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
# API pública sin clave: cotización diaria del dólar oficial (Argentina)
URL_COTIZACIONES = "https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial"


@dataclass(frozen=True)
class Config:
    raiz: Path = RAIZ_PROYECTO
    umbral_rechazos: float = 0.05  # fracción máxima tolerada de filas rechazadas
    url_cotizaciones: str | None = None  # None = no consultar la API (por defecto en la librería y los tests)

    @classmethod
    def desde_entorno(cls, raiz: str | os.PathLike | None = None) -> "Config":
        """Prioridad: argumento > variable REPORTES_HOME > raíz del proyecto."""
        valor = raiz or os.environ.get("REPORTES_HOME")
        umbral = float(os.environ.get("REPORTES_UMBRAL_RECHAZOS", cls.umbral_rechazos))
        url = os.environ.get("REPORTES_URL_COTIZACIONES", URL_COTIZACIONES)
        if url.strip().lower() in ("", "off", "none"):
            url = None
        return cls(Path(valor).resolve() if valor else RAIZ_PROYECTO, umbral, url)

    @property
    def data_dir(self) -> Path:
        return self.raiz / "data" / "raw"

    @property
    def db_path(self) -> Path:
        return self.raiz / "data" / "warehouse.db"

    @property
    def sql_dir(self) -> Path:
        return RAIZ_PROYECTO / "sql"

    @property
    def out_dir(self) -> Path:
        return self.raiz / "output"

    @property
    def log_dir(self) -> Path:
        return self.raiz / "logs"


def configurar_logging(cfg: Config, nivel: int = logging.INFO) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    formato = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        h.close()
        raiz.removeHandler(h)
    raiz.setLevel(nivel)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    for h in (logging.StreamHandler(), logging.FileHandler(cfg.log_dir / "pipeline.log", encoding="utf-8")):
        h.setFormatter(logging.Formatter(formato))
        raiz.addHandler(h)
