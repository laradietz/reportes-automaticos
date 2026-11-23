"""Fixtures. Los tests centrales corren contra SQLite y contra un PostgreSQL real.

PostgreSQL: si existe TEST_POSTGRES_URL (p. ej. el servicio de CI) se usa ese servidor; si no, se levanta
uno descartable con `pgserver` (PostgreSQL 16 embebido, sin instalar nada). Cada test usa su propia base.
"""
import logging
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from reportes import db, generate_data, pipeline
from reportes.config import Config

logging.getLogger("pgserver").setLevel(logging.CRITICAL)  # su log al cerrar el intérprete ensucia la salida


@pytest.fixture(scope="session")
def pg_admin_url(tmp_path_factory):
    url = os.environ.get("TEST_POSTGRES_URL")
    if url:
        yield url
        return
    try:
        import pgserver
    except ImportError:
        pytest.skip("PostgreSQL no disponible: instalar `pgserver` o definir TEST_POSTGRES_URL")
    servidor = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    yield servidor.get_uri()
    servidor.cleanup()


def _nueva_base(admin_url: str) -> str:
    nombre = "t_" + uuid.uuid4().hex[:12]
    engine = db.crear_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {nombre}"))
    engine.dispose()
    return make_url(admin_url).set(database=nombre).render_as_string(hide_password=False)


@pytest.fixture(params=["sqlite", "postgres"])
def db_url(request):
    """None = SQLite por defecto (archivo en tmp_path); si no, URL de una base PostgreSQL nueva."""
    if request.param == "sqlite":
        return None
    return _nueva_base(request.getfixturevalue("pg_admin_url"))


@pytest.fixture(scope="session", params=["sqlite", "postgres"])
def cfg_poblada(request, tmp_path_factory):
    """Pipeline completo sobre un dataset chico, compartido entre tests (una vez por motor)."""
    url = None if request.param == "sqlite" else _nueva_base(request.getfixturevalue("pg_admin_url"))
    cfg = Config(tmp_path_factory.mktemp("home"), db_url=url)
    generate_data.generar(cfg.data_dir, filas=2000, semilla=7)
    pipeline.ejecutar_etl(cfg)
    return cfg
