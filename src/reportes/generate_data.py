"""Genera datos sintéticos "sucios" que simulan los exports de un sistema de ventas.

Se inyectan errores reales a propósito (duplicados, fechas inválidas, claves
huérfanas, cantidades negativas, mayúsculas inconsistentes...) para demostrar
que la etapa de transformación los detecta y los aísla.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

REGIONES = ["AMBA", "Cuyo", "Litoral", "NOA", "NEA", "Patagonia", "Centro"]
SEGMENTOS = ["Minorista", "Mayorista", "Corporativo"]
VENDEDORES = ["Ana Pérez", "Bruno Gómez", "Carla Díaz", "Diego Ruiz", "Elena Sosa", "Facundo Luna", "Gisela Vera", "Hugo Mena"]
NOMBRES = ["Lucía", "Mateo", "Sofía", "Juan", "Valentina", "Tomás", "Camila", "Nicolás", "Julieta", "Martín", "Paula", "Agustín"]
APELLIDOS = ["García", "Rodríguez", "López", "Martínez", "Fernández", "Álvarez", "Romero", "Torres", "Acosta", "Benítez"]
CATALOGO = {
    "Tecnología": ["Notebook", "Mouse inalámbrico", "Teclado mecánico", "Monitor 24 pulgadas", "Auriculares", "Webcam HD", "Disco SSD 1TB", "Router WiFi"],
    "Hogar": ["Aspiradora", "Licuadora", "Cafetera", "Lámpara LED", "Set de ollas", "Ventilador", "Plancha", "Hervidor"],
    "Oficina": ["Silla ergonómica", "Escritorio", "Resma A4", "Impresora", "Biblioratos", "Calculadora", "Pizarra", "Organizador"],
    "Deportes": ["Pelota de fútbol", "Bicicleta", "Pesas 5kg", "Colchoneta", "Mochila trekking", "Zapatillas", "Bidón", "Raqueta"],
    "Librería": ["Cuaderno A4", "Marcadores x12", "Agenda 2026", "Carpeta", "Mochila escolar", "Lápices x24", "Corrector", "Tijera"],
}
MESES_PESO = np.array([0.8, 0.75, 0.9, 0.95, 1.0, 1.05, 1.1, 1.0, 1.05, 1.2])  # ene..oct 2026
DIAS_MES = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31])


def generar(destino: Path, filas: int = 12000, semilla: int = 42) -> dict:
    rng = np.random.default_rng(semilla)
    destino.mkdir(parents=True, exist_ok=True)

    # --- Productos -----------------------------------------------------
    prods = []
    for cat, nombres in CATALOGO.items():
        for n in nombres:
            prods.append({"id_producto": f"P-{len(prods) + 1:03d}", "nombre": n, "categoria": cat,
                          "precio_lista": round(float(rng.uniform(1500, 250000)), 2)})
    productos = pd.DataFrame(prods)

    # --- Clientes ------------------------------------------------------
    n_cli = 300
    clientes = pd.DataFrame({
        "id_cliente": [f"C-{i + 1:04d}" for i in range(n_cli)],
        "nombre": [f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}" for _ in range(n_cli)],
        "region": rng.choice(REGIONES, n_cli, p=[.32, .08, .14, .1, .06, .1, .2]),
        "segmento": rng.choice(SEGMENTOS, n_cli, p=[.6, .25, .15]),
    })
    clientes["email"] = [f"cliente{i + 1}@ejemplo.com" for i in range(n_cli)]
    # Suciedad: regiones mal escritas, emails en mayúsculas, clientes repetidos
    sucio = rng.choice(n_cli, 25, replace=False)
    clientes.loc[sucio[:10], "region"] = clientes.loc[sucio[:10], "region"].str.lower()
    clientes.loc[sucio[10:18], "region"] = " " + clientes.loc[sucio[10:18], "region"] + " "
    clientes.loc[sucio[18:], "email"] = clientes.loc[sucio[18:], "email"].str.upper()
    clientes = pd.concat([clientes, clientes.sample(6, random_state=semilla)], ignore_index=True)

    # --- Ventas --------------------------------------------------------
    mes = rng.choice(10, filas, p=MESES_PESO / MESES_PESO.sum()) + 1
    dia = (rng.random(filas) * DIAS_MES[mes - 1]).astype(int) + 1
    pop = 1 / np.arange(1, len(productos) + 1) ** 0.7
    idx_prod = rng.choice(len(productos), filas, p=pop / pop.sum())
    cli_idx = rng.integers(0, n_cli, filas)
    seg = clientes["segmento"].iloc[cli_idx].to_numpy()
    cant = np.where(seg == "Mayorista", rng.integers(5, 40, filas),
                    np.where(seg == "Corporativo", rng.integers(2, 15, filas), rng.integers(1, 5, filas)))
    precio = productos["precio_lista"].iloc[idx_prod].to_numpy() * rng.uniform(0.95, 1.05, filas)
    ventas = pd.DataFrame({
        "id_venta": [f"V-{i + 1:06d}" for i in range(filas)],
        "fecha": [f"2026-{m:02d}-{d:02d}" for m, d in zip(mes, dia)],
        "id_cliente": clientes["id_cliente"].iloc[cli_idx].to_numpy(),
        "id_producto": productos["id_producto"].iloc[idx_prod].to_numpy(),
        "vendedor": rng.choice(VENDEDORES, filas),
        "cantidad": cant.astype(str),
        "precio_unitario": np.round(precio, 2).astype(str),
        "descuento": rng.choice(["0", "0", "0", "0.05", "0.10", "0.15"], filas),
    })
    ventas = ventas.sort_values("fecha", kind="stable").reset_index(drop=True)

    # Suciedad inyectada (~5 % de filas en total)
    def pick(k):
        return rng.choice(filas, k, replace=False)

    ventas.loc[pick(40), "fecha"] = "31/02/2026"
    ventas.loc[pick(30), "fecha"] = ""
    ventas.loc[pick(40), "cantidad"] = "-1"
    ventas.loc[pick(25), "cantidad"] = "0"
    ventas.loc[pick(35), "id_cliente"] = "C-9999"        # cliente inexistente
    ventas.loc[pick(30), "id_producto"] = ""             # producto faltante
    ventas.loc[pick(20), "descuento"] = "1.5"            # descuento imposible
    ventas.loc[pick(60), "vendedor"] = ""                # se completa con "Sin asignar"
    ventas.loc[pick(30), "precio_unitario"] = "abc"
    ventas = pd.concat([ventas, ventas.sample(120, random_state=semilla)], ignore_index=True)  # duplicados exactos

    productos.to_csv(destino / "productos.csv", index=False, encoding="utf-8")
    clientes.to_csv(destino / "clientes.csv", index=False, encoding="utf-8")
    ventas.to_csv(destino / "ventas.csv", index=False, encoding="utf-8")
    info = {"productos": len(productos), "clientes": len(clientes), "ventas": len(ventas)}
    log.info("Datos sintéticos generados en %s: %s", destino, info)
    return info


def agregar_novedades(destino: Path, filas: int = 500, semilla: int = 99) -> dict:
    """Agrega ventas válidas posteriores a la última fecha del CSV (simula operación nueva)."""
    rng = np.random.default_rng(semilla)
    ventas = pd.read_csv(destino / "ventas.csv", dtype=str, keep_default_na=False)
    clientes = pd.read_csv(destino / "clientes.csv", dtype=str, keep_default_na=False)["id_cliente"].unique()
    productos = pd.read_csv(destino / "productos.csv", dtype=str, keep_default_na=False)
    fechas = pd.to_datetime(ventas["fecha"], format="%Y-%m-%d", errors="coerce").dropna()
    primero = fechas.max() + pd.Timedelta(days=1)
    ultimo_id = ventas["id_venta"].str.extract(r"(\d+)")[0].astype(int).max()
    precios = productos.set_index("id_producto")["precio_lista"].astype(float)
    ids_prod = rng.choice(productos["id_producto"], filas)
    nuevas = pd.DataFrame({
        "id_venta": [f"V-{ultimo_id + i + 1:06d}" for i in range(filas)],
        "fecha": [(primero + pd.Timedelta(days=int(d))).strftime("%Y-%m-%d") for d in rng.integers(0, 20, filas)],
        "id_cliente": rng.choice(clientes, filas),
        "id_producto": ids_prod,
        "vendedor": rng.choice(VENDEDORES, filas),
        "cantidad": rng.integers(1, 10, filas).astype(str),
        "precio_unitario": np.round(precios.loc[ids_prod].to_numpy() * rng.uniform(0.95, 1.05, filas), 2).astype(str),
        "descuento": rng.choice(["0", "0.05", "0.10"], filas),
    }).sort_values("fecha", kind="stable")
    pd.concat([ventas, nuevas], ignore_index=True).to_csv(destino / "ventas.csv", index=False, encoding="utf-8")
    info = {"ventas_agregadas": filas, "desde": nuevas["fecha"].min(), "hasta": nuevas["fecha"].max()}
    log.info("Novedades agregadas a %s: %s", destino, info)
    return info
