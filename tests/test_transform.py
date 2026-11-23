import pandas as pd

from reportes import transform


def _ventas(**cambios):
    base = {"id_venta": "V-1", "fecha": "2026-03-10", "id_cliente": "C-1", "id_producto": "P-1",
            "vendedor": "Ana", "cantidad": "2", "precio_unitario": "100", "descuento": "0.1"}
    base.update(cambios)
    return base


CLI = pd.DataFrame({"id_cliente": ["C-1"]})
PROD = pd.DataFrame({"id_producto": ["P-1"]})


def _limpiar(*filas):
    return transform.limpiar_ventas(pd.DataFrame(filas), CLI, PROD)


def test_calcula_importes():
    ok, rech = _limpiar(_ventas())
    assert rech.empty
    assert ok.loc[0, "importe_bruto"] == 200.0
    assert ok.loc[0, "importe_neto"] == 180.0


def test_rechaza_cada_error_con_su_motivo():
    casos = {
        "fecha inválida o vacía": _ventas(id_venta="a", fecha="31/02/2026"),
        "cantidad no positiva o inválida": _ventas(id_venta="b", cantidad="-1"),
        "precio_unitario inválido": _ventas(id_venta="c", precio_unitario="abc"),
        "descuento fuera de rango 0-1": _ventas(id_venta="d", descuento="1.5"),
        "cliente inexistente": _ventas(id_venta="e", id_cliente="C-9"),
        "producto inexistente o vacío": _ventas(id_venta="f", id_producto=""),
    }
    ok, rech = _limpiar(*casos.values())
    assert ok.empty
    assert dict(zip(rech["clave"], rech["motivo"])) == {
        v["id_venta"]: motivo for motivo, v in casos.items()}


def test_duplicados_y_valores_por_defecto():
    ok, rech = _limpiar(_ventas(), _ventas(), _ventas(id_venta="V-2", vendedor="", descuento=""))
    assert len(ok) == 2 and (rech["motivo"] == "id_venta duplicado").sum() == 1
    fila = ok[ok["id_venta"] == "V-2"].iloc[0]
    assert fila["vendedor"] == "Sin asignar" and fila["descuento"] == 0


def test_normaliza_clientes():
    raw = pd.DataFrame([
        {"id_cliente": "C-1", "nombre": "A", "email": "A@X.COM", "region": " amba ", "segmento": "minorista"},
        {"id_cliente": "C-1", "nombre": "A", "email": "A@X.COM", "region": " amba ", "segmento": "minorista"},
    ])
    ok, rech = transform.limpiar_clientes(raw)
    assert len(ok) == 1 and len(rech) == 1
    assert ok.loc[0, "region"] == "AMBA" and ok.loc[0, "email"] == "a@x.com"


def test_dim_fecha_continua():
    cal = transform.construir_dim_fecha(pd.Series(["2026-01-30", "2026-02-02"]))
    assert list(cal["fecha"]) == ["2026-01-30", "2026-01-31", "2026-02-01", "2026-02-02"]
    assert list(cal["anio_mes"].unique()) == ["2026-01", "2026-02"]
