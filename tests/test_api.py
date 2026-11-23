"""La fuente REST se prueba sin red: se reemplaza urllib.request.urlopen por una respuesta simulada."""
import io
import json
import sqlite3
import urllib.error

import pandas as pd
import pytest

from reportes import extract, generate_data, pipeline
from reportes.config import Config


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _api_falsa(monkeypatch, cotizacion=1000.0, desde="2025-12-01", hasta="2026-12-31", fallos=0):
    """Simula la API: una cotización por día. `fallos` = intentos que fallan antes de responder."""
    estado = {"llamadas": 0}
    dias = pd.date_range(desde, hasta, freq="D")
    cuerpo = json.dumps([{"casa": "oficial", "compra": cotizacion - 50, "venta": cotizacion,
                          "fecha": d.strftime("%Y-%m-%d")} for d in dias]).encode()

    def urlopen(req, timeout=None):
        estado["llamadas"] += 1
        if estado["llamadas"] <= fallos:
            raise urllib.error.URLError("sin conexión")
        return _Respuesta(cuerpo)

    monkeypatch.setattr(extract.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(extract.time, "sleep", lambda s: None)
    return estado


def test_descarga_y_guarda_copia_local(tmp_path, monkeypatch):
    _api_falsa(monkeypatch)
    df = extract.extraer_cotizaciones(tmp_path, "http://api.test/dolar")
    assert list(df.columns) == ["fecha", "compra", "venta"] and len(df) > 300
    assert (tmp_path / "cotizaciones.csv").exists()


def test_reintenta_ante_fallos_transitorios(tmp_path, monkeypatch):
    estado = _api_falsa(monkeypatch, fallos=2)
    df = extract.extraer_cotizaciones(tmp_path, "http://api.test/dolar")
    assert df is not None and estado["llamadas"] == 3


def test_si_la_api_cae_usa_la_copia_local(tmp_path, monkeypatch):
    _api_falsa(monkeypatch)
    extract.extraer_cotizaciones(tmp_path, "http://api.test/dolar")      # genera la copia
    _api_falsa(monkeypatch, fallos=99)                                    # ahora la API está caída
    df = extract.extraer_cotizaciones(tmp_path, "http://api.test/dolar")
    assert df is not None and len(df) > 300


def test_si_la_api_cae_y_no_hay_copia_devuelve_none(tmp_path, monkeypatch):
    _api_falsa(monkeypatch, fallos=99)
    assert extract.extraer_cotizaciones(tmp_path, "http://api.test/dolar") is None


def test_respuesta_sin_las_columnas_esperadas_se_rechaza(tmp_path, monkeypatch):
    monkeypatch.setattr(extract.urllib.request, "urlopen", lambda req, timeout=None: _Respuesta(b'[{"x": 1}]'))
    assert extract.extraer_cotizaciones(tmp_path, "http://api.test/dolar") is None


def _cfg(tmp_path, url="http://api.test/dolar"):
    cfg = Config(tmp_path, umbral_rechazos=1.0, url_cotizaciones=url)
    generate_data.generar(cfg.data_dir, filas=1500, semilla=8)
    return cfg


def test_pipeline_convierte_a_dolares(tmp_path, monkeypatch):
    _api_falsa(monkeypatch, cotizacion=1000.0)
    cfg = _cfg(tmp_path)
    stats = pipeline.ejecutar_etl(cfg)
    assert stats["cotizaciones"] > 0
    with sqlite3.connect(cfg.db_path) as c:
        neto, usd_ = c.execute(
            "SELECT SUM(importe_neto) FROM fact_ventas").fetchone()[0], None
    archivos = pipeline.ejecutar_reportes(cfg)
    hojas = pd.read_excel(archivos["excel"], sheet_name=None)
    assert "Ventas USD" in hojas
    # tipo de cambio constante 1000: USD = ARS / 1000
    assert hojas["Ventas USD"]["ventas_usd"].sum() == pytest.approx(neto / 1000, rel=1e-4)
    assert "Ventas netas en USD" in archivos["html"].read_text(encoding="utf-8")


def test_sin_api_los_reportes_siguen_funcionando(tmp_path):
    cfg = _cfg(tmp_path, url=None)
    stats = pipeline.ejecutar_etl(cfg)
    assert stats["cotizaciones"] == 0
    archivos = pipeline.ejecutar_reportes(cfg)
    assert "Ventas USD" not in pd.read_excel(archivos["excel"], sheet_name=None)


def test_cotizacion_invalida_se_rechaza_con_motivo(tmp_path, monkeypatch):
    cuerpo = json.dumps([
        {"fecha": "2026-03-10", "compra": 900, "venta": 1000},
        {"fecha": "2026-03-11", "compra": 900, "venta": -5},
        {"fecha": "no-es-fecha", "compra": 900, "venta": 1000},
        {"fecha": "2026-03-10", "compra": 900, "venta": 1001},   # duplicada: gana la última
    ]).encode()
    monkeypatch.setattr(extract.urllib.request, "urlopen", lambda req, timeout=None: _Respuesta(cuerpo))
    cfg = _cfg(tmp_path)
    pipeline.ejecutar_etl(cfg)
    with sqlite3.connect(cfg.db_path) as c:
        motivos = {m for (m,) in c.execute("SELECT motivo FROM etl_rechazos WHERE tabla = 'cotizaciones'")}
        (venta,), = c.execute("SELECT venta FROM dim_cotizacion WHERE fecha = '2026-03-10'").fetchall()
    assert {"fecha duplicada", "fecha inválida", "cotización de venta inválida"} <= motivos
    assert venta == 1001
