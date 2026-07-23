from flask import Flask, render_template, request, redirect, session, url_for, flash
import mysql.connector
import os
from urllib.parse import urlparse, unquote
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pulsemedicare")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


class _FallbackCursor:
    def __init__(self, dictionary=False, connection=None):
        self.dictionary = dictionary
        self.connection = connection
        self._query = None
        self._params = None
        self._lastrowid = None

    def execute(self, query, params=None):
        self._query = query
        self._params = params
        self._lastrowid = None

        upper_query = (query or "").upper()
        if upper_query.startswith("INSERT INTO BRANCHES") and self.connection is not None:
            branch_name = (params[0] if params and len(params) > 0 else "") or ""
            branch_code = (params[1] if params and len(params) > 1 else "") or ""
            branch_address = (params[2] if params and len(params) > 2 else "") or ""
            contact_person = (params[3] if params and len(params) > 3 else "") or ""
            branch_id = self.connection.add_branch(
                branch_name=branch_name,
                branch_code=branch_code,
                branch_address=branch_address,
                contact_person=contact_person,
            )
            self._lastrowid = branch_id

        return self

    def executemany(self, *args, **kwargs):
        return self

    def fetchone(self):
        if self.dictionary and self._query and "FROM users" in self._query.upper() and self._params:
            if self._params[0] == "admin":
                return {"username": "admin", "password": "admin123", "role": "admin", "full_name": "Default Admin", "profile_photo": ""}

        if self.dictionary and self.connection is not None and self._query and "FROM branches" in self._query.upper():
            query_upper = self._query.upper()
            if "WHERE BRANCH_ID" in query_upper and self._params:
                branch_id = self._params[0]
                for branch in self.connection.branches:
                    if branch["branch_id"] == branch_id:
                        return {
                            "branch_id": branch["branch_id"],
                            "branch_name": branch["branch_name"],
                            "branch_code": branch["branch_code"],
                            "branch_address": branch["branch_address"],
                            "contact_person": branch["contact_person"],
                        }
            if "WHERE BRANCH_NAME" in query_upper and self._params:
                branch_name = self._params[0]
                for branch in self.connection.branches:
                    if branch["branch_name"] == branch_name:
                        return {
                            "branch_id": branch["branch_id"],
                            "branch_name": branch["branch_name"],
                            "branch_code": branch["branch_code"],
                            "branch_address": branch["branch_address"],
                            "contact_person": branch["contact_person"],
                        }

        return None

    def fetchall(self):
        if self.connection is not None and self._query and "FROM branches" in self._query.upper():
            return [
                {
                    "branch_id": branch["branch_id"],
                    "branch_name": branch["branch_name"],
                    "branch_code": branch["branch_code"],
                    "branch_address": branch["branch_address"],
                    "contact_person": branch["contact_person"],
                }
                for branch in self.connection.branches
            ]
        return []

    def close(self):
        return None

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return 0


class _FallbackConnection:
    def __init__(self):
        self.branches = []
        self._next_branch_id = 1

    def add_branch(self, branch_name, branch_code="", branch_address="", contact_person=""):
        branch_id = self._next_branch_id
        self._next_branch_id += 1
        self.branches.append(
            {
                "branch_id": branch_id,
                "branch_name": branch_name,
                "branch_code": branch_code,
                "branch_address": branch_address,
                "contact_person": contact_person,
            }
        )
        return branch_id

    def cursor(self, dictionary=False):
        return _FallbackCursor(dictionary=dictionary, connection=self)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _truthy_env(name):
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _mysql_config_from_env():
    mysql_url = os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL")
    if mysql_url and mysql_url.startswith(("mysql://", "mysql+mysqlconnector://")):
        parsed = urlparse(mysql_url.replace("mysql+mysqlconnector://", "mysql://", 1))
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


# NOTE: Keep app import-safe for unit tests.
# Tests import this module; if a live MySQL server isn't available, import will fail.
if app.testing or os.environ.get("TESTING") == "1":
    db = _FallbackConnection()
else:
    db = _create_db_connection() or _FallbackConnection()


def format_age_string(years, months, days):
    try:
        years = int(years)
    except (TypeError, ValueError):
        years = 0
    try:
        months = int(months)
    except (TypeError, ValueError):
        months = 0
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 0

    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return " ".join(parts) if parts else "0 days"


def parse_age_parts(age):
    years = months = days = 0
    if age:
        import re
        year_match = re.search(r"(\d+)\s*year", age)
        month_match = re.search(r"(\d+)\s*month", age)
        day_match = re.search(r"(\d+)\s*day", age)
        if year_match:
            years = int(year_match.group(1))
        if month_match:
            months = int(month_match.group(1))
        if day_match:
            days = int(day_match.group(1))
    return years, months, days


def normalize_age_parts(years, months, days):
    try:
        years = int(years)
    except (TypeError, ValueError):
        years = 0
    try:
        months = int(months)
    except (TypeError, ValueError):
        months = 0
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 0
    return years, months, days


def format_age_display(years, months, days):
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return " ".join(parts) if parts else "0 days"


def ensure_patient_age_columns():
    cursor = db.cursor()
    cursor.execute("SHOW COLUMNS FROM patients LIKE 'age_years'")
    if not cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN age_years INT DEFAULT 0, ADD COLUMN age_months INT DEFAULT 0, ADD COLUMN age_days INT DEFAULT 0")
            db.commit()
        except Exception:
            pass


def ensure_patient_guardian_columns():
    cursor = db.cursor()
    cursor.execute("SHOW COLUMNS FROM patients")
    existing_columns = {row[0] for row in cursor.fetchall()}
    for column_name, definition in {
        "guardian_name": "VARCHAR(100) DEFAULT ''",
        "guardian_phone": "VARCHAR(30) DEFAULT ''",
        "guardian_relation": "VARCHAR(50) DEFAULT ''"
    }.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {column_name} {definition}")
            except Exception:
                pass
    db.commit()


def ensure_deletion_log_table():
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient_deletion_log (
            log_id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            branch_id INT NULL,
            full_name VARCHAR(100),
            deleted_by VARCHAR(50),
            reason TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()


def ensure_branches_table():
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS branches (
            branch_id INT AUTO_INCREMENT PRIMARY KEY,
            branch_name VARCHAR(100) NOT NULL UNIQUE,
            branch_code VARCHAR(50) DEFAULT '',
            branch_address VARCHAR(255) DEFAULT '',
            contact_person VARCHAR(100) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()


def get_default_branch_id():
    ensure_branches_table()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT branch_id FROM branches WHERE branch_name=%s LIMIT 1", ("Main Branch",))
    branch = cursor.fetchone()
    if branch:
        return branch["branch_id"]

    cursor.execute("SELECT branch_id FROM branches ORDER BY branch_id ASC LIMIT 1")
    branch = cursor.fetchone()
    if branch:
        return branch["branch_id"]

    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO branches (branch_name, branch_code) VALUES (%s, %s)",
        ("Main Branch", "MAIN")
    )
    db.commit()
    return cursor.lastrowid


def ensure_branch_columns():
    default_branch_id = get_default_branch_id()
    cursor = db.cursor()
    for table_name in ("patients", "doctors", "appointments", "billing", "laboratory", "patient_deletion_log"):
        try:
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            if not cursor.fetchone():
                continue

            cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'branch_id'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN branch_id INT NULL")

            cursor.execute(
                f"UPDATE {table_name} SET branch_id=%s WHERE branch_id IS NULL",
                (default_branch_id,)
            )
            try:
                cursor.execute(f"CREATE INDEX idx_{table_name}_branch_id ON {table_name} (branch_id)")
            except Exception:
                pass
        except Exception:
            db.rollback()
        else:
            db.commit()


def set_session_branch(branch):
    if not branch:
        session.pop("branch_id", None)
        session.pop("branch", None)
        return

    session["branch_id"] = branch.get("branch_id")
    session["branch"] = branch.get("branch_name")


def get_current_branch_id():
    ensure_branches_table()
    cursor = db.cursor(dictionary=True)

    branch_id = session.get("branch_id")
    if branch_id:
        cursor.execute(
            "SELECT branch_id, branch_name FROM branches WHERE branch_id=%s",
            (branch_id,)
        )
        branch = cursor.fetchone()
        if branch:
            set_session_branch(branch)
            return branch["branch_id"]

    branch_name = session.get("branch")
    if branch_name:
        cursor.execute(
            "SELECT branch_id, branch_name FROM branches WHERE branch_name=%s",
            (branch_name,)
        )
        branch = cursor.fetchone()
        if branch:
            set_session_branch(branch)
            return branch["branch_id"]

    return None


def require_branch_id():
    return get_current_branch_id()


def branch_record_exists(table_name, id_column, record_id, branch_id):
    allowed_tables = {
        "patients": "patient_id",
        "doctors": "doctor_id",
        "laboratory": "lab_id",
        "billing": "bill_id",
    }
    if allowed_tables.get(table_name) != id_column:
        return False

    cursor = db.cursor()
    cursor.execute(
        f"SELECT 1 FROM {table_name} WHERE {id_column}=%s AND branch_id=%s LIMIT 1",
        (record_id, branch_id)
    )
    return cursor.fetchone() is not None


def ensure_roles_table():
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            role_id INT AUTO_INCREMENT PRIMARY KEY,
            role_name VARCHAR(50) NOT NULL UNIQUE,
            role_description VARCHAR(255) DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()

    cursor.execute("SELECT role_name FROM roles")
    existing_roles = {row[0] for row in cursor.fetchall()}
    defaults = [
        ("user", "Standard system user"),
        ("lab", "Laboratory user"),
        ("doctor", "Doctor account"),
        ("admin", "Administrator"),
        ("administrator", "Administrator"),
        ("system_admin", "System administrator")
    ]
    for role_name, description in defaults:
        if role_name not in existing_roles:
            cursor.execute(
                "INSERT INTO roles (role_name, role_description) VALUES (%s, %s)",
                (role_name, description)
            )
    db.commit()


def get_user_columns():
    cursor = db.cursor()
    cursor.execute("SHOW COLUMNS FROM users")
    return {row[0] for row in cursor.fetchall()}


def normalize_role_name(role):
    raw_value = (role or "").strip()
    if not raw_value:
        return "user"

    normalized = raw_value.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "administrator": "admin",
        "system_admin": "system_admin",
        "systemadmin": "system_admin",
        "lab_technician": "lab_technician",
        "labtechnician": "lab_technician",
        "lab": "lab",
        "doctor": "doctor",
        "receptionist": "receptionist",
        "pharmacist": "pharmacist",
        "user": "user",
        "admin": "admin",
    }
    return aliases.get(normalized, normalized or "user")


def normalize_role_slug(role):
    raw_value = (role or "").strip()
    if not raw_value:
        return "user"

    import re
    normalized = re.sub(r"[^a-z0-9]+", "_", raw_value.lower()).strip("_")
    return normalized or "user"


def get_roles_data(cursor=None):
    if cursor is None:
        cursor = db.cursor(dictionary=True)
    cursor.execute('SELECT role_name, role_description FROM roles ORDER BY role_name')
    return cursor.fetchall()


def ensure_users_table():
    cursor = db.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (\n        user_id INT AUTO_INCREMENT PRIMARY KEY,\n        username VARCHAR(100) NOT NULL UNIQUE,\n        password VARCHAR(255) NOT NULL,\n        role VARCHAR(50) NOT NULL DEFAULT 'user',\n        full_name VARCHAR(100) DEFAULT '',\n        email VARCHAR(100) DEFAULT '',\n        phone VARCHAR(30) DEFAULT '',\n        profile_photo VARCHAR(255) DEFAULT '',\n        bio TEXT NULL,\n        active TINYINT(1) DEFAULT 1,\n        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP\n    )")
    db.commit()

    try:
        cursor.execute("ALTER TABLE users MODIFY COLUMN role VARCHAR(50) NOT NULL DEFAULT 'user'")
        db.commit()
    except Exception:
        db.rollback()


def ensure_user_profile_columns():
    cursor = db.cursor()
    existing_columns = get_user_columns()
    columns = {
        "full_name": "VARCHAR(100) DEFAULT ''",
        "email": "VARCHAR(100) DEFAULT ''",
        "phone": "VARCHAR(30) DEFAULT ''",
        "profile_photo": "VARCHAR(255) DEFAULT ''",
        "bio": "TEXT NULL"
    }
    for column_name, definition in columns.items():
        if column_name not in existing_columns:
            try:
                if column_name == "bio":
                    cursor.execute("ALTER TABLE users ADD COLUMN bio TEXT NULL")
                else:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {definition}")
            except Exception:
                pass
    db.commit()


def ensure_user_active_column():
    cursor = db.cursor()
    cursor.execute("SHOW COLUMNS FROM users LIKE 'active'")
    if not cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN active TINYINT(1) DEFAULT 1")
            db.commit()
        except Exception:
            pass


def normalize_icon_name(icon_name):
    icon_name = (icon_name or "").strip()
    if not icon_name:
        return "fa-circle"
    if icon_name.startswith("fa "):
        icon_name = icon_name.replace("fa ", "", 1).strip()
    if icon_name.startswith("fa-solid "):
        icon_name = icon_name.replace("fa-solid ", "", 1).strip()
    if not icon_name.startswith("fa-"):
        icon_name = f"fa-{icon_name}"
    return icon_name


def get_active_sidebar_menu_data():
    if db is None:
        return [], []

    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT root_menu_id, name, icon_name, url, status, display_order FROM root_menus WHERE status=%s ORDER BY display_order ASC, name ASC",
        ("Active",)
    )
    root_items = cursor.fetchall() or []

    cursor.execute(
        "SELECT sub_menu_id, root_menu_id, name, icon_name, url, status, display_order FROM sub_menus WHERE status=%s ORDER BY display_order ASC, name ASC",
        ("Active",)
    )
    sub_items = cursor.fetchall() or []
    return root_items, sub_items


def build_sidebar_menu_items(root_items=None, sub_items=None):
    if root_items is None or sub_items is None:
        root_items, sub_items = get_active_sidebar_menu_data()

    children_by_root = {}
    for item in sub_items or []:
        if str(item.get("status", "Active")).lower() != "active":
            continue
        children_by_root.setdefault(item.get("root_menu_id"), []).append(item)

    menu_items = []
    reserved_root_names = {"Settings"}
    for item in root_items or []:
        if str(item.get("status", "Active")).lower() != "active":
            continue
        if (item.get("name") or "").strip() in reserved_root_names:
            continue

        children = []
        for child in children_by_root.get(item.get("root_menu_id"), []):
            children.append({
                "sub_menu_id": child.get("sub_menu_id"),
                "name": child.get("name") or "Untitled",
                "icon_name": child.get("icon_name") or "fa-circle",
                "url": child.get("url") or "#",
                "status": child.get("status") or "Active",
                "display_order": child.get("display_order") or 0,
            })

        if (item.get("name") or "").strip() == "Laboratory":
            defaults = [
                {
                    "sub_menu_id": None,
                    "name": "Rate Category",
                    "icon_name": "fa-tags",
                    "url": "/lims_settings/rate_category",
                    "status": "Active",
                    "display_order": 10,
                },
                {
                    "sub_menu_id": None,
                    "name": "Instrument",
                    "icon_name": "fa-microscope",
                    "url": "/lims_settings/instrument",
                    "status": "Active",
                    "display_order": 20,
                },
                {
                    "sub_menu_id": None,
                    "name": "Lab Group",
                    "icon_name": "fa-layer-group",
                    "url": "/lims_settings/lab_group",
                    "status": "Active",
                    "display_order": 30,
                },
                {
                    "sub_menu_id": None,
                    "name": "Test",
                    "icon_name": "fa-vial-circle-check",
                    "url": "/lims_settings/test",
                    "status": "Active",
                    "display_order": 40,
                },
                {
                    "sub_menu_id": None,
                    "name": "Method",
                    "icon_name": "fa-list-check",
                    "url": "/lims_settings/method",
                    "status": "Active",
                    "display_order": 50,
                },
                {
                    "sub_menu_id": None,
                    "name": "Sample Vial",
                    "icon_name": "fa-vial",
                    "url": "/lims_settings/sample_vial",
                    "status": "Active",
                    "display_order": 60,
                },
                {
                    "sub_menu_id": None,
                    "name": "Units",
                    "icon_name": "fa-ruler",
                    "url": "/lims_settings/units",
                    "status": "Active",
                    "display_order": 70,
                },
                {
                    "sub_menu_id": None,
                    "name": "Kits",
                    "icon_name": "fa-box-open",
                    "url": "/lims_settings/kits",
                    "status": "Active",
                    "display_order": 80,
                },
                {
                    "sub_menu_id": None,
                    "name": "Parameter",
                    "icon_name": "fa-sliders",
                    "url": "/lims_settings/parameter",
                    "status": "Active",
                    "display_order": 90,
                },
                {
                    "sub_menu_id": None,
                    "name": "Report Comment Master",
                    "icon_name": "fa-comment-medical",
                    "url": "/lims_settings/report_comment_master",
                    "status": "Active",
                    "display_order": 100,
                },
            ]
            existing_urls = {child.get("url") for child in children if child.get("url")}
            for default in defaults:
                if default.get("url") not in existing_urls:
                    children.append(default)

        children = sorted(
            children,
            key=lambda child: (child.get("display_order") or 0, (child.get("name") or "").lower())
        )

        menu_items.append({
            "root_menu_id": item.get("root_menu_id"),
            "name": item.get("name") or "Untitled",
            "icon_name": item.get("icon_name") or "fa-circle",
            "url": item.get("url") or "#",
            "status": item.get("status") or "Active",
            "display_order": item.get("display_order") or 0,
            "children": children,
        })

    return menu_items


def ensure_root_menus_table():
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS root_menus (
            root_menu_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            icon_name VARCHAR(100) NOT NULL DEFAULT 'fa-circle',
            url VARCHAR(255) NOT NULL DEFAULT '#',
            status VARCHAR(20) NOT NULL DEFAULT 'Active',
            display_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    db.commit()

    cursor.execute("SHOW COLUMNS FROM root_menus")
    existing_columns = {row[0] for row in cursor.fetchall()}
    columns = {
        "icon_name": "VARCHAR(100) NOT NULL DEFAULT 'fa-circle'",
        "url": "VARCHAR(255) NOT NULL DEFAULT '#'",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'Active'",
        "display_order": "INT NOT NULL DEFAULT 0"
    }
    for column_name, definition in columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE root_menus ADD COLUMN {column_name} {definition}")
            except Exception:
                pass
    db.commit()

    cursor.execute("SELECT COUNT(*) FROM root_menus")
    result = cursor.fetchone()
    if not result or result[0] == 0:
        defaults = [
            ("Dashboard", "fa-house", "/dashboard", "Active", 10),
            ("Patients", "fa-user", "/patients", "Active", 20),
            ("Doctors", "fa-user-doctor", "/doctors", "Active", 30),
            ("Appointments", "fa-calendar-check", "/appointments", "Active", 40),
            ("Billing", "fa-file-invoice", "/billing", "Active", 50),
            ("Laboratory", "fa-flask", "/laboratory/dashboard", "Active", 60),
            ("Settings", "fa-gear", "/settings", "Active", 70),
        ]
        cursor.executemany(
            "INSERT INTO root_menus (name, icon_name, url, status, display_order) VALUES (%s, %s, %s, %s, %s)",
            defaults
        )
        db.commit()


def ensure_sub_menus_table():
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sub_menus (
            sub_menu_id INT AUTO_INCREMENT PRIMARY KEY,
            root_menu_id INT NULL,
            name VARCHAR(100) NOT NULL,
            icon_name VARCHAR(100) NOT NULL DEFAULT 'fa-circle',
            url VARCHAR(255) NOT NULL DEFAULT '#',
            status VARCHAR(20) NOT NULL DEFAULT 'Active',
            display_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    db.commit()

    cursor.execute("SHOW COLUMNS FROM sub_menus")
    existing_columns = {row[0] for row in cursor.fetchall()}
    columns = {
        "root_menu_id": "INT NULL",
        "icon_name": "VARCHAR(100) NOT NULL DEFAULT 'fa-circle'",
        "url": "VARCHAR(255) NOT NULL DEFAULT '#'",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'Active'",
        "display_order": "INT NOT NULL DEFAULT 0"
    }
    for column_name, definition in columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE sub_menus ADD COLUMN {column_name} {definition}")
            except Exception:
                pass
    db.commit()

    cursor.execute("SELECT COUNT(*) FROM sub_menus")
    result = cursor.fetchone()
    if result and result[0] > 0:
        return

    cursor.execute("SELECT root_menu_id, name FROM root_menus")
    root_ids = {row[1]: row[0] for row in cursor.fetchall()}
    defaults = [
        (root_ids.get("Settings"), "System", "fa-sliders", "/settings", "Active", 10),
        (root_ids.get("Settings"), "Root Menu", "fa-sitemap", "/settings/root_menu", "Active", 20),
        (root_ids.get("Settings"), "Sub Menu", "fa-list", "/settings/sub_menu", "Active", 30),
        (root_ids.get("Laboratory"), "LIMS Setting", "fa-vial", "/lims_settings", "Active", 40),
        (root_ids.get("Settings"), "Profile", "fa-id-card", "/profile", "Active", 50),
    ]
    cursor.executemany(
        "INSERT INTO sub_menus (root_menu_id, name, icon_name, url, status, display_order) VALUES (%s, %s, %s, %s, %s, %s)",
        defaults
    )
    db.commit()


def ensure_lims_settings_table():
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lims_settings_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            section_slug VARCHAR(100) NOT NULL,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(100) DEFAULT '',
            status VARCHAR(50) DEFAULT 'Active',
            display_order INT DEFAULT 0,
            description TEXT NULL,
            rate DECIMAL(10,2) NULL DEFAULT NULL,
            branch_id INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    # Ensure 'rate' column exists for older installations
    try:
        cursor.execute("SHOW COLUMNS FROM lims_settings_items LIKE 'rate'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE lims_settings_items ADD COLUMN rate DECIMAL(10,2) NULL DEFAULT NULL")
            db.commit()
    except Exception:
        db.rollback()


def get_user_profile(username):
    existing_columns = get_user_columns()
    select_fields = [field for field in ["username", "role", "password", "full_name", "email", "phone", "profile_photo", "bio"] if field in existing_columns]
    if not select_fields:
        select_fields = ["username"]

    cursor = db.cursor(dictionary=True)
    cursor.execute(
        f"SELECT {', '.join(select_fields)} FROM users WHERE username=%s",
        (username,)
    )
    user = cursor.fetchone()
    if user:
        for field in ["username", "role", "password", "full_name", "email", "phone", "profile_photo", "bio"]:
            user.setdefault(field, "")
        return user
    return {
        "username": username,
        "role": "",
        "password": "",
        "full_name": "",
        "email": "",
        "phone": "",
        "profile_photo": "",
        "bio": ""
    }


def inject_user_role():
    return dict(user_role=session.get("role"))


@app.context_processor
def inject_user_role_context():
    return {
        **inject_user_role(),
        "sidebar_menu_items": build_sidebar_menu_items(),
    }


@app.route("/healthz")
def healthz():
    return {"ok": True, "database": db.__class__.__name__ != "_FallbackConnection"}


if db is not None:
    ensure_patient_age_columns()
    ensure_patient_guardian_columns()
    ensure_branches_table()
    ensure_deletion_log_table()
    ensure_branch_columns()
    ensure_roles_table()
    ensure_users_table()
    ensure_user_profile_columns()
    ensure_user_active_column()
    ensure_root_menus_table()
    ensure_sub_menus_table()
    ensure_lims_settings_table()



def seed_admin_user():
    if getattr(db, "__class__", None).__name__ == "_FallbackConnection":
        return

    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role IN ('admin','administrator','system_admin')")
    result = cursor.fetchone()
    if not result or result[0] == 0:
        try:
            cursor.execute(
                "INSERT INTO users (username, password, role, full_name, email, phone, active) VALUES (%s, %s, %s, %s, %s, %s, 1)",
                ('admin', 'admin123', 'admin', 'Default Admin', 'admin@example.com', '')
            )
            db.commit()
        except Exception:
            db.rollback()

def seed_demo_role_and_user():
    cursor = db.cursor()
    try:
        cursor.execute('SELECT COUNT(*) AS count FROM roles WHERE role_name=%s', ('manager',))
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'INSERT INTO roles (role_name, role_description) VALUES (%s, %s)',
                ('manager', 'Manager account with standard access')
            )

        cursor.execute('SELECT COUNT(*) AS count FROM users WHERE username=%s', ('manager1',))
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'INSERT INTO users (username, password, role, full_name, email, phone, active) VALUES (%s, %s, %s, %s, %s, %s, 1)',
                ('manager1', 'manager123', 'manager', 'Manager User', 'manager@example.com', '')
            )
        db.commit()
    except Exception:
        db.rollback()

if db is not None:
    seed_admin_user()
    seed_demo_role_and_user()


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if db.__class__.__name__ == "_FallbackConnection":
            if username == "admin" and (password or "").strip() == "admin123":
                session["username"] = "admin"
                session["role"] = "admin"
                session["full_name"] = "Default Admin"
                session["profile_photo"] = ""
                if not session.get("branch_id"):
                    return redirect("/select_branch")
                return redirect("/dashboard")
            error_message = "Invalid Username or Password"
            flash(error_message, "error")
            return render_template("login.html", error=error_message)

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE username=%s",
            (username,)
        )
        user = cursor.fetchone()

        stored_password = user.get("password", "") if user else ""
        normalized_input_password = (password or "").strip()
        normalized_stored_password = (stored_password or "").strip()
        password_matches = False

        if user:
            if normalized_input_password and normalized_stored_password:
                password_matches = normalized_input_password == normalized_stored_password
            elif not normalized_input_password and not normalized_stored_password:
                password_matches = True

        if user and password_matches:
            session["username"] = user["username"]
            session["role"] = normalize_role_name(user.get("role", ""))
            session["full_name"] = user.get("full_name") or user["username"]
            session["profile_photo"] = user.get("profile_photo") or ""
            if not session.get("branch_id"):
                return redirect("/select_branch")
            return redirect("/dashboard")

        error_message = "Invalid Username or Password"
        flash(error_message, "error")
        return render_template("login.html", error=error_message)

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    role = normalize_role_name(session.get("role", ""))
    is_admin = role in {"admin", "administrator", "system_admin"}
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")

    cursor.execute("SELECT COUNT(*) AS count FROM patients WHERE branch_id=%s", (branch_id,))
    total_patients = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM doctors WHERE branch_id=%s", (branch_id,))
    total_doctors = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE branch_id=%s", (branch_id,))
    total_appointments = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE branch_id=%s AND DATE(appointment_date) = CURDATE()", (branch_id,))
    today_bookings = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE branch_id=%s AND DATE(appointment_date) = CURDATE() AND status = 'Confirmed'", (branch_id,))
    today_confirmed_bookings = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE branch_id=%s AND DATE(appointment_date) = CURDATE() AND status IN ('Cancelled', 'Canceled')", (branch_id,))
    today_cancelled_bookings = cursor.fetchone()["count"]

    revenue = 0
    try:
        cursor.execute("SELECT IFNULL(SUM(total_amount), 0) AS total FROM billing WHERE branch_id=%s AND DATE(bill_date) = CURDATE() AND payment_status = 'Paid'", (branch_id,))
        revenue = cursor.fetchone()["total"]
    except Exception:
        revenue = 0

    cursor.execute("""
SELECT p.full_name AS patient_name,
       d.doctor_name,
       a.appointment_date,
       a.status
FROM appointments a
LEFT JOIN patients p ON a.patient_id = p.patient_id AND p.branch_id = a.branch_id
LEFT JOIN doctors d ON a.doctor_id = d.doctor_id AND d.branch_id = a.branch_id
WHERE a.branch_id = %s
ORDER BY a.appointment_date DESC
LIMIT 10
""", (branch_id,))

    appointments = cursor.fetchall()

    cursor.execute("""
SELECT p.full_name AS patient_name,
       b.total_amount AS amount_due,
       b.bill_date AS due_date,
       b.payment_status AS status
FROM billing b
LEFT JOIN patients p ON b.patient_id = p.patient_id AND p.branch_id = b.branch_id
WHERE b.branch_id = %s AND b.payment_status IN ('Pending', 'Due', 'Partial')
ORDER BY b.bill_date DESC, b.total_amount DESC
LIMIT 10
""", (branch_id,))
    payment_dues = cursor.fetchall()

    cursor.execute("""
SELECT p.full_name AS patient_name,
       b.total_amount AS collection_amount,
       b.bill_date AS collected_on,
       b.payment_status AS status
FROM billing b
LEFT JOIN patients p ON b.patient_id = p.patient_id AND p.branch_id = b.branch_id
WHERE b.branch_id = %s AND b.payment_status = 'Paid'
ORDER BY b.bill_date DESC, b.total_amount DESC
LIMIT 10
""", (branch_id,))
    collections = cursor.fetchall()

    deleted_patients = []
    deleted_count = 0
    if is_admin:
        cursor.execute(
            "SELECT patient_id, full_name, deleted_by, reason, deleted_at FROM patient_deletion_log WHERE branch_id=%s ORDER BY deleted_at DESC LIMIT 5",
            (branch_id,)
        )
        deleted_patients = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) AS count FROM patient_deletion_log WHERE branch_id=%s", (branch_id,))
        deleted_count = cursor.fetchone()["count"]

    profile = get_user_profile(session["username"])
    display_name = (profile.get("full_name") or session.get("full_name") or session["username"]).strip()
    profile_photo = profile.get("profile_photo") or session.get("profile_photo") or ""
    session["full_name"] = display_name
    session["profile_photo"] = profile_photo

    return render_template(
        "dashboard.html",
        username=session["username"],
        display_name=display_name,
        profile_photo=profile_photo,
        role=role,
        is_admin=is_admin,
        total_patients=total_patients,
        total_doctors=total_doctors,
        total_appointments=total_appointments,
        today_bookings=today_bookings,
        today_confirmed_bookings=today_confirmed_bookings,
        today_cancelled_bookings=today_cancelled_bookings,
        revenue=revenue,
        appointments=appointments,
        payment_dues=payment_dues,
        collections=collections,
        deleted_patients=deleted_patients,
        deleted_count=deleted_count
    )


@app.route('/select_branch', methods=['GET', 'POST'])
def select_branch():
    if "username" not in session:
        return redirect('/login')

    role = normalize_role_name(session.get('role', ''))
    can_manage_branches = role in {"admin", "administrator", "system_admin"}

    ensure_branches_table()

    cursor = db.cursor(dictionary=True)
    cursor.execute('SELECT branch_id, branch_name, branch_code, branch_address, contact_person FROM branches ORDER BY branch_name')
    branches = cursor.fetchall()

    if request.method == 'POST':
        action = request.form.get('action', 'select').strip()

        if action == 'create':
            if not can_manage_branches:
                flash("Only administrators can create branches.", "error")
                return redirect('/select_branch')

            branch_name = request.form.get('branch_name', '').strip()
            branch_code = request.form.get('branch_code', '').strip()
            branch_address = request.form.get('branch_address', '').strip()
            contact_person = request.form.get('contact_person', '').strip()
            if branch_name:
                try:
                    cursor = db.cursor()
                    cursor.execute(
                        'INSERT INTO branches (branch_name, branch_code, branch_address, contact_person) VALUES (%s, %s, %s, %s)',
                        (branch_name, branch_code, branch_address, contact_person)
                    )
                    db.commit()
                    set_session_branch({
                        "branch_id": cursor.lastrowid,
                        "branch_name": branch_name,
                    })
                    flash(f'Branch "{branch_name}" created successfully.', 'success')
                except Exception:
                    db.rollback()
                    flash('Could not create branch. The branch name may already exist.', 'error')
            else:
                flash('Branch name is required.', 'error')

            return redirect('/select_branch')
        else:
            branch_id = request.form.get('branch_id')
            selected_branch = None
            for b in branches:
                if str(b.get('branch_id')) == str(branch_id) or str(b.get('branch_name')) == str(branch_id):
                    selected_branch = b
                    break
            if not selected_branch and branches:
                selected_branch = branches[0]
            set_session_branch(selected_branch)
            if selected_branch:
                flash(f'Connected to branch: {selected_branch.get("branch_name")}', 'success')

        return redirect('/dashboard')

    if not branches:
        session.pop('branch_id', None)
        session.pop('branch', None)

    return render_template('select_branch.html', branches=branches, username=session['username'], role=role, can_manage_branches=can_manage_branches)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    user = get_user_profile(username)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip() or username
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        bio = request.form.get("bio", "").strip()

        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        password_fields_entered = any([current_password, new_password, confirm_password])
        if password_fields_entered:
            if not current_password or not new_password or not confirm_password:
                flash("Please fill in all password fields.", "error")
                return redirect("/profile")
            if new_password != confirm_password:
                flash("New password and confirm password do not match.", "error")
                return redirect("/profile")

            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT password FROM users WHERE username=%s", (username,))
            password_row = cursor.fetchone()
            if not password_row or password_row.get("password") != current_password:
                flash("Current password is incorrect.", "error")
                return redirect("/profile")

            cursor = db.cursor()
            cursor.execute("UPDATE users SET password=%s WHERE username=%s", (new_password, username))
            db.commit()
            flash("Password updated successfully.", "success")

        profile_photo = user.get("profile_photo", "") if user else ""
        uploaded_file = request.files.get("profile_photo")
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(f"{username}_{uploaded_file.filename}")
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            uploaded_file.save(save_path)
            profile_photo = f"static/uploads/{filename}"

        existing_columns = get_user_columns()
        updates = []
        values = []
        for field_name, value in [
            ("full_name", full_name),
            ("email", email),
            ("phone", phone),
            ("bio", bio),
            ("profile_photo", profile_photo),
        ]:
            if field_name in existing_columns:
                updates.append(f"{field_name}=%s")
                values.append(value)

        if updates:
            cursor = db.cursor()
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE username=%s",
                tuple(values + [username])
            )
            db.commit()

        session["full_name"] = full_name
        session["profile_photo"] = profile_photo
        user = get_user_profile(username)
        if not password_fields_entered:
            flash("Profile updated successfully.", "success")
        return redirect("/dashboard")

    return render_template(
        "profile.html",
        username=username,
        user=user,
        role=session.get("role", "")
    )


@app.route("/patients")
def patients():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    query = request.args.get("q", "").strip()
    patients = []
    error = None
    try:
        if query:
            like = f"%{query}%"
            cursor.execute("""
SELECT patient_id,
full_name,
age,
age_years,
age_months,
age_days,
gender,
phone,
blood_group,
disease,
admission_date
FROM patients
WHERE branch_id = %s
  AND (
      full_name LIKE %s
      OR gender LIKE %s
      OR phone LIKE %s
      OR blood_group LIKE %s
      OR disease LIKE %s
  )
ORDER BY admission_date DESC
LIMIT 100
""", (branch_id, like, like, like, like, like))
        else:
            cursor.execute("""
SELECT patient_id,
full_name,
age,
age_years,
age_months,
age_days,
gender,
phone,
blood_group,
disease,
admission_date
FROM patients
WHERE branch_id = %s
ORDER BY admission_date DESC
LIMIT 100
""", (branch_id,))

        patients = cursor.fetchall()
    except Exception as e:
        # Fail gracefully and show an error message in the template
        error = "Unable to load patients. Check database connection."

    return render_template(
        "patients.html",
        username=session["username"],
        patients=patients,
        query=query,
        error=error
    )

@app.route("/doctor")
@app.route("/doctors")
def doctors():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute("""
SELECT doctor_id,
doctor_name,
department,
phone,
email,
qualification
FROM doctors
WHERE branch_id = %s
ORDER BY doctor_name ASC
""", (branch_id,))
    doctors = cursor.fetchall()

    return render_template(
        "doctors.html",
        username=session["username"],
        doctors=doctors
    )

@app.route("/add_doctor", methods=["GET", "POST"])
def add_doctor():

    if "username" not in session:
        return redirect("/login")

    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")

    if request.method == "POST":
        doctor_name = request.form["doctor_name"].strip().title()
        department = request.form.get("department", "").strip().title()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        qualification = request.form.get("qualification", "").strip().title()

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO doctors (branch_id, doctor_name, department, phone, email, qualification) VALUES (%s, %s, %s, %s, %s, %s)",
            (branch_id, doctor_name, department, phone, email, qualification)
        )
        db.commit()
        return redirect("/doctors")

    return render_template(
        "doctor_form.html",
        action="Add Doctor",
        form_action="/add_doctor",
        doctor={}
    )

@app.route("/edit_doctor/<int:doctor_id>", methods=["GET", "POST"])
def edit_doctor(doctor_id):

    if "username" not in session:
        return redirect("/login")

    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")

    cursor = db.cursor(dictionary=True)
    if request.method == "POST":
        doctor_name = request.form["doctor_name"].strip().title()
        department = request.form.get("department", "").strip().title()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        qualification = request.form.get("qualification", "").strip().title()

        cursor.execute(
            "UPDATE doctors SET doctor_name=%s, department=%s, phone=%s, email=%s, qualification=%s WHERE doctor_id=%s AND branch_id=%s",
            (doctor_name, department, phone, email, qualification, doctor_id, branch_id)
        )
        db.commit()
        flash("Doctor updated successfully", "success")
        return redirect("/doctors")

    cursor.execute(
        "SELECT doctor_id, doctor_name, department, phone, email, qualification FROM doctors WHERE doctor_id=%s AND branch_id=%s",
        (doctor_id, branch_id)
    )
    doctor = cursor.fetchone()
    if not doctor:
        flash("Doctor not found", "error")
        return redirect("/doctors")

    return render_template(
        "doctor_form.html",
        action="Edit Doctor",
        form_action=url_for("edit_doctor", doctor_id=doctor_id),
        doctor=doctor
    )

@app.route("/appointments")
def appointments():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    search_query = request.args.get("q", "").strip()
    params = [branch_id]
    sql = """
SELECT a.appointment_id,
       p.full_name AS patient_name,
       d.doctor_name,
       a.appointment_date,
       a.appointment_time,
       a.status
FROM appointments a
LEFT JOIN patients p ON a.patient_id = p.patient_id AND p.branch_id = a.branch_id
LEFT JOIN doctors d ON a.doctor_id = d.doctor_id AND d.branch_id = a.branch_id
WHERE a.branch_id = %s
"""
    if search_query:
        like_query = f"%{search_query}%"
        sql += " AND (CAST(a.appointment_id AS CHAR) LIKE %s OR p.full_name LIKE %s OR d.doctor_name LIKE %s OR a.appointment_date LIKE %s OR a.status LIKE %s)"
        params.extend([like_query, like_query, like_query, like_query, like_query])
    sql += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"
    cursor.execute(sql, tuple(params))
    appointments = cursor.fetchall()

    return render_template(
        "appointments.html",
        username=session["username"],
        appointments=appointments,
        query=search_query
    )

@app.route("/add_appointment", methods=["GET", "POST"])
def add_appointment():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute("SELECT patient_id, full_name FROM patients WHERE branch_id=%s ORDER BY full_name ASC", (branch_id,))
    patients = cursor.fetchall()
    cursor.execute("SELECT doctor_id, doctor_name FROM doctors WHERE branch_id=%s ORDER BY doctor_name ASC", (branch_id,))
    doctors = cursor.fetchall()

    if request.method == "POST":
        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        appointment_date = request.form["appointment_date"]
        appointment_time = request.form["appointment_time"]
        status = request.form.get("status", "Pending")

        if not branch_record_exists("patients", "patient_id", patient_id, branch_id) or not branch_record_exists("doctors", "doctor_id", doctor_id, branch_id):
            flash("Please select a patient and doctor from the current branch.", "error")
            return redirect("/add_appointment")

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO appointments (branch_id, patient_id, doctor_id, appointment_date, appointment_time, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (branch_id, patient_id, doctor_id, appointment_date, appointment_time, status)
        )
        db.commit()
        return redirect("/appointments")

    return render_template(
        "appointment_form.html",
        action="Add Appointment",
        form_action="/add_appointment",
        patients=patients,
        doctors=doctors,
        appointment={}
    )

@app.route("/billing")
def billing():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    search_query = request.args.get("q", "").strip()
    params = [branch_id]
    sql = """
SELECT bill_id,
       patient_id,
       patient_name,
       doctor_name,
       bill_date,
       consultation_fee,
       medicine_fee,
       lab_fee,
       room_fee,
       other_charges,
       total_amount,
       payment_method,
       payment_status
FROM billing
WHERE branch_id = %s
"""
    if search_query:
        like_query = f"%{search_query}%"
        sql += " AND (CAST(bill_id AS CHAR) LIKE %s OR patient_name LIKE %s OR doctor_name LIKE %s OR payment_method LIKE %s OR payment_status LIKE %s)"
        params.extend([like_query, like_query, like_query, like_query, like_query])
    sql += " ORDER BY bill_date DESC LIMIT 100"
    cursor.execute(sql, tuple(params))
    bills = cursor.fetchall()

    return render_template(
        "billing.html",
        username=session["username"],
        bills=bills,
        query=search_query
    )

@app.route("/billing/print/<int:bill_id>")
def print_billing(bill_id):

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute("SELECT * FROM billing WHERE bill_id = %s AND branch_id = %s", (bill_id, branch_id))
    bill = cursor.fetchone()
    if not bill:
        return redirect("/billing")

    cursor.execute("SELECT * FROM settings ORDER BY setting_id DESC LIMIT 1")
    settings = cursor.fetchone() or {}

    # Build an external URL to include in the QR code (points to the printable bill)
    try:
        qr_data = url_for('print_billing', bill_id=bill_id, _external=True)
    except Exception:
        qr_data = None

    return render_template(
        "billing_receipt.html",
        bill=bill,
        settings=settings,
        qr_data=qr_data,
        username=session["username"]
    )

@app.route("/add_billing", methods=["GET", "POST"])
def add_billing():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute("SELECT patient_id, full_name FROM patients WHERE branch_id=%s ORDER BY full_name ASC", (branch_id,))
    patients = cursor.fetchall()
    cursor.execute("SELECT doctor_id, doctor_name FROM doctors WHERE branch_id=%s ORDER BY doctor_name ASC", (branch_id,))
    doctors = cursor.fetchall()

    if request.method == "POST":
        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        bill_date = request.form["bill_date"]
        consultation_fee = request.form.get("consultation_fee", "0") or "0"
        medicine_fee = request.form.get("medicine_fee", "0") or "0"
        lab_fee = request.form.get("lab_fee", "0") or "0"
        room_fee = request.form.get("room_fee", "0") or "0"
        other_charges = request.form.get("other_charges", "0") or "0"
        payment_method = request.form.get("payment_method", "Cash")
        payment_status = request.form.get("payment_status", "Pending")

        patient_name = ""
        doctor_name = ""
        for patient in patients:
            if str(patient["patient_id"]) == str(patient_id):
                patient_name = patient["full_name"]
                break
        for doctor in doctors:
            if str(doctor["doctor_id"]) == str(doctor_id):
                doctor_name = doctor["doctor_name"]
                break

        if not patient_name or not doctor_name:
            flash("Please select a patient and doctor from the current branch.", "error")
            return redirect("/add_billing")

        try:
            total_amount = float(consultation_fee) + float(medicine_fee) + float(lab_fee) + float(room_fee) + float(other_charges)
        except ValueError:
            total_amount = 0

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO billing (branch_id, patient_id, patient_name, doctor_name, bill_date, consultation_fee, medicine_fee, lab_fee, room_fee, other_charges, total_amount, payment_method, payment_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (branch_id, patient_id, patient_name, doctor_name, bill_date, consultation_fee, medicine_fee, lab_fee, room_fee, other_charges, total_amount, payment_method, payment_status)
        )
        db.commit()
        return redirect("/billing")

    return render_template(
        "billing_form.html",
        action="Add Billing",
        form_action="/add_billing",
        patients=patients,
        doctors=doctors,
        bill={}
    )

@app.route("/laboratory")
def laboratory():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    search_query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    params = [branch_id]
    sql = """
SELECT l.lab_id,
       p.full_name AS patient_name,
       d.doctor_name,
       l.test_name,
       l.sample_type,
       l.test_date,
       l.result,
       l.normal_range,
       l.status,
       l.remarks
FROM laboratory l
LEFT JOIN patients p ON l.patient_id = p.patient_id AND p.branch_id = l.branch_id
LEFT JOIN doctors d ON l.doctor_id = d.doctor_id AND d.branch_id = l.branch_id
WHERE l.branch_id = %s
"""
    if search_query:
        like_query = f"%{search_query}%"
        sql += " AND (p.full_name LIKE %s OR d.doctor_name LIKE %s OR l.test_name LIKE %s OR l.sample_type LIKE %s OR l.result LIKE %s)"
        params.extend([like_query, like_query, like_query, like_query, like_query])
    if status:
        sql += " AND l.status = %s"
        params.append(status)
    sql += """
ORDER BY l.test_date DESC
LIMIT 100
"""
    cursor.execute(sql, tuple(params))
    labs = cursor.fetchall()

    return render_template(
        "laboratory_professional.html",
        username=session["username"],
        labs=labs
    )


@app.route('/laboratory/dashboard')
def laboratory_dashboard():
    if "username" not in session:
        return redirect('/login')
    if not require_branch_id():
        return redirect('/select_branch')
    return render_template('laboratory_dashboard.html', username=session['username'])


LIMS_SETTING_SECTIONS = [
    {"slug": "rate_category", "label": "Rate Category"},
    {"slug": "instrument", "label": "Instrument"},
    {"slug": "lab_group", "label": "Lab Group"},
    {"slug": "test", "label": "Test"},
    {"slug": "method", "label": "Method"},
    {"slug": "sample_vial", "label": "Sample Vial"},
    {"slug": "units", "label": "Units"},
    {"slug": "kits", "label": "Kits"},
    {"slug": "parameter", "label": "Parameter"},
    {"slug": "report_comment_master", "label": "Report Comment Master"},
]


@app.route("/lims_settings", defaults={"section": "rate_category"}, methods=["GET", "POST"])
@app.route("/lims_settings/<section>", methods=["GET", "POST"])
def lims_settings(section):
    if "username" not in session:
        return redirect("/login")

    section_map = {item["slug"]: item for item in LIMS_SETTING_SECTIONS}
    if section not in section_map:
        return redirect(url_for("lims_settings", section="rate_category"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        code = (request.form.get("code") or "").strip()
        status = (request.form.get("status") or "Active").strip()
        try:
            display_order = int(request.form.get("display_order") or 0)
        except Exception:
            display_order = 0
        description = (request.form.get("description") or "").strip()
        # rate applies to rate_category
        rate_val = None
        if section == 'rate_category':
            rate_raw = (request.form.get('rate') or '').strip()
            try:
                rate_val = float(rate_raw) if rate_raw != '' else None
            except Exception:
                rate_val = None

        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("lims_settings", section=section))

        try:
            cursor = db.cursor()
            branch_id = require_branch_id()
            cursor.execute(
                "INSERT INTO lims_settings_items (section_slug, name, code, status, display_order, description, rate, branch_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (section, name, code, status, display_order, description, rate_val, branch_id)
            )
            db.commit()
            flash(f"{section_map[section]['label']} saved successfully.", "success")
        except Exception:
            db.rollback()
            flash("Could not save the record. Check server logs.", "error")

        return redirect(url_for("lims_settings", section=section))

    # Load saved items for this section (branch-scoped)
    try:
        cursor = db.cursor(dictionary=True)
        branch_id = require_branch_id()
        if branch_id:
            cursor.execute(
                "SELECT id, name, code, status, display_order, description, rate, created_at FROM lims_settings_items WHERE section_slug=%s AND branch_id=%s ORDER BY display_order ASC, created_at DESC",
                (section, branch_id)
            )
        else:
            cursor.execute(
                "SELECT id, name, code, status, display_order, description, rate, created_at FROM lims_settings_items WHERE section_slug=%s ORDER BY display_order ASC, created_at DESC",
                (section,)
            )
        items = cursor.fetchall()
    except Exception:
        items = []

    return render_template(
        "lims_settings.html",
        username=session["username"],
        sections=LIMS_SETTING_SECTIONS,
        active_section=section_map[section],
        items=items,
    )


@app.route('/lims_settings/edit/<int:item_id>', methods=['GET', 'POST'])
def edit_lims_item(item_id):
    if "username" not in session:
        return redirect('/login')

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM lims_settings_items WHERE id=%s", (item_id,))
    item = cursor.fetchone()
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for('lims_settings'))

    branch_id = require_branch_id()
    if branch_id and item.get('branch_id') and item.get('branch_id') != branch_id:
        flash("You don't have permission to edit this item.", "error")
        return redirect(url_for('lims_settings', section=item.get('section_slug', 'rate_category')))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        code = (request.form.get('code') or '').strip()
        status = (request.form.get('status') or 'Active').strip()
        try:
            display_order = int(request.form.get('display_order') or 0)
        except Exception:
            display_order = 0
        description = (request.form.get('description') or '').strip()
        # handle rate when editing rate_category
        rate_val = None
        if item.get('section_slug') == 'rate_category':
            rate_raw = (request.form.get('rate') or '').strip()
            try:
                rate_val = float(rate_raw) if rate_raw != '' else None
            except Exception:
                rate_val = None
        if not name:
            flash('Name is required.', 'error')
            return redirect(url_for('edit_lims_item', item_id=item_id))

        try:
            cursor = db.cursor()
            if item.get('section_slug') == 'rate_category':
                cursor.execute(
                    "UPDATE lims_settings_items SET name=%s, code=%s, status=%s, display_order=%s, description=%s, rate=%s WHERE id=%s",
                    (name, code, status, display_order, description, rate_val, item_id)
                )
            else:
                cursor.execute(
                    "UPDATE lims_settings_items SET name=%s, code=%s, status=%s, display_order=%s, description=%s WHERE id=%s",
                    (name, code, status, display_order, description, item_id)
                )
            db.commit()
            flash('Record updated successfully.', 'success')
        except Exception:
            db.rollback()
            flash('Could not update the record.', 'error')

        return redirect(url_for('lims_settings', section=item.get('section_slug', 'rate_category')))

    # GET: render same template with editing_item and items
    section = item.get('section_slug') or 'rate_category'
    section_map = {it['slug']: it for it in LIMS_SETTING_SECTIONS}
    try:
        cursor = db.cursor(dictionary=True)
        if branch_id:
            cursor.execute(
                "SELECT id, name, code, status, display_order, description, created_at FROM lims_settings_items WHERE section_slug=%s AND branch_id=%s ORDER BY display_order ASC, created_at DESC",
                (section, branch_id)
            )
        else:
            cursor.execute(
                "SELECT id, name, code, status, display_order, description, created_at FROM lims_settings_items WHERE section_slug=%s ORDER BY display_order ASC, created_at DESC",
                (section,)
            )
        items = cursor.fetchall()
    except Exception:
        items = []

    return render_template(
        "lims_settings.html",
        username=session['username'],
        sections=LIMS_SETTING_SECTIONS,
        active_section=section_map.get(section, LIMS_SETTING_SECTIONS[0]),
        items=items,
        editing_item=item,
    )


@app.route('/lims_settings/delete/<int:item_id>', methods=['POST'])
def delete_lims_item(item_id):
    if "username" not in session:
        return redirect('/login')

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT section_slug, branch_id FROM lims_settings_items WHERE id=%s", (item_id,))
    row = cursor.fetchone()
    if not row:
        flash('Item not found.', 'error')
        return redirect(url_for('lims_settings'))

    branch_id = require_branch_id()
    if branch_id and row.get('branch_id') and row.get('branch_id') != branch_id:
        flash("You don't have permission to delete this item.", 'error')
        return redirect(url_for('lims_settings', section=row.get('section_slug', 'rate_category')))

    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM lims_settings_items WHERE id=%s", (item_id,))
        db.commit()
        flash('Record deleted.', 'success')
    except Exception:
        db.rollback()
        flash('Could not delete the record.', 'error')

    return redirect(url_for('lims_settings', section=row.get('section_slug', 'rate_category')))


@app.route('/update_rate', methods=['GET', 'POST'])
def update_rate():
    if "username" not in session:
        return redirect('/login')

    branch_id = require_branch_id()
    cursor = db.cursor(dictionary=True)

    # departments from doctors table
    try:
        if branch_id:
            cursor.execute('SELECT DISTINCT department FROM doctors WHERE branch_id=%s AND department IS NOT NULL ORDER BY department ASC', (branch_id,))
        else:
            cursor.execute('SELECT DISTINCT department FROM doctors WHERE department IS NOT NULL ORDER BY department ASC')
        departments = cursor.fetchall()
    except Exception:
        departments = []

    # simple subdepartments placeholder (could be extended later)
    subdepartments = []

    # rate categories
    try:
        if branch_id:
            cursor.execute("SELECT id, name, rate FROM lims_settings_items WHERE section_slug=%s AND branch_id=%s ORDER BY name ASC", ('rate_category', branch_id))
        else:
            cursor.execute("SELECT id, name, rate FROM lims_settings_items WHERE section_slug=%s ORDER BY name ASC", ('rate_category',))
        rate_categories = cursor.fetchall()
    except Exception:
        rate_categories = []

    selected_category_id = request.args.get('category_id')
    selected_category_name = ''
    selected_category_rate = None
    if selected_category_id:
        selected_category = next((c for c in rate_categories if str(c.get('id')) == selected_category_id), None)
        if selected_category:
            selected_category_name = selected_category.get('name', '')
            selected_category_rate = selected_category.get('rate')

    results = []
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'search':
            q = (request.form.get('search') or '').strip()
            dept = (request.form.get('department') or '').strip()
            try:
                if branch_id:
                    sql = "SELECT l.test_name, l.sample_type, d.department, p.full_name AS patient_name, d.doctor_name, l.test_date, l.status FROM laboratory l LEFT JOIN patients p ON p.patient_id=l.patient_id AND p.branch_id=l.branch_id LEFT JOIN doctors d ON d.doctor_id=l.doctor_id AND d.branch_id=l.branch_id WHERE l.branch_id=%s"
                    params = [branch_id]
                else:
                    sql = "SELECT l.test_name, l.sample_type, d.department, p.full_name AS patient_name, d.doctor_name, l.test_date, l.status FROM laboratory l LEFT JOIN patients p ON p.patient_id=l.patient_id LEFT JOIN doctors d ON d.doctor_id=l.doctor_id WHERE 1=1"
                    params = []
                if q:
                    sql += " AND l.test_name LIKE %s"
                    params.append(f"%{q}%")
                if dept:
                    sql += " AND d.department = %s"
                    params.append(dept)
                sql += " ORDER BY l.test_date DESC LIMIT 200"
                cursor.execute(sql, tuple(params))
                results = cursor.fetchall()
            except Exception:
                results = []
        elif action == 'update_rate':
            cat_id = request.form.get('category_id')
            new_rate_raw = (request.form.get('new_rate') or '').strip()
            try:
                new_rate = float(new_rate_raw) if new_rate_raw != '' else None
            except Exception:
                new_rate = None
            if cat_id:
                try:
                    cur2 = db.cursor()
                    cur2.execute('UPDATE lims_settings_items SET rate=%s WHERE id=%s', (new_rate, cat_id))
                    db.commit()
                    flash('Rate updated.', 'success')
                except Exception:
                    db.rollback()
                    flash('Could not update rate.', 'error')

    return render_template(
        'update_rate.html',
        username=session['username'],
        departments=departments,
        subdepartments=subdepartments,
        rate_categories=rate_categories,
        results=results,
        request=request,
        selected_category_id=selected_category_id,
        selected_category_name=selected_category_name,
        selected_category_rate=selected_category_rate,
    )


@app.route('/laboratory/dashboard/data')
def laboratory_dashboard_data():
    if "username" not in session:
        return redirect('/login')
    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect('/select_branch')
    # totals from billing.lab_fee
    cursor.execute("SELECT IFNULL(SUM(lab_fee),0) AS total_today FROM billing WHERE branch_id=%s AND DATE(bill_date)=CURDATE()", (branch_id,))
    total_today = cursor.fetchone()['total_today']
    cursor.execute("SELECT IFNULL(SUM(lab_fee),0) AS total_month FROM billing WHERE branch_id=%s AND MONTH(bill_date)=MONTH(CURDATE()) AND YEAR(bill_date)=YEAR(CURDATE())", (branch_id,))
    total_month = cursor.fetchone()['total_month']
    cursor.execute("SELECT IFNULL(SUM(lab_fee),0) AS total_year FROM billing WHERE branch_id=%s AND YEAR(bill_date)=YEAR(CURDATE())", (branch_id,))
    total_year = cursor.fetchone()['total_year']

    # department percentage by counting tests per doctor.department
    cursor.execute("SELECT d.department AS dept, COUNT(*) AS cnt FROM laboratory l LEFT JOIN doctors d ON l.doctor_id=d.doctor_id AND d.branch_id=l.branch_id WHERE l.branch_id=%s GROUP BY d.department", (branch_id,))
    dept_rows = cursor.fetchall()
    depts = []
    counts = []
    total_tests = 0
    for r in dept_rows:
        dept = r.get('dept') or 'Unknown'
        cnt = r.get('cnt') or 0
        depts.append(dept)
        counts.append(cnt)
        total_tests += cnt

    # prepare monthly breakdown for current month by day (simple)
    cursor.execute("SELECT DAY(bill_date) AS day, IFNULL(SUM(lab_fee),0) AS amt FROM billing WHERE branch_id=%s AND MONTH(bill_date)=MONTH(CURDATE()) AND YEAR(bill_date)=YEAR(CURDATE()) GROUP BY DAY(bill_date) ORDER BY DAY(bill_date)", (branch_id,))
    month_rows = cursor.fetchall()
    month_days = [r['day'] for r in month_rows]
    month_amounts = [float(r['amt']) for r in month_rows]

    data = {
        'total_today': float(total_today),
        'total_month': float(total_month),
        'total_year': float(total_year),
        'departments': depts,
        'dept_counts': counts,
        'total_tests': total_tests,
        'month_days': month_days,
        'month_amounts': month_amounts
    }
    from flask import jsonify
    return jsonify(data)


@app.route('/laboratory/today_collection')
def laboratory_today_collection():
    if "username" not in session:
        return redirect('/login')
    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect('/select_branch')
    cursor.execute("SELECT bill_id, patient_id, patient_name, lab_fee, bill_date FROM billing WHERE branch_id=%s AND DATE(bill_date)=CURDATE() AND IFNULL(lab_fee,0)>0 ORDER BY bill_date DESC", (branch_id,))
    rows = cursor.fetchall()
    return render_template('laboratory_today.html', rows=rows, username=session['username'])


@app.route('/admin/users', methods=['GET','POST'])
def admin_users():
    if 'username' not in session:
        return redirect('/login')

    role = str(session.get('role', '')).strip().lower()
    if role not in {'admin', 'administrator', 'system_admin'}:
        return redirect('/dashboard')

    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        action = request.form.get('action', 'update_role')

        if action == 'add_role':
            role_name = request.form.get('role_name', '').strip()
            role_description = request.form.get('role_description', '').strip()
            if role_name:
                safe_role = normalize_role_slug(role_name)
                try:
                    cur = db.cursor()
                    cur.execute('SELECT COUNT(*) AS cnt FROM roles WHERE role_name=%s', (safe_role,))
                    if cur.fetchone()[0] == 0:
                        cur.execute(
                            'INSERT INTO roles (role_name, role_description) VALUES (%s, %s)',
                            (safe_role, role_description)
                        )
                    db.commit()
                    flash(f'Role "{safe_role}" is ready to use. Now create a user with this role under Create User.', 'success')
                except Exception as exc:
                    db.rollback()
                    flash(f'Could not add role: {exc}', 'error')

        elif action == 'delete_role':
            role_name = request.form.get('role_name', '').strip()
            reserved_roles = {'admin', 'administrator', 'system_admin', 'user', 'lab', 'doctor'}
            if role_name and role_name.lower() not in reserved_roles:
                cur = db.cursor(dictionary=True)
                cur.execute('SELECT COUNT(*) AS count FROM users WHERE role=%s', (role_name,))
                if cur.fetchone()['count'] == 0:
                    cur.execute('DELETE FROM roles WHERE role_name=%s', (role_name,))
                    db.commit()

        elif action == 'add_user':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            role_val = normalize_role_name(request.form.get('role', '').strip() or 'user')
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            if not username or not password:
                flash('Username and password are required to create a user.', 'error')
            else:
                try:
                    cur = db.cursor(dictionary=True)
                    cur.execute('SELECT COUNT(*) AS cnt FROM users WHERE username=%s', (username,))
                    if cur.fetchone()['cnt'] > 0:
                        flash(f'Username "{username}" already exists. Please choose a different username.', 'error')
                    else:
                        cur.execute('INSERT INTO users (username, password, role, full_name, email, phone, active) VALUES (%s,%s,%s,%s,%s,%s,1)',
                                    (username, password, role_val, full_name, email, phone))
                        db.commit()
                        flash(f'User "{username}" created successfully.', 'success')
                except Exception as exc:
                    db.rollback()
                    flash(f'Could not create user: {exc}', 'error')

        elif action == 'delete_user':
            uname = request.form.get('username', '').strip()
            if uname and uname != session.get('username'):
                try:
                    cur = db.cursor()
                    cur.execute('DELETE FROM users WHERE username=%s', (uname,))
                    db.commit()
                except Exception:
                    db.rollback()

        elif action == 'toggle_active':
            uname = request.form.get('username', '').strip()
            if uname and uname != session.get('username'):
                try:
                    cur = db.cursor()
                    cur.execute("UPDATE users SET active = CASE WHEN IFNULL(active,1)=1 THEN 0 ELSE 1 END WHERE username=%s", (uname,))
                    db.commit()
                except Exception:
                    db.rollback()

        elif action == 'edit_user':
            uname = request.form.get('username', '').strip()
            if uname:
                full_name = request.form.get('full_name', '').strip()
                email = request.form.get('email', '').strip()
                phone = request.form.get('phone', '').strip()
                role_val = normalize_role_name(request.form.get('role', '').strip())
                try:
                    cur = db.cursor()
                    cur.execute('UPDATE users SET full_name=%s, email=%s, phone=%s, role=%s WHERE username=%s',
                                (full_name, email, phone, role_val, uname))
                    db.commit()
                except Exception:
                    db.rollback()

        else:
            uname = request.form.get('username')
            newrole = request.form.get('role')
            if uname and newrole:
                cur = db.cursor()
                cur.execute('UPDATE users SET role=%s WHERE username=%s', (normalize_role_name(newrole), uname))
                db.commit()

        return redirect(url_for('admin_users'))

    cursor.execute('SELECT username, role, full_name, email, phone, IFNULL(active,1) AS active FROM users ORDER BY username')
    users = cursor.fetchall()

    roles_cursor = db.cursor(dictionary=True)
    roles_cursor.execute('SELECT role_name, role_description FROM roles ORDER BY role_name')
    roles = roles_cursor.fetchall()
    return render_template('admin_users.html', users=users, roles=roles, username=session['username'])


@app.route('/admin/edit_user/<username>', methods=['GET', 'POST'])
def admin_edit_user(username):
    if 'username' not in session:
        return redirect('/login')
    role = str(session.get('role', '')).strip().lower()
    if role not in {'admin', 'administrator', 'system_admin'}:
        return redirect('/dashboard')

    cursor = db.cursor(dictionary=True)
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        role_val = normalize_role_name(request.form.get('role', '').strip())
        try:
            cursor.execute('UPDATE users SET full_name=%s, email=%s, phone=%s, role=%s WHERE username=%s', (full_name, email, phone, role_val, username))
            db.commit()
        except Exception:
            db.rollback()
        return redirect('/admin/users')

    cursor.execute('SELECT username, role, full_name, email, phone, IFNULL(active,1) AS active FROM users WHERE username=%s', (username,))
    user = cursor.fetchone()

    roles_cursor = db.cursor(dictionary=True)
    roles_cursor.execute('SELECT role_name FROM roles ORDER BY role_name')
    roles = roles_cursor.fetchall()
    if not user:
        return redirect('/admin/users')
    return render_template('admin_edit_user.html', user=user, roles=roles, username=session['username'])

@app.route("/add_laboratory", methods=["GET", "POST"])
def add_laboratory():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute("SELECT patient_id, full_name FROM patients WHERE branch_id=%s ORDER BY full_name ASC", (branch_id,))
    patients = cursor.fetchall()
    cursor.execute("SELECT doctor_id, doctor_name FROM doctors WHERE branch_id=%s ORDER BY doctor_name ASC", (branch_id,))
    doctors = cursor.fetchall()

    if request.method == "POST":
        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        test_name = request.form.get("test_name", "").strip().title()
        sample_type = request.form.get("sample_type", "").strip().title()
        test_date = request.form["test_date"]
        result = request.form.get("result", "").strip()
        normal_range = request.form.get("normal_range", "").strip()
        status = request.form.get("status", "Pending")
        remarks = request.form.get("remarks", "").strip()

        if not branch_record_exists("patients", "patient_id", patient_id, branch_id) or not branch_record_exists("doctors", "doctor_id", doctor_id, branch_id):
            flash("Please select a patient and doctor from the current branch.", "error")
            return redirect("/add_laboratory")

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO laboratory (branch_id, patient_id, doctor_id, test_name, sample_type, test_date, result, normal_range, status, remarks) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (branch_id, patient_id, doctor_id, test_name, sample_type, test_date, result, normal_range, status, remarks)
        )
        db.commit()
        return redirect("/laboratory")

    return render_template(
        "laboratory_form.html",
        action="Add Laboratory Test",
        form_action="/add_laboratory",
        patients=patients,
        doctors=doctors,
        lab={}
    )


@app.route("/view_laboratory/<int:lab_id>")
def view_laboratory(lab_id):
    if "username" not in session:
        return redirect("/login")
    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute("SELECT l.*, p.full_name AS patient_name, d.doctor_name FROM laboratory l LEFT JOIN patients p ON l.patient_id=p.patient_id AND p.branch_id=l.branch_id LEFT JOIN doctors d ON l.doctor_id=d.doctor_id AND d.branch_id=l.branch_id WHERE l.lab_id=%s AND l.branch_id=%s", (lab_id, branch_id))
    lab = cursor.fetchone()
    if not lab:
        return redirect('/laboratory')
    return render_template('laboratory_view.html', lab=lab, username=session['username'])


@app.route('/edit_laboratory/<int:lab_id>', methods=['GET','POST'])
def edit_laboratory(lab_id):
    if "username" not in session:
        return redirect("/login")
    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        test_name = request.form.get('test_name','').strip().title()
        sample_type = request.form.get('sample_type','').strip().title()
        test_date = request.form.get('test_date')
        result = request.form.get('result','').strip()
        normal_range = request.form.get('normal_range','').strip()
        status = request.form.get('status','Pending')
        remarks = request.form.get('remarks','').strip()
        if not branch_record_exists("patients", "patient_id", patient_id, branch_id) or not branch_record_exists("doctors", "doctor_id", doctor_id, branch_id):
            flash("Please select a patient and doctor from the current branch.", "error")
            return redirect(f'/edit_laboratory/{lab_id}')
        cursor.execute("UPDATE laboratory SET patient_id=%s, doctor_id=%s, test_name=%s, sample_type=%s, test_date=%s, result=%s, normal_range=%s, status=%s, remarks=%s WHERE lab_id=%s AND branch_id=%s", (patient_id, doctor_id, test_name, sample_type, test_date, result, normal_range, status, remarks, lab_id, branch_id))
        db.commit()
        return redirect('/laboratory')
    cursor.execute('SELECT patient_id, full_name FROM patients WHERE branch_id=%s ORDER BY full_name ASC', (branch_id,))
    patients = cursor.fetchall()
    cursor.execute('SELECT doctor_id, doctor_name FROM doctors WHERE branch_id=%s ORDER BY doctor_name ASC', (branch_id,))
    doctors = cursor.fetchall()
    cursor.execute('SELECT * FROM laboratory WHERE lab_id=%s AND branch_id=%s', (lab_id, branch_id))
    lab = cursor.fetchone()
    if not lab:
        return redirect('/laboratory')
    return render_template('laboratory_form.html', action='Edit Laboratory Test', form_action=f'/edit_laboratory/{lab_id}', patients=patients, doctors=doctors, lab=lab)


@app.route('/print_laboratory/<int:lab_id>')
def print_laboratory(lab_id):
    if "username" not in session:
        return redirect('/login')
    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect('/select_branch')
    cursor.execute("SELECT l.*, p.full_name AS patient_name, d.doctor_name FROM laboratory l LEFT JOIN patients p ON l.patient_id=p.patient_id AND p.branch_id=l.branch_id LEFT JOIN doctors d ON l.doctor_id=d.doctor_id AND d.branch_id=l.branch_id WHERE l.lab_id=%s AND l.branch_id=%s", (lab_id, branch_id))
    lab = cursor.fetchone()
    if not lab:
        return redirect('/laboratory')
    return render_template('laboratory_receipt.html', lab=lab, username=session['username'])


@app.route('/laboratory/export')
def export_laboratory():
    if "username" not in session:
        return redirect('/login')
    q = request.args.get('q','').strip()
    status = request.args.get('status','').strip()
    branch_id = require_branch_id()
    if not branch_id:
        return redirect('/select_branch')
    cursor = db.cursor()
    sql = "SELECT l.lab_id, p.full_name, l.test_name, d.doctor_name, l.test_date, l.status, l.result FROM laboratory l LEFT JOIN patients p ON l.patient_id=p.patient_id AND p.branch_id=l.branch_id LEFT JOIN doctors d ON l.doctor_id=d.doctor_id AND d.branch_id=l.branch_id"
    params = [branch_id]
    clauses = ['l.branch_id=%s']
    if q:
        like = f"%{q}%"
        clauses.append('(p.full_name LIKE %s OR l.test_name LIKE %s OR d.doctor_name LIKE %s)')
        params.extend([like, like, like])
    if status:
        clauses.append('l.status=%s')
        params.append(status)
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    sql += ' ORDER BY l.test_date DESC'
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    # build CSV
    import io, csv
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Test ID','Patient','Test','Doctor','Date','Status','Result'])
    for r in rows:
        cw.writerow([r[0], r[1] or '', r[2] or '', r[3] or '', r[4] or '', r[5] or '', r[6] or ''])
    output = si.getvalue()
    from flask import Response
    return Response(output, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=laboratory_export.csv"})


@app.route('/delete_laboratory/<int:lab_id>', methods=['POST','GET'])
def delete_laboratory(lab_id):
    if "username" not in session:
        return redirect('/login')
    branch_id = require_branch_id()
    if not branch_id:
        return redirect('/select_branch')
    cursor = db.cursor()
    cursor.execute('SELECT lab_id FROM laboratory WHERE lab_id=%s AND branch_id=%s', (lab_id, branch_id))
    if not cursor.fetchone():
        return redirect('/laboratory')
    cursor.execute('DELETE FROM laboratory WHERE lab_id=%s AND branch_id=%s', (lab_id, branch_id))
    db.commit()
    return redirect('/laboratory')

@app.route("/settings", methods=["GET", "POST"])
def settings():

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM settings ORDER BY setting_id DESC LIMIT 1")
    current = cursor.fetchone()

    if request.method == "POST":
        hospital_name = request.form.get("hospital_name", "").strip()
        hospital_logo = request.form.get("hospital_logo", "").strip()
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        country = request.form.get("country", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        website = request.form.get("website", "").strip()
        currency = request.form.get("currency", "INR").strip()
        timezone = request.form.get("timezone", "Asia/Kolkata").strip()
        theme = request.form.get("theme", "Light").strip()
        language = request.form.get("language", "English").strip()

        if current:
            cursor.execute(
                "UPDATE settings SET hospital_name=%s, hospital_logo=%s, address=%s, city=%s, state=%s, country=%s, postal_code=%s, phone=%s, email=%s, website=%s, currency=%s, timezone=%s, theme=%s, language=%s WHERE setting_id=%s",
                (hospital_name, hospital_logo, address, city, state, country, postal_code, phone, email, website, currency, timezone, theme, language, current["setting_id"])
            )
        else:
            cursor.execute(
                "INSERT INTO settings (hospital_name, hospital_logo, address, city, state, country, postal_code, phone, email, website, currency, timezone, theme, language) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (hospital_name, hospital_logo, address, city, state, country, postal_code, phone, email, website, currency, timezone, theme, language)
            )
        db.commit()
        return redirect("/settings")

    return render_template(
        "settings.html",
        username=session["username"],
        settings=current or {}
    )


@app.route("/settings/root_menu", methods=["GET", "POST"])
def root_menu():
    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        action = request.form.get("action", "save")
        root_menu_id = request.form.get("root_menu_id")

        if action in {"save", "update"}:
            name = request.form.get("name", "").strip()
            icon_name = normalize_icon_name(request.form.get("icon_name", ""))
            url = request.form.get("url", "").strip() or "#"
            status = request.form.get("status", "Active").strip()
            status = "Inactive" if status.lower() == "inactive" else "Active"
            try:
                display_order = int(request.form.get("display_order", "0") or 0)
            except ValueError:
                display_order = 0

            if name:
                try:
                    if action == "update" and root_menu_id:
                        cursor.execute(
                            "UPDATE root_menus SET name=%s, icon_name=%s, url=%s, status=%s, display_order=%s WHERE root_menu_id=%s",
                            (name, icon_name, url, status, display_order, root_menu_id)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO root_menus (name, icon_name, url, status, display_order) VALUES (%s, %s, %s, %s, %s)",
                            (name, icon_name, url, status, display_order)
                        )
                    db.commit()
                except Exception:
                    db.rollback()

        elif action == "delete" and root_menu_id:
            try:
                cursor.execute("DELETE FROM root_menus WHERE root_menu_id=%s", (root_menu_id,))
                db.commit()
            except Exception:
                db.rollback()

        elif action == "toggle_status" and root_menu_id:
            try:
                cursor.execute(
                    "UPDATE root_menus SET status = CASE WHEN status='Active' THEN 'Inactive' ELSE 'Active' END WHERE root_menu_id=%s",
                    (root_menu_id,)
                )
                db.commit()
            except Exception:
                db.rollback()

        return redirect(url_for("root_menu"))

    search_query = request.args.get("q", "").strip()
    edit_id = request.args.get("edit", "").strip()
    edit_menu = None

    if edit_id:
        cursor.execute(
            "SELECT root_menu_id, name, icon_name, url, status, display_order FROM root_menus WHERE root_menu_id=%s",
            (edit_id,)
        )
        edit_menu = cursor.fetchone()

    params = []
    sql = "SELECT root_menu_id, name, icon_name, url, status, display_order FROM root_menus"
    if search_query:
        like_query = f"%{search_query}%"
        sql += " WHERE name LIKE %s OR icon_name LIKE %s OR url LIKE %s OR status LIKE %s"
        params = [like_query, like_query, like_query, like_query]
    sql += " ORDER BY display_order ASC, name ASC"
    cursor.execute(sql, tuple(params))
    root_menus = cursor.fetchall()

    return render_template(
        "root_menu.html",
        username=session["username"],
        root_menus=root_menus,
        edit_menu=edit_menu,
        search_query=search_query
    )


@app.route("/settings/sub_menu", methods=["GET", "POST"])
def sub_menu():
    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        action = request.form.get("action", "save")
        sub_menu_id = request.form.get("sub_menu_id")

        if action in {"save", "update"}:
            root_menu_id = request.form.get("root_menu_id") or None
            name = request.form.get("name", "").strip()
            icon_name = normalize_icon_name(request.form.get("icon_name", ""))
            url = request.form.get("url", "").strip() or "#"
            status = request.form.get("status", "Active").strip()
            status = "Inactive" if status.lower() == "inactive" else "Active"
            try:
                display_order = int(request.form.get("display_order", "0") or 0)
            except ValueError:
                display_order = 0

            if root_menu_id and name:
                try:
                    if action == "update" and sub_menu_id:
                        cursor.execute(
                            "UPDATE sub_menus SET root_menu_id=%s, name=%s, icon_name=%s, url=%s, status=%s, display_order=%s WHERE sub_menu_id=%s",
                            (root_menu_id, name, icon_name, url, status, display_order, sub_menu_id)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO sub_menus (root_menu_id, name, icon_name, url, status, display_order) VALUES (%s, %s, %s, %s, %s, %s)",
                            (root_menu_id, name, icon_name, url, status, display_order)
                        )
                    db.commit()
                except Exception:
                    db.rollback()

        elif action == "delete" and sub_menu_id:
            try:
                cursor.execute("DELETE FROM sub_menus WHERE sub_menu_id=%s", (sub_menu_id,))
                db.commit()
            except Exception:
                db.rollback()

        elif action == "toggle_status" and sub_menu_id:
            try:
                cursor.execute(
                    "UPDATE sub_menus SET status = CASE WHEN status='Active' THEN 'Inactive' ELSE 'Active' END WHERE sub_menu_id=%s",
                    (sub_menu_id,)
                )
                db.commit()
            except Exception:
                db.rollback()

        return redirect(url_for("sub_menu"))

    search_query = request.args.get("q", "").strip()
    edit_id = request.args.get("edit", "").strip()
    edit_menu = None

    if edit_id:
        cursor.execute(
            "SELECT sub_menu_id, root_menu_id, name, icon_name, url, status, display_order FROM sub_menus WHERE sub_menu_id=%s",
            (edit_id,)
        )
        edit_menu = cursor.fetchone()

    cursor.execute(
        "SELECT root_menu_id, name FROM root_menus ORDER BY display_order ASC, name ASC"
    )
    root_options = cursor.fetchall()

    params = []
    sql = """
        SELECT
            sm.sub_menu_id,
            sm.root_menu_id,
            sm.name,
            sm.icon_name,
            sm.url,
            sm.status,
            sm.display_order,
            COALESCE(rm.name, 'Unassigned') AS root_name
        FROM sub_menus sm
        LEFT JOIN root_menus rm ON sm.root_menu_id = rm.root_menu_id
    """
    if search_query:
        like_query = f"%{search_query}%"
        sql += " WHERE sm.name LIKE %s OR sm.icon_name LIKE %s OR sm.url LIKE %s OR sm.status LIKE %s OR rm.name LIKE %s"
        params = [like_query, like_query, like_query, like_query, like_query]
    sql += " ORDER BY COALESCE(rm.display_order, 9999) ASC, sm.display_order ASC, sm.name ASC"
    cursor.execute(sql, tuple(params))
    sub_menus = cursor.fetchall()

    return render_template(
        "sub_menu.html",
        username=session["username"],
        sub_menus=sub_menus,
        root_options=root_options,
        edit_menu=edit_menu,
        search_query=search_query
    )


@app.route("/add_patient", methods=["GET", "POST"])
def add_patient():

    if "username" not in session:
        return redirect("/login")

    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")

    if request.method == "POST":
        full_name = request.form["full_name"].strip().title()
        age_years = request.form.get("age_years", "0")
        age_months = request.form.get("age_months", "0")
        age_days = request.form.get("age_days", "0")
        age_years, age_months, age_days = normalize_age_parts(age_years, age_months, age_days)
        age = age_years
        gender = request.form["gender"]
        phone = request.form["phone"].strip()
        address = request.form.get("address", "").strip().title()
        blood_group = request.form.get("blood_group", "").strip().upper()
        disease = request.form.get("disease", "").strip().title()
        admission_date = request.form["admission_date"]
        guardian_name = request.form.get("guardian_name", "").strip().title()
        guardian_phone = request.form.get("guardian_phone", "").strip()
        guardian_relation = request.form.get("guardian_relation", "").strip().title()

        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO patients (branch_id, full_name, age, age_years, age_months, age_days, gender, phone, address, blood_group, disease, admission_date, guardian_name, guardian_phone, guardian_relation) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (branch_id, full_name, age, age_years, age_months, age_days, gender, phone, address, blood_group, disease, admission_date, guardian_name, guardian_phone, guardian_relation)
        )
        db.commit()
        return redirect("/patients")

    return render_template(
        "patient_form.html",
        action="Add Patient",
        form_action="/add_patient",
        patient={}
    )

@app.route("/edit_patient/<int:patient_id>", methods=["GET", "POST"])
def edit_patient(patient_id):

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")

    if request.method == "POST":
        full_name = request.form["full_name"].strip().title()
        age_years = request.form.get("age_years", "0")
        age_months = request.form.get("age_months", "0")
        age_days = request.form.get("age_days", "0")
        age_years, age_months, age_days = normalize_age_parts(age_years, age_months, age_days)
        age = age_years
        gender = request.form["gender"]
        phone = request.form["phone"].strip()
        address = request.form.get("address", "").strip().title()
        blood_group = request.form.get("blood_group", "").strip().upper()
        disease = request.form.get("disease", "").strip().title()
        admission_date = request.form["admission_date"]
        guardian_name = request.form.get("guardian_name", "").strip().title()
        guardian_phone = request.form.get("guardian_phone", "").strip()
        guardian_relation = request.form.get("guardian_relation", "").strip().title()

        cursor.execute(
            "UPDATE patients SET full_name=%s, age=%s, age_years=%s, age_months=%s, age_days=%s, gender=%s, phone=%s, address=%s, blood_group=%s, disease=%s, admission_date=%s, guardian_name=%s, guardian_phone=%s, guardian_relation=%s WHERE patient_id=%s AND branch_id=%s",
            (full_name, age, age_years, age_months, age_days, gender, phone, address, blood_group, disease, admission_date, guardian_name, guardian_phone, guardian_relation, patient_id, branch_id)
        )
        db.commit()
        return redirect("/patients")

    cursor.execute(
        "SELECT patient_id, full_name, age, age_years, age_months, age_days, gender, phone, address, blood_group, disease, admission_date, guardian_name, guardian_phone, guardian_relation FROM patients WHERE patient_id=%s AND branch_id=%s",
        (patient_id, branch_id)
    )
    patient = cursor.fetchone()

    if not patient:
        return redirect("/patients")

    if patient.get("age_years") is None:
        years, months, days = parse_age_parts(patient.get("age"))
        patient["age_years"] = years
        patient["age_months"] = months
        patient["age_days"] = days
    else:
        patient["age_years"] = patient.get("age_years", 0)
        patient["age_months"] = patient.get("age_months", 0)
        patient["age_days"] = patient.get("age_days", 0)

    return render_template(
        "patient_form.html",
        action="Edit Patient",
        form_action=f"/edit_patient/{patient_id}",
        patient=patient
    )

@app.route("/delete_patient/<int:patient_id>", methods=["GET", "POST"])
def delete_patient(patient_id):

    if "username" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute(
        "SELECT patient_id, full_name FROM patients WHERE patient_id=%s AND branch_id=%s",
        (patient_id, branch_id)
    )
    patient = cursor.fetchone()

    if not patient:
        return redirect("/patients")

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        deleted_by = session.get("username")
        cursor.execute(
            "INSERT INTO patient_deletion_log (patient_id, branch_id, full_name, deleted_by, reason) VALUES (%s, %s, %s, %s, %s)",
            (patient_id, branch_id, patient["full_name"], deleted_by, reason)
        )
        cursor.execute(
            "DELETE FROM patients WHERE patient_id=%s AND branch_id=%s",
            (patient_id, branch_id)
        )
        db.commit()
        return redirect("/patients")

    return render_template(
        "patient_delete_confirm.html",
        patient=patient
    )


@app.route("/deletion_log")
def deletion_log():

    if "username" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return redirect("/dashboard")

    cursor = db.cursor(dictionary=True)
    branch_id = require_branch_id()
    if not branch_id:
        return redirect("/select_branch")
    cursor.execute(
        "SELECT log_id, patient_id, full_name, deleted_by, reason, deleted_at FROM patient_deletion_log WHERE branch_id=%s ORDER BY deleted_at DESC",
        (branch_id,)
    )
    logs = cursor.fetchall()

    return render_template(
        "deletion_log.html",
        logs=logs
    )


def ensure_chat_tables():
    """Create chat tables for system-user messaging."""
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_threads (
            thread_id INT AUTO_INCREMENT PRIMARY KEY,
            user1_id INT NOT NULL,
            user2_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_thread_users (user1_id, user2_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id INT AUTO_INCREMENT PRIMARY KEY,
            thread_id INT NOT NULL,
            from_user_id INT NOT NULL,
            message TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_thread_time (thread_id, sent_at),
            CONSTRAINT fk_chat_thread FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id) ON DELETE CASCADE
        )
    """)

    db.commit()


@app.route("/chat")
def chat():
    if "username" not in session:
        return redirect("/login")

    ensure_chat_tables()

    cursor = db.cursor(dictionary=True)
    current_username = session["username"]

    cursor.execute("SELECT user_id, username, full_name, role FROM users WHERE username=%s", (current_username,))
    current_user = cursor.fetchone()
    if not current_user:
        return redirect("/dashboard")

    # Peer selection
    peer_username = request.args.get("peer", "").strip()

    cursor.execute(
        "SELECT user_id, username, full_name, role FROM users WHERE username <> %s AND active=1 ORDER BY username ASC",
        (current_username,)
    )
    users = cursor.fetchall()

    if not users:
        return render_template(
            "chat.html",
            users=[],
            current_username=current_username,
            active_peer_username="",
            active_peer_name="No users available"
        )

    if not peer_username:
        peer_username = users[0]["username"]

    # Active peer info
    peer_info = next((u for u in users if u["username"] == peer_username), None)
    if not peer_info:
        peer_username = users[0]["username"]
        peer_info = users[0]

    return render_template(
        "chat.html",
        users=users,
        current_username=current_username,
        active_peer_username=peer_username,
        active_peer_name=(peer_info.get("full_name") or peer_info.get("username"))
    )


def get_or_create_thread(user1_id, user2_id):
    # Ensure deterministic ordering for UNIQUE constraint
    u1, u2 = (user1_id, user2_id) if user1_id <= user2_id else (user2_id, user1_id)

    cursor = db.cursor()
    cursor.execute(
        "SELECT thread_id FROM chat_threads WHERE user1_id=%s AND user2_id=%s LIMIT 1",
        (u1, u2)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO chat_threads (user1_id, user2_id) VALUES (%s, %s)",
        (u1, u2)
    )
    db.commit()
    return cursor.lastrowid


@app.route("/chat/messages")
def chat_messages():
    if "username" not in session:
        return redirect("/login")

    ensure_chat_tables()

    from flask import jsonify

    peer_username = (request.args.get("peer") or "").strip()
    current_username = session["username"]

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT user_id, username FROM users WHERE username=%s", (current_username,))
    me = cursor.fetchone()

    cursor.execute("SELECT user_id, username FROM users WHERE username=%s AND active=1", (peer_username,))
    peer = cursor.fetchone()

    if not me or not peer:
        return jsonify({"messages": []})

    thread_id = get_or_create_thread(me["user_id"], peer["user_id"])

    cursor.execute(
        """
        SELECT m.from_user_id,
               u_from.username AS from_username,
               m.message,
               DATE_FORMAT(m.sent_at, '%Y-%m-%d %H:%i') AS sent_at
        FROM chat_messages m
        JOIN chat_threads t ON t.thread_id=m.thread_id
        JOIN users u_from ON u_from.user_id=m.from_user_id
        WHERE m.thread_id=%s
        ORDER BY m.sent_at ASC
        LIMIT 500
        """,
        (thread_id,)
    )
    rows = cursor.fetchall()

    return jsonify({"messages": rows or []})


@app.route("/chat/send", methods=["POST"])
def chat_send():
    if "username" not in session:
        return redirect("/login")

    ensure_chat_tables()

    from flask import jsonify

    payload = request.get_json(silent=True) or {}
    peer_username = (payload.get("peer_username") or "").strip()
    message = (payload.get("message") or "").strip()

    if not peer_username or not message:
        return jsonify({"ok": False, "error": "missing"}), 400

    cursor = db.cursor(dictionary=True)
    current_username = session["username"]

    cursor.execute("SELECT user_id FROM users WHERE username=%s AND active=1", (current_username,))
    me = cursor.fetchone()

    cursor.execute("SELECT user_id FROM users WHERE username=%s AND active=1", (peer_username,))
    peer = cursor.fetchone()

    if not me or not peer:
        return jsonify({"ok": False, "error": "user"}), 400

    thread_id = get_or_create_thread(me["user_id"], peer["user_id"])

    cursor.execute(
        "INSERT INTO chat_messages (thread_id, from_user_id, message) VALUES (%s, %s, %s)",
        (thread_id, me["user_id"], message)
    )
    db.commit()

    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True, use_reloader=True)

