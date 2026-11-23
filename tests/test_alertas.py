import json

from reportes import generate_data, pipeline
from reportes.cli import main
from reportes.config import Config


def _cfg(tmp_path, umbral):
    cfg = Config(tmp_path, umbral)
    generate_data.generar(cfg.data_dir, filas=1500, semilla=5)
    return cfg


def test_alerta_si_se_supera_el_umbral(tmp_path):
    stats = pipeline.ejecutar_etl(_cfg(tmp_path, umbral=0.001))
    assert stats["alerta"] is True
    assert stats["tasa_rechazos"] > 0.001


def test_sin_alerta_si_esta_bajo_el_umbral(tmp_path):
    stats = pipeline.ejecutar_etl(_cfg(tmp_path, umbral=0.5))
    assert stats["alerta"] is False


def test_cli_devuelve_2_cuando_hay_alerta(tmp_path, capsys):
    _cfg(tmp_path, umbral=0.5)
    assert main(["--home", str(tmp_path), "--umbral", "0.001", "etl"]) == 2
    assert json.loads(capsys.readouterr().out)["alerta"] is True
    assert main(["--home", str(tmp_path), "--umbral", "0.5", "etl"]) == 0
