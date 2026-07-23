import os
from urllib.parse import urlparse, unquote, parse_qs
import mysql.connector


def _truthy_env(name):
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _mysql_config_from_env():
    mysql_url = os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL")
    if mysql_url and mysql_url.startswith(("mysql://", "mysql+mysqlconnector://")):
        parsed = urlparse(mysql_url.replace("mysql+mysqlconnector://", "mysql://", 1))
        query = parse_qs(parsed.query)
        config = {
            "host": parsed.hostname,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "database": (parsed.path or "/pulse_medicare").lstrip("/") or "pulse_medicare",
        }
        if parsed.port:
            config["port"] = parsed.port
    else:
        config = {
            "host": os.environ.get("MYSQL_HOST") or os.environ.get("DB_HOST") or "localhost",
            "user": os.environ.get("MYSQL_USER") or os.environ.get("DB_USER") or "root",
            "password": os.environ.get("MYSQL_PASSWORD") or os.environ.get("DB_PASSWORD") or os.environ.get("PASSWORD", "pulse_medicare"),
            "database": os.environ.get("MYSQL_DB") or os.environ.get("MYSQL_DATABASE") or os.environ.get("DB_NAME") or "pulse_medicare",
        }
        if os.environ.get("MYSQL_PORT") or os.environ.get("DB_PORT"):
            config["port"] = int(os.environ.get("MYSQL_PORT") or os.environ.get("DB_PORT"))

    config["connection_timeout"] = int(os.environ.get("MYSQL_CONNECTION_TIMEOUT", "10"))

    ssl_ca = os.environ.get("MYSQL_SSL_CA")
    if ssl_ca:
        config["ssl_ca"] = ssl_ca
    ssl_mode = (os.environ.get("MYSQL_SSL_MODE") or (query.get("ssl-mode", [""])[0] if "query" in locals() else "")).upper()
    if ssl_mode in {"REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"}:
        config["ssl_disabled"] = False
    if _truthy_env("MYSQL_SSL_DISABLED"):
        config["ssl_disabled"] = True

    return config


def _create_db_connection():
    try:
        return mysql.connector.connect(**_mysql_config_from_env())
    except Exception as exc:
        if _truthy_env("MYSQL_REQUIRED"):
            raise RuntimeError("MySQL connection is required but could not be established") from exc
        return None


db = _create_db_connection()
cursor = db.cursor() if db else None
