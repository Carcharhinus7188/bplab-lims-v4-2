from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import DATA_DIR, EXPERIMENTS


UTC8 = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(UTC8).replace(microsecond=0).isoformat()


def db_path() -> Path:
    return Path(os.environ.get("BPLAB_DB_PATH", DATA_DIR / "bplab_trace_v57.db"))


@contextmanager
def connect(path: Path | None = None):
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    address TEXT DEFAULT '',
    contact TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    management_no TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    model TEXT DEFAULT '',
    measurement_range TEXT DEFAULT '',
    manufacturer TEXT DEFAULT '',
    serial_no TEXT DEFAULT '',
    category TEXT DEFAULT '',
    calibration_certificate TEXT DEFAULT '',
    traceability_body TEXT DEFAULT '',
    calibration_date TEXT DEFAULT '',
    valid_until TEXT DEFAULT '',
    responsible_person TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT '启用',
    status_reason TEXT DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiment_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_code TEXT NOT NULL,
    version TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    change_note TEXT DEFAULT '',
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(experiment_code, version)
);
CREATE TABLE IF NOT EXISTS experiment_equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_versions(id) ON DELETE CASCADE,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    role TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 1,
    UNIQUE(experiment_version_id, equipment_id)
);
CREATE TABLE IF NOT EXISTS commissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commission_no TEXT NOT NULL UNIQUE,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    production_unit TEXT NOT NULL,
    production_address TEXT DEFAULT '',
    received_date TEXT NOT NULL,
    due_date TEXT DEFAULT '',
    detection_type TEXT NOT NULL DEFAULT '委托检测',
    main_tester_id INTEGER REFERENCES users(id),
    reviewer_id INTEGER REFERENCES users(id),
    approver_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'draft',
    notes TEXT DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sample_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commission_id INTEGER NOT NULL REFERENCES commissions(id) ON DELETE CASCADE,
    group_no INTEGER NOT NULL,
    sample_name TEXT NOT NULL,
    specification TEXT DEFAULT '',
    material TEXT DEFAULT '',
    batch_no TEXT DEFAULT '',
    quantity INTEGER NOT NULL,
    unit TEXT NOT NULL DEFAULT '件',
    receive_condition TEXT NOT NULL DEFAULT '完好',
    receive_note TEXT DEFAULT '',
    sample_ids_json TEXT NOT NULL,
    shelf_status TEXT NOT NULL DEFAULT '在库',
    UNIQUE(commission_id, group_no)
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_no TEXT NOT NULL UNIQUE,
    commission_id INTEGER NOT NULL REFERENCES commissions(id),
    sample_group_id INTEGER NOT NULL REFERENCES sample_groups(id),
    experiment_code TEXT NOT NULL,
    experiment_version_id INTEGER NOT NULL REFERENCES experiment_versions(id),
    tester_id INTEGER REFERENCES users(id),
    reviewer_id INTEGER REFERENCES users(id),
    location TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    config_snapshot_json TEXT NOT NULL,
    equipment_snapshot_json TEXT NOT NULL,
    inherited_snapshot_json TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    calculations_json TEXT NOT NULL DEFAULT '{}',
    judgment TEXT DEFAULT '',
    started_at TEXT,
    submitted_at TEXT,
    reviewed_at TEXT,
    returned_at TEXT,
    return_condition TEXT DEFAULT '',
    return_note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS record_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    data_snapshot_json TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    output_path TEXT DEFAULT '',
    operator_id INTEGER REFERENCES users(id),
    review_comment TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(task_id, version)
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attachment_no TEXT NOT NULL UNIQUE,
    commission_id INTEGER NOT NULL REFERENCES commissions(id),
    task_id INTEGER REFERENCES tasks(id),
    sample_group_id INTEGER REFERENCES sample_groups(id),
    sample_id TEXT DEFAULT '',
    attachment_type TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES users(id),
    description TEXT DEFAULT '',
    source_relation TEXT DEFAULT '原始文件',
    sha256 TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT '待核对'
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commission_id INTEGER NOT NULL UNIQUE REFERENCES commissions(id),
    report_no TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT '待检测员确认',
    tester_id INTEGER REFERENCES users(id),
    reviewer_id INTEGER REFERENCES users(id),
    approver_id INTEGER REFERENCES users(id),
    snapshot_json TEXT NOT NULL,
    output_path TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    tester_signed_at TEXT,
    reviewer_signed_at TEXT,
    approver_signed_at TEXT,
    published_at TEXT,
    return_comment TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_commission ON tasks(commission_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_attachments_task ON attachments(task_id);
"""


def _password_hash(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 220_000)
    return digest.hex(), salt.hex()


def _seed_users(conn: sqlite3.Connection) -> None:
    defaults = [
        ("admin", "系统管理员", "admin", "admin123"),
        ("sample", "样品管理员", "sample_manager", "sample123"),
        ("tester", "实验员", "tester", "123456"),
        ("reviewer", "复核员", "reviewer", "review123"),
        ("approver", "批准人", "approver", "approve123"),
    ]
    for username, display_name, role, password in defaults:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            continue
        digest, salt = _password_hash(password)
        conn.execute(
            "INSERT INTO users(username,display_name,role,password_hash,salt,created_at) VALUES(?,?,?,?,?,?)",
            (username, display_name, role, digest, salt, now_iso()),
        )


EQUIPMENT_SEED = [
    ("BPGL-A035", "数显维氏硬度计", "HV-30Z", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-A036", "表面粗糙度仪", "TR200", "±160 μm", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-A040", "大理石平台", "", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-A041", "高精度数字水平仪", "", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-B007", "标准维氏硬度块", "466HV10", "", "", "", "B", "", "", "", "", "", "启用"),
    ("BPGL-XRAY", "X射线数字成像设备", "", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-IMG", "二次元影像测量仪", "", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-CUT", "高速精密切割机", "", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-CTE", "热膨胀测试仪", "", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-OVEN", "电热恒温烘箱", "", "100±2 ℃", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-BEND", "电子万能试验机", "", "0～2000 N，0.5级", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-COLOR", "耐光色稳定性测试仪", "SGJ611Y", "", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-D65", "D65标准光源灯箱", "D65", "1000～2000 lx", "", "", "A", "", "", "", "", "", "启用"),
    ("BPGL-TIMER", "电子秒表", "YS-860", "", "", "", "A", "", "", "", "", "", "启用"),
]

EQUIPMENT_BINDINGS = {
    "roughness": [("BPGL-A036", "主设备", 1), ("BPGL-A040", "平台", 1), ("BPGL-A041", "水平仪", 1)],
    "crack_initiation": [("BPGL-BEND", "主设备", 1)],
    "xray": [("BPGL-XRAY", "主设备", 1)],
    "warpage": [("BPGL-IMG", "主设备", 1), ("BPGL-CUT", "制样设备", 1)],
    "thermal_expansion": [("BPGL-CTE", "主设备", 1)],
    "thermal_shock": [("BPGL-OVEN", "主设备", 1), ("BPGL-TIMER", "计时器", 1)],
    "bending": [("BPGL-BEND", "主设备", 1)],
    "vickers": [("BPGL-A035", "主设备", 1), ("BPGL-B007", "标准器", 1), ("BPGL-A040", "平台", 0)],
    "thickness": [("BPGL-IMG", "主设备", 1), ("BPGL-A040", "平台", 0)],
    "color_stability": [("BPGL-COLOR", "主设备", 1), ("BPGL-D65", "观察光源", 1), ("BPGL-TIMER", "计时器", 1)],
}


def _seed_equipment(conn: sqlite3.Connection) -> None:
    for row in EQUIPMENT_SEED:
        if conn.execute("SELECT 1 FROM equipment WHERE management_no=?", (row[0],)).fetchone():
            continue
        conn.execute(
            """INSERT INTO equipment(
                management_no,name,model,measurement_range,manufacturer,serial_no,category,
                calibration_certificate,traceability_body,calibration_date,valid_until,
                responsible_person,status,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*row, now_iso()),
        )


def _seed_experiments(conn: sqlite3.Connection) -> None:
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    admin_id = admin["id"] if admin else None
    for code, config in EXPERIMENTS.items():
        row = conn.execute(
            "SELECT id FROM experiment_versions WHERE experiment_code=? AND version='1.0'",
            (code,),
        ).fetchone()
        if row:
            version_id = row["id"]
        else:
            cur = conn.execute(
                """INSERT INTO experiment_versions(
                    experiment_code,version,config_json,status,change_note,approved_by,approved_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    code,
                    "1.0",
                    json.dumps(config, ensure_ascii=False),
                    "current",
                    "V5.7初始受控配置",
                    admin_id,
                    now_iso(),
                    now_iso(),
                ),
            )
            version_id = cur.lastrowid
        for management_no, role, required in EQUIPMENT_BINDINGS.get(code, []):
            equipment = conn.execute(
                "SELECT id FROM equipment WHERE management_no=?", (management_no,)
            ).fetchone()
            if equipment:
                conn.execute(
                    """INSERT OR IGNORE INTO experiment_equipment(
                        experiment_version_id,equipment_id,role,required
                    ) VALUES(?,?,?,?)""",
                    (version_id, equipment["id"], role, required),
                )


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _seed_users(conn)
        _seed_equipment(conn)
        _seed_experiments(conn)


def query(sql: str, params: Iterable[Any] = (), path: Path | None = None) -> list[dict[str, Any]]:
    with connect(path) as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = (), path: Path | None = None) -> dict[str, Any] | None:
    rows = query(sql, params, path)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = (), path: Path | None = None) -> int:
    with connect(path) as conn:
        cur = conn.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)


def authenticate(username: str, password: str, path: Path | None = None) -> dict[str, Any] | None:
    user = query_one("SELECT * FROM users WHERE username=? AND active=1", (username,), path)
    if not user:
        return None
    digest, _ = _password_hash(password, user["salt"])
    if not hmac.compare_digest(digest, user["password_hash"]):
        return None
    return {k: v for k, v in user.items() if k not in {"password_hash", "salt"}}


def create_session(user_id: int, days: int = 7, path: Path | None = None) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(UTC8) + timedelta(days=days)).replace(microsecond=0).isoformat()
    execute(
        "INSERT INTO sessions(token,user_id,expires_at,created_at) VALUES(?,?,?,?)",
        (token, user_id, expires, now_iso()),
        path,
    )
    return token


def session_user(token: str, path: Path | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    row = query_one(
        """SELECT u.id,u.username,u.display_name,u.role,u.active,s.expires_at
           FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?""",
        (token,),
        path,
    )
    if not row or not row["active"] or row["expires_at"] < now_iso():
        execute("DELETE FROM sessions WHERE token=?", (token,), path)
        return None
    return row


def delete_session(token: str, path: Path | None = None) -> None:
    execute("DELETE FROM sessions WHERE token=?", (token,), path)


def audit(
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    detail: dict[str, Any] | None = None,
    path: Path | None = None,
) -> None:
    execute(
        "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
        (actor_id, action, entity_type, str(entity_id), json.dumps(detail or {}, ensure_ascii=False), now_iso()),
        path,
    )


def json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default

