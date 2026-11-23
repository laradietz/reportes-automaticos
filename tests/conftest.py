import pytest

from reportes import generate_data, pipeline
from reportes.config import Config


@pytest.fixture(scope="session")
def cfg_poblada(tmp_path_factory):
    """Pipeline completo sobre un dataset chico, compartido entre tests."""
    cfg = Config(tmp_path_factory.mktemp("home"))
    generate_data.generar(cfg.data_dir, filas=2000, semilla=7)
    pipeline.ejecutar_etl(cfg)
    return cfg
