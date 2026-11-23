"""Pruebas específicas de PostgreSQL: tipos nativos, CLI con --db-url y que no se filtren contraseñas."""
import logging

import pytest
from sqlalchemy.engine import make_url

from conftest import _nueva_base
from helpers import consulta
from reportes import generate_data
from reportes.cli import main
from reportes.config import Config


@pytest.fixture
def url(pg_admin_url):
    return _nueva_base(pg_admin_url)


def test_tipos_nativos_de_postgres(tmp_path, url):
    cfg = Config(tmp_path, db_url=url)
    generate_data.generar(cfg.data_dir, filas=300, semilla=4)
    assert main(["--home", str(tmp_path), "--db-url", url, "--sin-api", "--umbral", "1", "etl"]) == 0
    tipos = dict(consulta(cfg, """SELECT table_name || '.' || column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND (table_name, column_name) IN
        (('fact_ventas', 'fecha'), ('fact_ventas', 'importe_neto'), ('dim_fecha', 'fecha'), ('etl_runs', 'inicio'))"""))
    assert tipos == {"fact_ventas.fecha": "date", "fact_ventas.importe_neto": "numeric",
                     "dim_fecha.fecha": "date", "etl_runs.inicio": "timestamp without time zone"}


def test_cli_genera_reportes_desde_postgres(tmp_path, url):
    generate_data.generar(Config(tmp_path).data_dir, filas=400, semilla=4)
    assert main(["--home", str(tmp_path), "--db-url", url, "--sin-api", "--umbral", "1", "ejecutar"]) == 0
    assert list((tmp_path / "output").glob("reporte_ventas_*.xlsx"))
    assert not (tmp_path / "output" / "powerbi" / "conectar_sqlite.py").exists()   # el script es solo para SQLite
    assert (tmp_path / "output" / "powerbi" / "modelo_ventas.xlsx").exists()


def test_la_clave_no_se_escribe_en_los_logs(tmp_path, pg_admin_url, caplog):
    url = make_url(_nueva_base(pg_admin_url)).set(password="clave-secreta-123").render_as_string(hide_password=False)
    cfg = Config(tmp_path, db_url=url)
    assert "clave-secreta-123" in cfg.url_db
    from reportes import db
    engine = db.crear_engine("postgresql://usuario:clave-secreta-123@localhost/base")
    with caplog.at_level(logging.INFO):
        logging.getLogger("x").info("conectando a %s", db.descripcion(engine))
    assert "clave-secreta-123" not in caplog.text and "***" in caplog.text


def test_db_url_por_variable_de_entorno(monkeypatch, tmp_path, url):
    monkeypatch.setenv("REPORTES_DB_URL", url)
    assert Config.desde_entorno(tmp_path).url_db == url
    monkeypatch.delenv("REPORTES_DB_URL")
    assert Config.desde_entorno(tmp_path).url_db.startswith("sqlite:///")


def test_los_reportes_dan_lo_mismo_en_sqlite_y_postgres(tmp_path, url):
    """Mismos datos en ambos motores: cada consulta de los reportes debe devolver el mismo resultado."""
    from pandas.testing import assert_frame_equal

    from reportes import db, pipeline, reports

    sqlite_cfg = Config(tmp_path / "sqlite", umbral_rechazos=1.0)
    pg_cfg = Config(tmp_path / "pg", umbral_rechazos=1.0, db_url=url)
    generate_data.generar(sqlite_cfg.data_dir, filas=3000, semilla=21)
    pg_cfg.data_dir.mkdir(parents=True)
    for f in sqlite_cfg.data_dir.glob("*.csv"):
        (pg_cfg.data_dir / f.name).write_bytes(f.read_bytes())

    resultados = {}
    for nombre, cfg in (("sqlite", sqlite_cfg), ("postgres", pg_cfg)):
        pipeline.ejecutar_etl(cfg)
        engine = db.crear_engine(cfg.url_db)
        with engine.connect() as conn:
            resultados[nombre] = reports.cargar_datos(conn, cfg.sql_dir)
        engine.dispose()

    for consulta in reports.CONSULTAS:
        if consulta == "ultima_corrida":     # ids y horas distintos por naturaleza
            continue
        assert_frame_equal(resultados["sqlite"][consulta], resultados["postgres"][consulta],
                           check_dtype=False, rtol=1e-9, obj=consulta)


def test_top_productos_respeta_el_limite(cfg_poblada):
    from reportes import db, reports

    engine = db.crear_engine(cfg_poblada.url_db)
    with engine.connect() as conn:
        datos = reports.cargar_datos(conn, cfg_poblada.sql_dir)
    engine.dispose()
    assert len(datos["top_productos"]) == 15
    assert datos["top_productos"]["ranking"].tolist() == list(range(1, 16))
