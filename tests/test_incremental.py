import sqlite3

import pytest

from reportes import generate_data, pipeline
from reportes.config import Config


def _q(cfg, sql):
    with sqlite3.connect(cfg.db_path) as c:
        return c.execute(sql).fetchall()


@pytest.fixture
def cfg(tmp_path):
    cfg = Config(tmp_path, umbral_rechazos=1.0)
    generate_data.generar(cfg.data_dir, filas=1500, semilla=11)
    return cfg


def test_primera_corrida_incremental_equivale_a_completa(cfg):
    stats = pipeline.ejecutar_etl(cfg, incremental=True)   # warehouse vacío: no hay marca de agua
    assert stats["modo"] == "completa" and stats["omitidas"] == 0


def test_incremental_procesa_solo_lo_nuevo(cfg):
    pipeline.ejecutar_etl(cfg)
    (antes,), = _q(cfg, "SELECT COUNT(*) FROM fact_ventas")
    (marca,), = _q(cfg, "SELECT MAX(fecha) FROM fact_ventas")

    generate_data.agregar_novedades(cfg.data_dir, filas=200)
    stats = pipeline.ejecutar_etl(cfg, incremental=True)

    assert stats["modo"] == "incremental" and stats["desde"] == marca
    assert stats["omitidas"] > 1000                      # lo viejo ni se toca
    (despues,), = _q(cfg, "SELECT COUNT(*) FROM fact_ventas")
    # Entran las 200 nuevas; las del día de la marca (solape) ya existían y no se duplican
    assert despues == antes + 200


def test_incremental_equivale_a_recarga_completa(cfg, tmp_path):
    pipeline.ejecutar_etl(cfg)
    generate_data.agregar_novedades(cfg.data_dir, filas=300)
    pipeline.ejecutar_etl(cfg, incremental=True)
    incremental = _q(cfg, "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas")

    completa = Config(tmp_path / "otra", umbral_rechazos=1.0)
    completa.data_dir.mkdir(parents=True)
    for f in cfg.data_dir.glob("*.csv"):
        (completa.data_dir / f.name).write_bytes(f.read_bytes())
    pipeline.ejecutar_etl(completa)
    assert _q(completa, "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas") == incremental


def test_incremental_sin_novedades_no_duplica(cfg):
    pipeline.ejecutar_etl(cfg)
    antes = _q(cfg, "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas")
    pipeline.ejecutar_etl(cfg, incremental=True)
    assert _q(cfg, "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas") == antes


def test_incremental_no_reporta_de_nuevo_rechazos_viejos(tmp_path):
    cfg = Config(tmp_path, umbral_rechazos=0.05)
    generate_data.generar(cfg.data_dir, filas=1500, semilla=11)
    pipeline.ejecutar_etl(cfg)
    generate_data.agregar_novedades(cfg.data_dir, filas=200)
    stats = pipeline.ejecutar_etl(cfg, incremental=True)
    assert stats["alerta"] is False
    assert stats["rechazos"] < 20       # solo problemas de dimensiones, no los ~100 viejos de ventas
