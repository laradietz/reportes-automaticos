"""Generación de reportes: ejecuta las consultas SQL y produce Excel + HTML."""
from __future__ import annotations

import base64
import html
import io
import logging
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin ventana: funciona en servidores / tareas programadas
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from openpyxl.chart import BarChart, Reference  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
from openpyxl.worksheet.table import Table, TableStyleInfo  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402

log = logging.getLogger(__name__)

AZUL, GRIS = "#1f4e79", "#8a96a3"
CONSULTAS = ["kpi_resumen", "ventas_mensuales", "top_productos", "ventas_region",
             "ventas_categoria", "ranking_vendedores", "calidad_motivos", "ultima_corrida",
             "kpi_usd", "ventas_usd_mensual"]
COLS_DINERO = {"ventas_netas", "ventas_mes_anterior", "acumulado", "ticket_promedio", "ventas_ultimo_mes",
               "tipo_cambio_promedio"}
COLS_USD = {"ventas_usd"}
COLS_PCT = {"variacion_pct", "participacion_pct", "acumulado_pct", "descuento_promedio_pct"}
NOMBRES_HOJA = {"ventas_mensuales": "Mensual", "top_productos": "Top productos", "ventas_region": "Regiones",
                "ventas_categoria": "Categorías", "ranking_vendedores": "Vendedores", "calidad_motivos": "Calidad de datos"}


def money(x: float) -> str:
    return "$ " + f"{x:,.0f}".replace(",", ".")


def usd(x: float) -> str:
    return "US$ " + f"{x:,.0f}".replace(",", ".")


def hay_usd(datos: dict[str, pd.DataFrame]) -> bool:
    k = datos["kpi_usd"]
    return not k.empty and pd.notna(k.loc[0, "ventas_usd"])


def num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def cargar_datos(conn: Connection, sql_dir: Path) -> dict[str, pd.DataFrame]:
    """Cada reporte es una consulta .sql versionada: la lógica de negocio vive en SQL."""
    datos = {n: pd.read_sql_query(text((sql_dir / "queries" / f"{n}.sql").read_text(encoding="utf-8")), conn)
             for n in CONSULTAS}
    if datos["kpi_resumen"].empty or pd.isna(datos["kpi_resumen"].loc[0, "ventas_netas"]):
        raise RuntimeError("No hay ventas cargadas en el warehouse: ejecutá primero el ETL.")
    return datos


def kpis(datos: dict[str, pd.DataFrame]) -> list[tuple[str, str, str]]:
    """Lista de (etiqueta, valor, detalle) para cabecera de reportes."""
    k = datos["kpi_resumen"].iloc[0]
    var = k["variacion_mom_pct"]
    detalle_mes = f"{k['ultimo_mes']}: " + ("sin mes previo" if pd.isna(var) else f"{var:+.1f}% vs mes anterior")
    extra = []
    if hay_usd(datos):
        u = datos["kpi_usd"].iloc[0]
        extra = [("Ventas netas en USD", usd(u["ventas_usd"]), f"dólar oficial promedio {money(u['tipo_cambio_promedio'])}")]
    return [
        ("Ventas netas", money(k["ventas_netas"]), detalle_mes),
        ("Órdenes", num(k["ordenes"]), f"{num(k['unidades'])} unidades"),
        ("Ticket promedio", money(k["ticket_promedio"]), "por orden"),
        ("Clientes activos", num(k["clientes_activos"]), f"descuento efectivo {k['descuento_efectivo_pct']:.1f}%"),
    ] + extra


# ------------------------------------------------------------------ Excel
def _formatear_hoja(ws) -> None:
    encabezado = {c.value: c.column for c in ws[1]}
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL.lstrip("#"))
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for nombre, col in encabezado.items():
        letra = ws.cell(row=1, column=col).column_letter
        ancho = max([len(str(nombre))] + [len(str(c.value)) for c in ws[letra][1:] if c.value is not None]) + 3
        ws.column_dimensions[letra].width = min(ancho, 48)
        fmt = '"US$" #,##0' if nombre in COLS_USD else '"$" #,##0' if nombre in COLS_DINERO else '0.0"%"' if nombre in COLS_PCT else None
        if fmt:
            for c in ws[letra][1:]:
                c.number_format = fmt
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = False


def generar_excel(datos: dict[str, pd.DataFrame], ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    resumen = pd.DataFrame([(a, b, c) for a, b, c in kpis(datos)], columns=["Indicador", "Valor", "Detalle"])
    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        resumen.to_excel(xw, sheet_name="Resumen", index=False)
        hojas = dict(NOMBRES_HOJA)
        if hay_usd(datos):
            hojas["ventas_usd_mensual"] = "Ventas USD"
        for clave, hoja in hojas.items():
            datos[clave].to_excel(xw, sheet_name=hoja, index=False)
        for ws in xw.book.worksheets:
            _formatear_hoja(ws)
        # Gráfico nativo de Excel (editable) en la hoja Mensual
        ws, n = xw.book["Mensual"], len(datos["ventas_mensuales"])
        graf = BarChart()
        graf.title, graf.y_axis.title, graf.height, graf.width = "Ventas netas por mes", "Ventas netas ($)", 8, 18
        graf.add_data(Reference(ws, min_col=3, min_row=1, max_row=n + 1), titles_from_data=True)
        graf.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n + 1))
        graf.legend = None
        ws.add_chart(graf, "H2")
    log.info("Excel generado: %s", ruta)
    return ruta


# ------------------------------------------------------------------ HTML
def _png_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _estilo(ax) -> None:
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.grid(axis="y", alpha=.25)
    ax.set_axisbelow(True)


def _graficos(datos: dict[str, pd.DataFrame]) -> dict[str, str]:
    g = {}
    m = datos["ventas_mensuales"]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.bar(m["anio_mes"], m["ventas_netas"] / 1e6, color=AZUL)
    ax.set_ylabel("Millones de $")
    _estilo(ax)
    ax.tick_params(axis="x", rotation=45)
    g["mensual"] = _png_b64(fig)

    t = datos["top_productos"].head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh(t["nombre"], t["ventas_netas"] / 1e6, color=AZUL)
    ax.set_xlabel("Millones de $")
    _estilo(ax)
    ax.grid(axis="x", alpha=.25)
    ax.grid(axis="y", visible=False)
    g["productos"] = _png_b64(fig)

    r = datos["ventas_region"].iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.barh(r["region"], r["participacion_pct"], color=AZUL)
    ax.set_xlabel("% de las ventas netas")
    _estilo(ax)
    ax.grid(axis="x", alpha=.25)
    ax.grid(axis="y", visible=False)
    g["regiones"] = _png_b64(fig)
    return g


def _tabla(df: pd.DataFrame) -> str:
    def fmt(col, v):
        if pd.isna(v):
            return "—"
        if col in COLS_USD:
            return usd(v)
        if col in COLS_DINERO:
            return money(v)
        if col in COLS_PCT:
            return f"{v:.1f}%"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return num(v)
        return html.escape(str(v))
    cab = "".join(f"<th>{html.escape(c.replace('_', ' '))}</th>" for c in df.columns)
    filas = "".join("<tr>" + "".join(f"<td>{fmt(c, v)}</td>" for c, v in zip(df.columns, fila)) + "</tr>"
                    for fila in df.itertuples(index=False))
    return f"<div class='tw'><table><thead><tr>{cab}</tr></thead><tbody>{filas}</tbody></table></div>"


CSS = """
:root{--azul:#1f4e79;--txt:#1d2733;--sut:#5b6877;--bg:#f5f7fa;--card:#fff;--borde:#e1e6ec}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 20px 56px}
header h1{margin:0;font-size:1.7rem}header p{margin:.25rem 0 0;color:var(--sut)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:24px 0}
.kpi{background:var(--card);border:1px solid var(--borde);border-radius:10px;padding:16px}
.kpi small{color:var(--sut);display:block}.kpi b{display:block;font-size:1.4rem;white-space:nowrap;margin:2px 0;color:var(--azul)}
section{background:var(--card);border:1px solid var(--borde);border-radius:10px;padding:18px 20px;margin-top:18px}
h2{margin:0 0 12px;font-size:1.1rem}img{max-width:100%;height:auto}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem}
th{background:var(--azul);color:#fff;text-align:left;padding:7px 10px;text-transform:capitalize;white-space:nowrap}
td{padding:6px 10px;border-bottom:1px solid var(--borde);white-space:nowrap}
tr:nth-child(even) td{background:#f8fafc}footer{margin-top:26px;color:var(--sut);font-size:.82rem}
"""


def generar_html(datos: dict[str, pd.DataFrame], ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img = _graficos(datos)
    c = datos["ultima_corrida"]
    corrida = (f"Corrida ETL {c.loc[0, 'run_id']}: {num(c.loc[0, 'filas_cargadas'])} registros cargados, "
               f"{num(c.loc[0, 'filas_rechazadas'])} rechazados "
               f"({100 * c.loc[0, 'filas_rechazadas'] / c.loc[0, 'filas_leidas']:.1f} % de lo leído).") if not c.empty else ""
    tarjetas = "".join(f"<div class='kpi'><small>{html.escape(a)}</small><b>{html.escape(b)}</b><small>{html.escape(d)}</small></div>"
                       for a, b, d in kpis(datos))

    def sec(titulo, cuerpo):
        return f"<section><h2>{titulo}</h2>{cuerpo}</section>"

    def graf(clave, alt):
        return f"<img alt='{alt}' src='data:image/png;base64,{img[clave]}'>"

    cuerpo = "".join([
        sec("Evolución mensual de ventas", graf("mensual", "Ventas netas por mes") + _tabla(datos["ventas_mensuales"])),
        sec("Top 10 productos (Pareto)", graf("productos", "Top 10 de productos por ventas") + _tabla(datos["top_productos"])),
        sec("Ventas por región", graf("regiones", "Participación por región") + _tabla(datos["ventas_region"])),
        sec("Ventas por categoría", _tabla(datos["ventas_categoria"])),
        sec("Ventas en dólares (API de cotizaciones)", _tabla(datos["ventas_usd_mensual"])) if hay_usd(datos) else "",
        sec("Ranking de vendedores", _tabla(datos["ranking_vendedores"])),
        sec("Calidad de datos: registros rechazados", _tabla(datos["calidad_motivos"]) if not datos["calidad_motivos"].empty
            else "<p>Sin rechazos en la última corrida.</p>"),
    ])
    documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                 f"<title>Reporte de ventas</title><style>{CSS}</style></head><body><main>"
                 f"<header><h1>Reporte automático de ventas</h1><p>Generado el {datetime.now():%d/%m/%Y %H:%M} · {html.escape(corrida)}</p></header>"
                 f"<div class='kpis'>{tarjetas}</div>{cuerpo}"
                 f"<footer>Generado automáticamente por el pipeline ETL (Python + SQL + SQLite).</footer></main></body></html>")
    ruta.write_text(documento, encoding="utf-8")
    log.info("HTML generado: %s", ruta)
    return ruta


def generar_reportes(conn: Connection, sql_dir: Path, out_dir: Path) -> dict[str, Path]:
    datos = cargar_datos(conn, sql_dir)
    sello = datetime.now().strftime("%Y%m%d")
    return {"excel": generar_excel(datos, out_dir / f"reporte_ventas_{sello}.xlsx"),
            "html": generar_html(datos, out_dir / f"reporte_ventas_{sello}.html")}


# ------------------------------------------------------------------ Power BI
TABLAS_MODELO = ["fact_ventas", "dim_cliente", "dim_producto", "dim_fecha", "dim_cotizacion"]


def exportar_powerbi(conn: Connection, out_dir: Path, db_path: Path | None = None) -> Path:
    """Exporta el modelo en estrella con nombres de archivo FIJOS (sin fecha),
    para que Power BI pueda actualizar la fuente con "Actualizar" sin reconfigurar."""
    carpeta = out_dir / "powerbi"
    carpeta.mkdir(parents=True, exist_ok=True)
    tablas = {t: pd.read_sql_query(text(f"SELECT * FROM {t}"), conn) for t in TABLAS_MODELO}
    if tablas["fact_ventas"].empty:
        raise RuntimeError("No hay ventas cargadas en el warehouse: ejecutá primero el ETL.")
    for df in tablas.values():
        if "fecha" in df:
            df["fecha"] = pd.to_datetime(df["fecha"])
    for t, df in tablas.items():
        df.to_csv(carpeta / f"{t}.csv", index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    with pd.ExcelWriter(carpeta / "modelo_ventas.xlsx", engine="openpyxl", date_format="yyyy-mm-dd") as xw:
        for t, df in tablas.items():
            df.to_excel(xw, sheet_name=t, index=False)
            if df.empty:  # una tabla de Excel necesita al menos una fila de datos
                continue
            # Tabla de Excel real: Power BI la detecta con sus encabezados ya promovidos
            tabla = Table(displayName=t, ref=f"A1:{get_column_letter(df.shape[1])}{len(df) + 1}")
            tabla.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            xw.book[t].add_table(tabla)
    if db_path is not None:
        (carpeta / "conectar_sqlite.py").write_text(_script_powerbi(db_path), encoding="utf-8")
    log.info("Modelo para Power BI exportado en %s", carpeta)
    return carpeta


def _script_powerbi(db_path: Path) -> str:
    """Script para 'Obtener datos > Script de Python' en Power BI: lee SQLite en vivo, sin driver ODBC."""
    return f'''# Pegar en Power BI Desktop: Obtener datos > Script de Python.
# Lee el warehouse SQLite directamente (cada "Actualizar" vuelve a consultar la base).
import sqlite3
import pandas as pd

_con = sqlite3.connect(r"{db_path}")
fact_ventas = pd.read_sql_query("SELECT * FROM fact_ventas", _con, parse_dates=["fecha"])
dim_cliente = pd.read_sql_query("SELECT * FROM dim_cliente", _con)
dim_producto = pd.read_sql_query("SELECT * FROM dim_producto", _con)
dim_fecha = pd.read_sql_query("SELECT * FROM dim_fecha", _con, parse_dates=["fecha"])
dim_cotizacion = pd.read_sql_query("SELECT * FROM dim_cotizacion", _con, parse_dates=["fecha"])
etl_runs = pd.read_sql_query("SELECT * FROM etl_runs", _con)
etl_rechazos = pd.read_sql_query("SELECT * FROM etl_rechazos", _con)
_con.close()
'''
