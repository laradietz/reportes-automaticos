import pytest

from helpers import consulta
from reportes import generate_data, pipeline
from reportes.config import Config

TOTALES = "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas"


@pytest.fixture
def cfg(tmp_path, db_url):
    cfg = Config(tmp_path, umbral_rechazos=1.0, db_url=db_url)
    generate_data.generar(cfg.data_dir, filas=1500, semilla=11)
    return cfg


def test_primera_corrida_incremental_equivale_a_completa(cfg):
    stats = pipeline.ejecutar_etl(cfg, incremental=True)   # warehouse vacío: no hay marca de agua
    assert stats["modo"] == "completa" and stats["omitidas"] == 0


def test_incremental_procesa_solo_lo_nuevo(cfg):
    pipeline.ejecutar_etl(cfg)
    (antes,), = consulta(cfg, "SELECT COUNT(*) FROM fact_ventas")
    (marca,), = consulta(cfg, "SELECT MAX(fecha) FROM fact_ventas")

    generate_data.agregar_novedades(cfg.data_dir, filas=200)
    stats = pipeline.ejecutar_etl(cfg, incremental=True)

    assert stats["modo"] == "incremental" and stats["desde"] == marca
    assert stats["omitidas"] > 1000                      # lo viejo ni se toca
    (despues,), = consulta(cfg, "SELECT COUNT(*) FROM fact_ventas")
    # Entran las 200 nuevas; las del día de la marca (solape) ya existían y no se duplican
    assert despues == antes + 200


def test_incremental_equivale_a_recarga_completa(cfg, tmp_path, db_url):
    pipeline.ejecutar_etl(cfg)
    generate_data.agregar_novedades(cfg.data_dir, filas=300)
    pipeline.ejecutar_etl(cfg, incremental=True)
    incremental = consulta(cfg, TOTALES)

    # Misma fuente cargada de cero en otra base: debe dar exactamente lo mismo
    completa = Config(tmp_path / "otra", umbral_rechazos=1.0, db_url=_otra_base(db_url))
    completa.data_dir.mkdir(parents=True)
    for f in cfg.data_dir.glob("*.csv"):
        (completa.data_dir / f.name).write_bytes(f.read_bytes())
    pipeline.ejecutar_etl(completa)
    assert consulta(completa, TOTALES) == incremental


def _otra_base(db_url):
    """Segunda base del mismo motor (en PostgreSQL, una base nueva en el mismo servidor)."""
    if db_url is None:
        return None
    from conftest import _nueva_base
    return _nueva_base(db_url)


def test_incremental_sin_novedades_no_duplica(cfg):
    pipeline.ejecutar_etl(cfg)
    antes = consulta(cfg, TOTALES)
    pipeline.ejecutar_etl(cfg, incremental=True)
    assert consulta(cfg, TOTALES) == antes


def test_incremental_no_reporta_de_nuevo_rechazos_viejos(tmp_path, db_url):
    cfg = Config(tmp_path, umbral_rechazos=0.05, db_url=db_url)
    generate_data.generar(cfg.data_dir, filas=1500, semilla=11)
    pipeline.ejecutar_etl(cfg)
    generate_data.agregar_novedades(cfg.data_dir, filas=200)
    stats = pipeline.ejecutar_etl(cfg, incremental=True)
    assert stats["alerta"] is False
    assert stats["rechazos"] < 20       # solo problemas de dimensiones, no los ~100 viejos de ventas
