import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError

from helpers import consulta
from reportes import db, extract, generate_data, load, pipeline, transform
from reportes.config import Config


def test_etl_carga_y_audita(cfg_poblada):
    (leidas, cargadas, rechazadas, estado), = consulta(
        cfg_poblada, "SELECT filas_leidas, filas_cargadas, filas_rechazadas, estado FROM etl_runs")
    assert estado == "OK" and rechazadas > 0
    (n_ventas,), = consulta(cfg_poblada, "SELECT COUNT(*) FROM fact_ventas")
    (n_rech_ventas,), = consulta(cfg_poblada, "SELECT COUNT(*) FROM etl_rechazos WHERE tabla='ventas'")
    # Conservación: todo lo leído de ventas está cargado o rechazado, nada se pierde
    assert n_ventas + n_rech_ventas == len(pd.read_csv(cfg_poblada.data_dir / "ventas.csv"))


def test_integridad_referencial(cfg_poblada):
    huerfanas = consulta(cfg_poblada, """SELECT COUNT(*) FROM fact_ventas v
        LEFT JOIN dim_cliente c ON c.id_cliente = v.id_cliente
        LEFT JOIN dim_producto p ON p.id_producto = v.id_producto
        WHERE c.id_cliente IS NULL OR p.id_producto IS NULL""")
    assert huerfanas == [(0,)]


def test_etl_es_idempotente(tmp_path, db_url):
    cfg = Config(tmp_path, db_url=db_url)
    generate_data.generar(cfg.data_dir, filas=800, semilla=3)
    pipeline.ejecutar_etl(cfg)
    antes = consulta(cfg, "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas")
    pipeline.ejecutar_etl(cfg)
    assert consulta(cfg, "SELECT COUNT(*), ROUND(SUM(importe_neto), 2) FROM fact_ventas") == antes
    assert consulta(cfg, "SELECT COUNT(*) FROM etl_runs") == [(2,)]


def test_carga_falla_y_hace_rollback(tmp_path, db_url):
    cfg = Config(tmp_path, db_url=db_url)
    generate_data.generar(cfg.data_dir, filas=300, semilla=1)
    datos = transform.transformar(extract.extraer_todo(cfg.data_dir))
    datos["ventas"].loc[0, "cantidad"] = -5          # viola el CHECK de la tabla
    engine = db.crear_engine(cfg.url_db)
    load.inicializar(engine, cfg.sql_dir)
    run = load.iniciar_run(engine, 0)
    with pytest.raises(IntegrityError):
        load.cargar(engine, datos, run)
    engine.dispose()
    assert consulta(cfg, "SELECT COUNT(*) FROM dim_cliente") == [(0,)]          # rollback total
    assert consulta(cfg, "SELECT estado FROM etl_runs") == [("ERROR",)]


def test_reportes_generan_archivos_y_cuadran(cfg_poblada):
    archivos = pipeline.ejecutar_reportes(cfg_poblada)
    assert archivos["excel"].stat().st_size > 5000 and archivos["html"].stat().st_size > 5000
    hojas = pd.read_excel(archivos["excel"], sheet_name=None)
    assert {"Resumen", "Mensual", "Top productos", "Regiones", "Vendedores", "Calidad de datos"} <= set(hojas)
    total_sql = consulta(cfg_poblada, "SELECT ROUND(SUM(importe_neto), 2) FROM fact_ventas")[0][0]
    assert hojas["Mensual"]["ventas_netas"].sum() == pytest.approx(total_sql, abs=0.05)
    assert hojas["Regiones"]["ventas_netas"].sum() == pytest.approx(total_sql, abs=0.05)
    assert "Reporte automático de ventas" in archivos["html"].read_text(encoding="utf-8")


def test_reportes_sin_datos_da_error_claro(tmp_path, db_url):
    cfg = Config(tmp_path, db_url=db_url)
    engine = db.crear_engine(cfg.url_db)
    load.inicializar(engine, cfg.sql_dir)
    engine.dispose()
    with pytest.raises(RuntimeError, match="ejecutá primero el ETL"):
        pipeline.ejecutar_reportes(cfg)


def test_cli_devuelve_codigo_de_error_si_falta_fuente(tmp_path):
    from reportes.cli import main
    assert main(["--home", str(tmp_path), "etl"]) == 1
