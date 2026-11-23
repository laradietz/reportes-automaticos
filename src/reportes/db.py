"""Acceso a la base de datos: un único punto de entrada para SQLite (por defecto) y PostgreSQL."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine, make_url


def url_sqlite(ruta: Path) -> str:
    return "sqlite:///" + Path(ruta).as_posix()


def crear_engine(url: str, **opciones) -> Engine:
    """Engine de SQLAlchemy. En SQLite activa las claves foráneas y crea la carpeta si falta.

    Para PostgreSQL, `postgresql://...` usa el driver psycopg2 (SQLAlchemy 2.1 cambió el valor por defecto)."""
    u = make_url(url)
    if u.drivername in ("postgresql", "postgres"):
        u = u.set(drivername="postgresql+psycopg2")
    if u.get_backend_name() == "sqlite" and u.database:
        Path(u.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(u, **opciones)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _claves_foraneas(dbapi_connection, _registro):
            dbapi_connection.execute("PRAGMA foreign_keys = ON")
    return engine


def es_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


def descripcion(engine: Engine) -> str:
    """URL sin contraseña, segura para loguear."""
    return engine.url.render_as_string(hide_password=True)


def ejecutar_script(conn: Connection, sql: str) -> None:
    """Ejecuta un script de DDL sentencia por sentencia (sin interpretar `:` ni `%` como parámetros)."""
    sin_comentarios = "\n".join(linea.split("--")[0] for linea in sql.splitlines())
    for sentencia in (s.strip() for s in sin_comentarios.split(";")):
        if sentencia:
            conn.exec_driver_sql(sentencia)
