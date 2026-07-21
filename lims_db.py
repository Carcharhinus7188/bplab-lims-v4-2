# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo
import calendar
import hashlib
import json
import re
import secrets
import sqlite3
from typing import Any, Iterable

from constants import EXPERIMENTS, TIMEZONE_NAME

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "bplab_trace.db"
CHINA_TZ = ZoneInfo(TIMEZONE_NAME)


def china_now() -> datetime:
    return datetime.now(CHINA_TZ).replace(tzinfo=None)


def china_today() -> date:
    return china_now().date()


def now() -> str:
    return china_now().isoformat(timespec="seconds")


def add_months_to_date(value: date | str, months: int = 1) -> date:
    if isinstance(value, str):
        value = date.fromisoformat(value)
    total = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _rows(sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, tuple(args)).fetchall()]


def _one(sql: str, args: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connect() as c:
        r = c.execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def _phash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def init_db() -> None:
    with connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
              username TEXT PRIMARY KEY, display_name TEXT NOT NULL,
              password_hash TEXT NOT NULL, role TEXT NOT NULL,
              enabled INTEGER DEFAULT 1, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions(
              token TEXT PRIMARY KEY, username TEXT NOT NULL,
              expires_at TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS customers(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              customer_code TEXT UNIQUE, name TEXT UNIQUE NOT NULL,
              short_name TEXT, address TEXT, contact TEXT, phone TEXT,
              notes TEXT, enabled INTEGER DEFAULT 1,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sample_catalog(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              sample_code TEXT UNIQUE, name TEXT NOT NULL, model TEXT NOT NULL,
              production_unit TEXT, category TEXT, unit TEXT DEFAULT '件',
              default_experiments TEXT, notes TEXT, enabled INTEGER DEFAULT 1,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(name, model)
            );
            CREATE TABLE IF NOT EXISTS commissions(
              commission_no TEXT PRIMARY KEY, customer_id INTEGER,
              customer_name TEXT NOT NULL, customer_address TEXT,
              contact TEXT, phone TEXT, commission_date TEXT NOT NULL,
              due_date TEXT NOT NULL, sample_condition TEXT NOT NULL,
              condition_note TEXT, subcontract_allowed TEXT,
              confidentiality TEXT, report_medium TEXT,
              conformity_judgment TEXT, uncertainty TEXT,
              delivery_method TEXT, cnas_mark TEXT, capability TEXT,
              notes TEXT, status TEXT DEFAULT '已入库',
              created_by TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS commission_tests(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              commission_no TEXT NOT NULL, experiment TEXT NOT NULL,
              standard TEXT, status TEXT DEFAULT '待分配', task_no TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(commission_no, experiment)
            );
            CREATE TABLE IF NOT EXISTS samples(
              sample_no TEXT PRIMARY KEY, base_no TEXT NOT NULL,
              commission_no TEXT NOT NULL, sample_catalog_id INTEGER,
              sample_name TEXT NOT NULL, model TEXT NOT NULL,
              product_no TEXT, production_unit TEXT, unit TEXT DEFAULT '件',
              condition TEXT NOT NULL, condition_note TEXT,
              storage_area TEXT NOT NULL, status TEXT NOT NULL,
              current_location TEXT NOT NULL, current_holder TEXT,
              received_by TEXT NOT NULL, received_at TEXT NOT NULL,
              is_deleted INTEGER DEFAULT 0, deleted_by TEXT,
              deleted_at TEXT, delete_reason TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sample_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, sample_no TEXT NOT NULL,
              actor TEXT NOT NULL, action TEXT NOT NULL,
              from_status TEXT, to_status TEXT,
              from_location TEXT, to_location TEXT,
              details TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks(
              task_no TEXT PRIMARY KEY, commission_test_id INTEGER NOT NULL,
              commission_no TEXT NOT NULL, experiment TEXT NOT NULL,
              standard TEXT, assignee TEXT NOT NULL, reviewer TEXT NOT NULL,
              status TEXT NOT NULL, assigned_by TEXT NOT NULL,
              assigned_at TEXT NOT NULL, notified_at TEXT NOT NULL,
              accepted_at TEXT, detection_location TEXT,
              acceptance_result TEXT, acceptance_note TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_samples(
              task_no TEXT NOT NULL, sample_no TEXT NOT NULL,
              PRIMARY KEY(task_no, sample_no)
            );
            CREATE TABLE IF NOT EXISTS sample_loans(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_no TEXT NOT NULL, sample_no TEXT NOT NULL,
              borrower TEXT NOT NULL, borrowed_at TEXT NOT NULL,
              purpose TEXT NOT NULL, detection_location TEXT NOT NULL,
              issue_condition TEXT, issue_note TEXT,
              returned_at TEXT, returned_by TEXT,
              return_condition TEXT, return_note TEXT,
              return_status TEXT DEFAULT '未归还',
              confirmed_by TEXT, confirmed_at TEXT,
              confirmed_location TEXT,
              UNIQUE(task_no, sample_no)
            );
            CREATE TABLE IF NOT EXISTS records(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              record_no TEXT NOT NULL, task_no TEXT NOT NULL,
              version INTEGER NOT NULL, experiment TEXT NOT NULL,
              owner TEXT NOT NULL, status TEXT NOT NULL,
              payload TEXT NOT NULL, template_version TEXT,
              sop_version TEXT, change_reason TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(record_no, version)
            );
            CREATE TABLE IF NOT EXISTS reviews(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              record_no TEXT NOT NULL, version INTEGER NOT NULL,
              reviewer TEXT NOT NULL, decision TEXT NOT NULL,
              comment TEXT, reviewed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_logs(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              object_type TEXT NOT NULL, object_no TEXT NOT NULL,
              version INTEGER, actor TEXT NOT NULL, action TEXT NOT NULL,
              field_name TEXT, old_value TEXT, new_value TEXT,
              reason TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports(
              report_no TEXT PRIMARY KEY, commission_no TEXT UNIQUE NOT NULL,
              status TEXT NOT NULL, tester TEXT, verifier TEXT, approver TEXT,
              report_category TEXT DEFAULT '委托检验',
              sample_statement TEXT, conclusion TEXT, notes TEXT,
              tester_signed_at TEXT, verifier_signed_at TEXT,
              approver_signed_at TEXT, publish_date TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS report_actions(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              report_no TEXT NOT NULL, actor TEXT NOT NULL,
              action TEXT NOT NULL, comment TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signatures(
              username TEXT PRIMARY KEY, source_file TEXT NOT NULL,
              image_file TEXT, uploaded_by TEXT NOT NULL,
              uploaded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS template_versions(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              experiment TEXT NOT NULL, doc_type TEXT NOT NULL,
              file_name TEXT NOT NULL, version TEXT NOT NULL,
              effective_date TEXT NOT NULL, status TEXT NOT NULL,
              uploader TEXT NOT NULL, uploaded_at TEXT NOT NULL,
              change_note TEXT,
              UNIQUE(experiment, doc_type, version)
            );
            """
        )
        users = [
            ("admin", "系统管理员", "admin123", "管理员"),
            ("receiver", "收样员王工", "receive123", "收样员"),
            ("tester", "实验员张工", "test123", "实验人员"),
            ("reviewer", "复核员李工", "review123", "复核实验员"),
            ("store", "样品管理员赵工", "store123", "样品管理员"),
            ("approver", "批准人刘工", "approve123", "批准人"),
        ]
        c.executemany(
            "INSERT OR IGNORE INTO users VALUES(?,?,?,?,1,?)",
            [(u, n, _phash(p), r, now()) for u, n, p, r in users],
        )
        c.execute(
            """INSERT OR IGNORE INTO customers(
              customer_code,name,short_name,address,contact,phone,notes,
              enabled,created_at,updated_at)
              VALUES('C-DEFAULT','默认客户','默认客户','','','','入库默认预设',1,?,?)""",
            (now(), now()),
        )
        c.execute(
            """INSERT OR IGNORE INTO sample_catalog(
              sample_code,name,model,production_unit,category,unit,
              default_experiments,notes,enabled,created_at,updated_at)
              VALUES('S-DEFAULT','默认样品','默认规格','','未分类','件','[]',
              '入库默认预设',1,?,?)""",
            (now(), now()),
        )


# ---------- Authentication ----------
def authenticate(username: str, password: str) -> dict[str, Any] | None:
    return _one(
        "SELECT username,display_name,role FROM users WHERE username=? AND password_hash=? AND enabled=1",
        (username.strip(), _phash(password)),
    )


def create_session(username: str, days: int = 7) -> str:
    token = secrets.token_urlsafe(28)
    with connect() as c:
        c.execute(
            "INSERT INTO auth_sessions VALUES(?,?,?,?)",
            (token, username, (china_now() + timedelta(days=days)).isoformat(timespec="seconds"), now()),
        )
    return token


def session_user(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    return _one(
        """SELECT u.username,u.display_name,u.role
           FROM auth_sessions s JOIN users u ON u.username=s.username
           WHERE s.token=? AND s.expires_at>? AND u.enabled=1""",
        (token, now()),
    )


def delete_session(token: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM auth_sessions WHERE token=?", (token,))


# ---------- Master data ----------
def users() -> list[dict[str, Any]]:
    return _rows("SELECT username,display_name,role,enabled,created_at FROM users ORDER BY role,display_name")


def add_user(username: str, display_name: str, password: str, role: str) -> None:
    if not username.strip() or not display_name.strip() or not password:
        raise ValueError("用户名、姓名和密码不能为空")
    with connect() as c:
        c.execute(
            "INSERT INTO users VALUES(?,?,?,?,1,?)",
            (username.strip(), display_name.strip(), _phash(password), role, now()),
        )


def list_customers(include_disabled: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM customers"
    if not include_disabled:
        q += " WHERE enabled=1"
    return _rows(q + " ORDER BY name")


def add_customer(code: str, name: str, short_name: str = "", address: str = "", contact: str = "", phone: str = "", notes: str = "") -> None:
    if not name.strip():
        raise ValueError("客户名称不能为空")
    with connect() as c:
        c.execute(
            """INSERT INTO customers(customer_code,name,short_name,address,contact,phone,notes,
               enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)""",
            (code.strip() or None, name.strip(), short_name.strip(), address.strip(), contact.strip(), phone.strip(), notes.strip(), now(), now()),
        )


def set_customer_enabled(customer_id: int, enabled: bool) -> None:
    with connect() as c:
        c.execute("UPDATE customers SET enabled=?,updated_at=? WHERE id=?", (1 if enabled else 0, now(), customer_id))


def list_sample_catalog(include_disabled: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM sample_catalog"
    if not include_disabled:
        q += " WHERE enabled=1"
    rows = _rows(q + " ORDER BY name,model")
    for r in rows:
        try:
            r["default_experiments_list"] = json.loads(r.get("default_experiments") or "[]")
        except json.JSONDecodeError:
            r["default_experiments_list"] = []
    return rows


def add_sample_catalog(code: str, name: str, model: str, production_unit: str = "", category: str = "", unit: str = "件", default_experiments: list[str] | None = None, notes: str = "") -> None:
    if not name.strip() or not model.strip():
        raise ValueError("样品名称和规格型号不能为空")
    with connect() as c:
        c.execute(
            """INSERT INTO sample_catalog(sample_code,name,model,production_unit,category,unit,
               default_experiments,notes,enabled,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
            (code.strip() or None, name.strip(), model.strip(), production_unit.strip(), category.strip(), unit.strip() or "件", json.dumps(default_experiments or [], ensure_ascii=False), notes.strip(), now(), now()),
        )


def set_sample_catalog_enabled(catalog_id: int, enabled: bool) -> None:
    with connect() as c:
        c.execute("UPDATE sample_catalog SET enabled=?,updated_at=? WHERE id=?", (1 if enabled else 0, now(), catalog_id))


# ---------- Numbering (temporary rules; can be replaced later) ----------
def _next_daily(prefix: str, table: str, column: str) -> str:
    stem = f"{prefix}{china_now().strftime('%Y%m%d')}"
    values = _rows(f"SELECT {column} value FROM {table} WHERE {column} LIKE ?", (stem + "%",))
    seqs: list[int] = []
    for r in values:
        m = re.match(re.escape(stem) + r"(\d{3})", str(r["value"]))
        if m:
            seqs.append(int(m.group(1)))
    return f"{stem}{max(seqs or [0]) + 1:03d}"


def next_commission_no() -> str:
    return _next_daily("WT", "commissions", "commission_no")


def next_sample_base() -> str:
    return _next_daily("BP", "samples", "base_no")


def normalize_sample_no(value: str) -> str:
    return value.strip().upper().replace(" ", "")


def validate_sample_base(value: str) -> bool:
    return bool(re.fullmatch(r"BP\d{11}(?:[A-Z0-9]*)?", normalize_sample_no(value)))


# ---------- Commission and intake ----------
def create_commission_and_samples(data: dict[str, Any], experiments: list[str], actor: str) -> list[str]:
    commission_no = data["commission_no"].strip().upper().replace(" ", "")
    base_no = normalize_sample_no(data["base_no"])
    qty = int(data["qty"])
    if qty < 1:
        raise ValueError("接收数量至少为1")
    sample_nos = [base_no] if qty == 1 else [f"{base_no}-{i}" for i in range(1, qty + 1)]
    if not experiments:
        raise ValueError("至少选择一个检测项目")
    with connect() as c:
        if c.execute("SELECT 1 FROM commissions WHERE commission_no=?", (commission_no,)).fetchone():
            raise ValueError("检验委托单编号已存在")
        dup = c.execute(
            f"SELECT sample_no FROM samples WHERE sample_no IN ({','.join('?' for _ in sample_nos)})",
            sample_nos,
        ).fetchall()
        if dup:
            raise ValueError(f"样品编号已存在：{dup[0][0]}")
        ts = now()
        c.execute(
            """INSERT INTO commissions(
               commission_no,customer_id,customer_name,customer_address,contact,phone,
               commission_date,due_date,sample_condition,condition_note,
               subcontract_allowed,confidentiality,report_medium,conformity_judgment,
               uncertainty,delivery_method,cnas_mark,capability,notes,status,
               created_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'已入库',?,?,?)""",
            (
                commission_no, data["customer_id"], data["customer_name"], data.get("customer_address", ""),
                data.get("contact", ""), data.get("phone", ""), str(data["commission_date"]), str(data["due_date"]),
                data["condition"], data.get("condition_note", ""), data["subcontract_allowed"],
                data["confidentiality"], data["report_medium"], data["conformity_judgment"],
                data["uncertainty"], data["delivery_method"], data["cnas_mark"], data["capability"],
                data.get("notes", ""), actor, ts, ts,
            ),
        )
        for exp in experiments:
            c.execute(
                """INSERT INTO commission_tests(commission_no,experiment,standard,status,created_at,updated_at)
                   VALUES(?,?,?,'待分配',?,?)""",
                (commission_no, exp, EXPERIMENTS[exp]["std"], ts, ts),
            )
        for sample_no in sample_nos:
            c.execute(
                """INSERT INTO samples(
                   sample_no,base_no,commission_no,sample_catalog_id,sample_name,model,
                   product_no,production_unit,unit,condition,condition_note,storage_area,
                   status,current_location,current_holder,received_by,received_at,
                   created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'待分配',?,?,?, ?,?,?)""",
                (
                    sample_no, base_no, commission_no, data["sample_catalog_id"], data["sample_name"], data["model"],
                    data.get("product_no", ""), data.get("production_unit", ""), data.get("unit", "件"),
                    data["condition"], data.get("condition_note", ""), data["storage_area"],
                    data["storage_area"], actor, actor, ts, ts, ts,
                ),
            )
            c.execute(
                """INSERT INTO sample_events(sample_no,actor,action,from_status,to_status,
                   from_location,to_location,details,created_at)
                   VALUES(?,?,?,'','待分配','',?,?,?)""",
                (sample_no, actor, "样品接收并入库", data["storage_area"], f"委托单：{commission_no}；状态：{data['condition']}；{data.get('condition_note','')}", ts),
            )
    return sample_nos


def list_commissions() -> list[dict[str, Any]]:
    return _rows("SELECT * FROM commissions ORDER BY created_at DESC")


def commission(commission_no: str) -> dict[str, Any] | None:
    return _one("SELECT * FROM commissions WHERE commission_no=?", (commission_no,))


def commission_tests(commission_no: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM commission_tests WHERE commission_no=? ORDER BY id", (commission_no,))


def commission_samples(commission_no: str, include_deleted: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM samples WHERE commission_no=?"
    args: list[Any] = [commission_no]
    if not include_deleted:
        q += " AND is_deleted=0"
    return _rows(q + " ORDER BY sample_no", args)


def list_samples(include_deleted: bool = False) -> list[dict[str, Any]]:
    return _rows(
        "SELECT * FROM samples WHERE is_deleted=? ORDER BY updated_at DESC",
        (1 if include_deleted else 0,),
    )


def sample(sample_no: str) -> dict[str, Any] | None:
    return _one("SELECT * FROM samples WHERE sample_no=?", (sample_no,))


def sample_events(sample_no: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM sample_events WHERE sample_no=? ORDER BY id", (sample_no,))


def _event(c: sqlite3.Connection, sample_no: str, actor: str, action: str, from_status: str, to_status: str, from_location: str, to_location: str, details: str = "") -> None:
    c.execute(
        """INSERT INTO sample_events(sample_no,actor,action,from_status,to_status,
           from_location,to_location,details,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
        (sample_no, actor, action, from_status, to_status, from_location, to_location, details, now()),
    )


# ---------- Task assignment, notification and acceptance ----------
def pending_test_items() -> list[dict[str, Any]]:
    return _rows(
        """SELECT ct.*,c.customer_name,c.due_date
           FROM commission_tests ct JOIN commissions c ON c.commission_no=ct.commission_no
           WHERE ct.status='待分配' ORDER BY c.created_at,ct.id"""
    )


def _next_task_no(c: sqlite3.Connection, commission_no: str) -> str:
    rows = c.execute("SELECT task_no FROM tasks WHERE commission_no=?", (commission_no,)).fetchall()
    seqs = []
    for r in rows:
        m = re.search(r"-T(\d+)$", r[0])
        if m:
            seqs.append(int(m.group(1)))
    return f"{commission_no}-T{max(seqs or [0]) + 1:02d}"


def assign_test_item(test_item_id: int, sample_nos: list[str], assignee: str, reviewer: str, actor: str) -> str:
    if not sample_nos:
        raise ValueError("至少选择一个样品")
    with connect() as c:
        item = c.execute("SELECT * FROM commission_tests WHERE id=?", (test_item_id,)).fetchone()
        if not item or item["status"] != "待分配":
            raise ValueError("该检测项目已分配或不存在")
        for sn in sample_nos:
            s = c.execute("SELECT * FROM samples WHERE sample_no=? AND is_deleted=0", (sn,)).fetchone()
            if not s or s["commission_no"] != item["commission_no"]:
                raise ValueError(f"样品{sn}不属于本委托单")
            active = c.execute(
                """SELECT 1 FROM task_samples ts JOIN tasks t ON t.task_no=ts.task_no
                   WHERE ts.sample_no=? AND t.status IN('待接收','检测中','待复核','接收异常')""",
                (sn,),
            ).fetchone()
            if active:
                raise ValueError(f"样品{sn}当前已有未结束任务")
        task_no = _next_task_no(c, item["commission_no"])
        ts_now = now()
        c.execute(
            """INSERT INTO tasks(task_no,commission_test_id,commission_no,experiment,standard,
               assignee,reviewer,status,assigned_by,assigned_at,notified_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,'待接收',?,?,?,?,?)""",
            (task_no, test_item_id, item["commission_no"], item["experiment"], item["standard"], assignee, reviewer, actor, ts_now, ts_now, ts_now, ts_now),
        )
        c.executemany("INSERT INTO task_samples(task_no,sample_no) VALUES(?,?)", [(task_no, sn) for sn in sample_nos])
        c.execute("UPDATE commission_tests SET status='已分配',task_no=?,updated_at=? WHERE id=?", (task_no, ts_now, test_item_id))
        for sn in sample_nos:
            s = c.execute("SELECT * FROM samples WHERE sample_no=?", (sn,)).fetchone()
            c.execute("UPDATE samples SET status='等待实验员接收',current_holder=?,updated_at=? WHERE sample_no=?", (assignee, ts_now, sn))
            _event(c, sn, actor, "检测任务下发", s["status"], "等待实验员接收", s["current_location"], s["current_location"], f"任务：{task_no}；实验员：{assignee}；提醒时间：{ts_now}")
    return task_no


def task(task_no: str) -> dict[str, Any] | None:
    r = _one("SELECT * FROM tasks WHERE task_no=?", (task_no,))
    if r:
        r["sample_nos"] = [x["sample_no"] for x in _rows("SELECT sample_no FROM task_samples WHERE task_no=? ORDER BY sample_no", (task_no,))]
    return r


def list_tasks(statuses: list[str] | None = None, assignee: str | None = None, reviewer: str | None = None) -> list[dict[str, Any]]:
    q = """SELECT t.*,GROUP_CONCAT(ts.sample_no,'、') sample_nos
           FROM tasks t JOIN task_samples ts ON ts.task_no=t.task_no WHERE 1=1"""
    args: list[Any] = []
    if statuses:
        q += " AND t.status IN (" + ",".join("?" for _ in statuses) + ")"
        args.extend(statuses)
    if assignee is not None:
        q += " AND t.assignee=?"
        args.append(assignee)
    if reviewer is not None:
        q += " AND t.reviewer=?"
        args.append(reviewer)
    q += " GROUP BY t.task_no ORDER BY t.updated_at DESC"
    return _rows(q, args)


def pending_task_count(assignee: str) -> int:
    r = _one("SELECT COUNT(*) n FROM tasks WHERE assignee=? AND status='待接收'", (assignee,))
    return int(r["n"] if r else 0)


def accept_task(task_no: str, actor: str, result: str, detection_location: str, note: str = "") -> None:
    with connect() as c:
        t = c.execute("SELECT * FROM tasks WHERE task_no=?", (task_no,)).fetchone()
        if not t or t["assignee"] != actor:
            raise ValueError("任务不存在或不属于当前实验员")
        samples = c.execute(
            """SELECT s.* FROM samples s JOIN task_samples ts ON ts.sample_no=s.sample_no
               WHERE ts.task_no=? ORDER BY s.sample_no""",
            (task_no,),
        ).fetchall()
        ts_now = now()
        if result == "尚未收到样品":
            c.execute("UPDATE tasks SET acceptance_result=?,acceptance_note=?,updated_at=? WHERE task_no=?", (result, note, ts_now, task_no))
            for s in samples:
                _event(c, s["sample_no"], actor, "任务接收反馈", s["status"], s["status"], s["current_location"], s["current_location"], result + (f"；{note}" if note else ""))
            return
        status = "检测中" if result == "样品已收到，确认完好" else "接收异常"
        c.execute(
            """UPDATE tasks SET status=?,accepted_at=?,detection_location=?,
               acceptance_result=?,acceptance_note=?,updated_at=? WHERE task_no=?""",
            (status, ts_now, detection_location, result, note, ts_now, task_no),
        )
        for s in samples:
            c.execute(
                "UPDATE samples SET status=?,current_location=?,current_holder=?,updated_at=? WHERE sample_no=?",
                (status, detection_location, actor, ts_now, s["sample_no"]),
            )
            _event(c, s["sample_no"], actor, "实验员领用样品", s["status"], status, s["current_location"], detection_location, f"任务：{task_no}；{result}；{note}")
            if status == "检测中":
                c.execute(
                    """INSERT OR REPLACE INTO sample_loans(
                       task_no,sample_no,borrower,borrowed_at,purpose,detection_location,
                       issue_condition,issue_note,return_status)
                       VALUES(?,?,?,?,?,?,?,?,'未归还')""",
                    (task_no, s["sample_no"], actor, ts_now, t["experiment"], detection_location, s["condition"], note),
                )


# ---------- Controlled records and review ----------
def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = value
    return out


def latest_record_by_task(task_no: str) -> dict[str, Any] | None:
    r = _one("SELECT * FROM records WHERE task_no=? ORDER BY version DESC LIMIT 1", (task_no,))
    if r:
        r["payload"] = json.loads(r["payload"])
    return r


def record(record_no: str, version: int) -> dict[str, Any] | None:
    r = _one("SELECT * FROM records WHERE record_no=? AND version=?", (record_no, version))
    if r:
        r["payload"] = json.loads(r["payload"])
    return r


def record_versions(record_no: str) -> list[dict[str, Any]]:
    rows = _rows("SELECT * FROM records WHERE record_no=? ORDER BY version", (record_no,))
    for r in rows:
        r["payload"] = json.loads(r["payload"])
    return rows


def latest_records(statuses: list[str] | None = None, owner: str | None = None) -> list[dict[str, Any]]:
    q = """SELECT r.* FROM records r WHERE r.version=(
           SELECT MAX(x.version) FROM records x WHERE x.record_no=r.record_no)"""
    args: list[Any] = []
    if statuses:
        q += " AND r.status IN (" + ",".join("?" for _ in statuses) + ")"
        args.extend(statuses)
    if owner:
        q += " AND r.owner=?"
        args.append(owner)
    rows = _rows(q + " ORDER BY r.updated_at DESC", args)
    for r in rows:
        r["payload"] = json.loads(r["payload"])
    return rows


def save_record(task_no: str, version: int, payload: dict[str, Any], owner: str, status: str, template_version: str, sop_version: str, reason: str = "", compare_payload: dict[str, Any] | None = None) -> None:
    t = task(task_no)
    if not t:
        raise ValueError("任务不存在")
    ts_now = now()
    with connect() as c:
        c.execute(
            """INSERT INTO records(record_no,task_no,version,experiment,owner,status,payload,
               template_version,sop_version,change_reason,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(record_no,version) DO UPDATE SET owner=excluded.owner,
               status=excluded.status,payload=excluded.payload,template_version=excluded.template_version,
               sop_version=excluded.sop_version,change_reason=excluded.change_reason,updated_at=excluded.updated_at""",
            (task_no, task_no, version, t["experiment"], owner, status, json.dumps(payload, ensure_ascii=False, default=str), template_version, sop_version, reason, ts_now, ts_now),
        )
        old = _flatten(compare_payload or {})
        new = _flatten(payload)
        for field in sorted(set(old) | set(new)):
            ov, nv = old.get(field, ""), new.get(field, "")
            if str(ov) != str(nv):
                c.execute(
                    """INSERT INTO audit_logs(object_type,object_no,version,actor,action,
                       field_name,old_value,new_value,reason,created_at)
                       VALUES('原始记录',?,?,?,?,?,?,?,?,?)""",
                    (task_no, version, owner, "字段修改", field, str(ov), str(nv), reason, ts_now),
                )
        c.execute(
            """INSERT INTO audit_logs(object_type,object_no,version,actor,action,reason,created_at)
               VALUES('原始记录',?,?,?,?,?,?)""",
            (task_no, version, owner, "提交复核" if status in ("待复核", "更正待复核") else "保存草稿", reason, ts_now),
        )
        if status in ("待复核", "更正待复核"):
            c.execute("UPDATE tasks SET status='待复核',updated_at=? WHERE task_no=?", (ts_now, task_no))
            for sn in t["sample_nos"]:
                s = c.execute("SELECT * FROM samples WHERE sample_no=?", (sn,)).fetchone()
                _event(c, sn, owner, "原始记录提交复核", s["status"], "待复核", s["current_location"], s["current_location"], f"任务/记录编号：{task_no} V{version}")


def pending_reviews(reviewer: str | None = None) -> list[dict[str, Any]]:
    q = """SELECT r.*,t.commission_no,t.experiment,t.reviewer,
           GROUP_CONCAT(ts.sample_no,'、') sample_nos
           FROM records r JOIN tasks t ON t.task_no=r.task_no
           JOIN task_samples ts ON ts.task_no=t.task_no
           WHERE r.status IN('待复核','更正待复核')"""
    args: list[Any] = []
    if reviewer:
        q += " AND t.reviewer=?"
        args.append(reviewer)
    q += " GROUP BY r.record_no,r.version ORDER BY r.updated_at DESC"
    rows = _rows(q, args)
    for r in rows:
        r["payload"] = json.loads(r["payload"])
    return rows


def review_record(record_no: str, version: int, reviewer: str, decision: str, comment: str) -> None:
    rec = record(record_no, version)
    t = task(record_no)
    if not rec or not t:
        raise ValueError("记录不存在")
    ts_now = now()
    with connect() as c:
        new_status = "已锁定" if decision == "通过" else "退回修改"
        c.execute("UPDATE records SET status=?,updated_at=? WHERE record_no=? AND version=?", (new_status, ts_now, record_no, version))
        c.execute("INSERT INTO reviews(record_no,version,reviewer,decision,comment,reviewed_at) VALUES(?,?,?,?,?,?)", (record_no, version, reviewer, decision, comment, ts_now))
        c.execute("INSERT INTO audit_logs(object_type,object_no,version,actor,action,reason,created_at) VALUES('原始记录',?,?,?,?,?,?)", (record_no, version, reviewer, "复核" + decision, comment, ts_now))
        c.execute("UPDATE tasks SET status=?,updated_at=? WHERE task_no=?", ("已完成" if decision == "通过" else "退回修改", ts_now, record_no))
        if decision == "通过":
            c.execute("UPDATE commission_tests SET status='已完成',updated_at=? WHERE id=?", (ts_now, t["commission_test_id"]))
        for sn in t["sample_nos"]:
            s = c.execute("SELECT * FROM samples WHERE sample_no=?", (sn,)).fetchone()
            target = "待归还" if decision == "通过" else "退回修改"
            c.execute("UPDATE samples SET status=?,updated_at=? WHERE sample_no=?", (target, ts_now, sn))
            _event(c, sn, reviewer, "原始记录复核" + decision, s["status"], target, s["current_location"], s["current_location"], f"任务/记录编号：{record_no} V{version}；{comment}")
    if decision == "通过":
        ensure_report(record_no)


def ensure_report(task_no: str) -> None:
    t = task(task_no)
    if not t:
        return
    remaining = _one("SELECT COUNT(*) n FROM commission_tests WHERE commission_no=? AND status!='已完成'", (t["commission_no"],))
    if remaining and int(remaining["n"]) == 0:
        first = _one("SELECT assignee,reviewer FROM tasks WHERE commission_no=? ORDER BY created_at LIMIT 1", (t["commission_no"],)) or {}
        ts_now = now()
        with connect() as c:
            c.execute(
                """INSERT OR IGNORE INTO reports(report_no,commission_no,status,tester,verifier,approver,
                   created_at,updated_at) VALUES(?,?,'待检测员确认',?,?, 'approver',?,?)""",
                (t["commission_no"], t["commission_no"], first.get("assignee"), first.get("reviewer"), ts_now, ts_now),
            )
            c.execute("UPDATE commissions SET status='报告编制中',updated_at=? WHERE commission_no=?", (ts_now, t["commission_no"]))


def audit_logs(object_no: str, version: int | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM audit_logs WHERE object_no=?"
    args: list[Any] = [object_no]
    if version is not None:
        q += " AND version=?"
        args.append(version)
    return _rows(q + " ORDER BY id", args)


def create_revision(record_no: str, actor: str, reason: str) -> int:
    if not reason.strip():
        raise ValueError("修改原因不能为空")
    versions = record_versions(record_no)
    if not versions or versions[-1]["status"] != "已锁定":
        raise ValueError("仅已锁定记录可以创建修改版")
    base = versions[-1]
    new_version = base["version"] + 1
    save_record(record_no, new_version, base["payload"], actor, "草稿", base.get("template_version") or "A/0", base.get("sop_version") or "A/0", reason, base["payload"])
    with connect() as c:
        c.execute("UPDATE tasks SET status='退回修改',updated_at=? WHERE task_no=?", (now(), record_no))
    return new_version


# ---------- Return and storage ----------
def return_candidates(user: str) -> list[dict[str, Any]]:
    return _rows(
        """SELECT l.task_no,t.experiment,t.commission_no,l.borrower,l.borrowed_at,
           GROUP_CONCAT(l.sample_no,'、') sample_nos
           FROM sample_loans l JOIN tasks t ON t.task_no=l.task_no
           WHERE l.borrower=? AND t.status='已完成' AND l.return_status='未归还'
           GROUP BY l.task_no ORDER BY l.borrowed_at""",
        (user,),
    )


def task_loan_rows(task_no: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM sample_loans WHERE task_no=? ORDER BY sample_no", (task_no,))


def submit_return(task_no: str, actor: str, details: list[dict[str, str]]) -> None:
    ts_now = now()
    with connect() as c:
        for d in details:
            loan = c.execute("SELECT * FROM sample_loans WHERE task_no=? AND sample_no=?", (task_no, d["sample_no"])).fetchone()
            if not loan or loan["borrower"] != actor:
                raise ValueError("归还记录不存在或不属于当前实验员")
            c.execute(
                """UPDATE sample_loans SET returned_at=?,returned_by=?,return_condition=?,
                   return_note=?,return_status='待回库确认' WHERE task_no=? AND sample_no=?""",
                (ts_now, actor, d["condition"], d.get("note", ""), task_no, d["sample_no"]),
            )
            s = c.execute("SELECT * FROM samples WHERE sample_no=?", (d["sample_no"],)).fetchone()
            c.execute("UPDATE samples SET status='待回库确认',current_location='回库交接区',current_holder='',updated_at=? WHERE sample_no=?", (ts_now, d["sample_no"]))
            _event(c, d["sample_no"], actor, "实验员提交样品归还", s["status"], "待回库确认", s["current_location"], "回库交接区", f"任务：{task_no}；状态：{d['condition']}；{d.get('note','')}")


def pending_return_tasks() -> list[dict[str, Any]]:
    return _rows(
        """SELECT l.task_no,t.experiment,t.commission_no,l.returned_by,l.returned_at,
           GROUP_CONCAT(l.sample_no,'、') sample_nos
           FROM sample_loans l JOIN tasks t ON t.task_no=l.task_no
           WHERE l.return_status='待回库确认'
           GROUP BY l.task_no ORDER BY l.returned_at"""
    )


def confirm_return(task_no: str, actor: str, details: list[dict[str, str]]) -> None:
    ts_now = now()
    with connect() as c:
        for d in details:
            loan = c.execute("SELECT * FROM sample_loans WHERE task_no=? AND sample_no=?", (task_no, d["sample_no"])).fetchone()
            if not loan or loan["return_status"] != "待回库确认":
                raise ValueError("该样品不在待回库状态")
            consumed = loan["return_condition"] == "全部消耗"
            location = "无实物（全部消耗）" if consumed else d["location"]
            status = "全部消耗，记录归档" if consumed else "留样保存"
            c.execute(
                """UPDATE sample_loans SET return_status='已回库',confirmed_by=?,confirmed_at=?,
                   confirmed_location=? WHERE task_no=? AND sample_no=?""",
                (actor, ts_now, location, task_no, d["sample_no"]),
            )
            s = c.execute("SELECT * FROM samples WHERE sample_no=?", (d["sample_no"],)).fetchone()
            c.execute("UPDATE samples SET status=?,current_location=?,current_holder=?,updated_at=? WHERE sample_no=?", (status, location, actor, ts_now, d["sample_no"]))
            _event(c, d["sample_no"], actor, "样品回库确认", s["status"], status, s["current_location"], location, f"任务：{task_no}")


# ---------- Soft deletion ----------
def can_delete_sample(sample_no: str) -> tuple[bool, str]:
    active = _one(
        """SELECT COUNT(*) n FROM task_samples ts JOIN tasks t ON t.task_no=ts.task_no
           WHERE ts.sample_no=? AND t.status NOT IN('待接收')""",
        (sample_no,),
    )
    if active and int(active["n"]) > 0:
        return False, "样品已被实验员接收或已产生检测记录，不能删除"
    return True, ""


def soft_delete_sample(sample_no: str, actor: str, reason: str) -> None:
    if not reason.strip():
        raise ValueError("删除原因不能为空")
    ok, msg = can_delete_sample(sample_no)
    if not ok:
        raise ValueError(msg)
    s = sample(sample_no)
    if not s:
        raise ValueError("样品不存在")
    ts_now = now()
    with connect() as c:
        tasks_for_sample = c.execute("SELECT task_no FROM task_samples WHERE sample_no=?", (sample_no,)).fetchall()
        for tr in tasks_for_sample:
            t = c.execute("SELECT * FROM tasks WHERE task_no=?", (tr[0],)).fetchone()
            if t and t["status"] == "待接收":
                c.execute("DELETE FROM task_samples WHERE task_no=? AND sample_no=?", (tr[0], sample_no))
                left = c.execute("SELECT COUNT(*) FROM task_samples WHERE task_no=?", (tr[0],)).fetchone()[0]
                if left == 0:
                    c.execute("UPDATE commission_tests SET status='待分配',task_no=NULL,updated_at=? WHERE id=?", (ts_now, t["commission_test_id"]))
                    c.execute("DELETE FROM tasks WHERE task_no=?", (tr[0],))
        c.execute("UPDATE samples SET is_deleted=1,deleted_by=?,deleted_at=?,delete_reason=?,updated_at=? WHERE sample_no=?", (actor, ts_now, reason, ts_now, sample_no))
        _event(c, sample_no, actor, "删除错误入库记录", s["status"], "已删除", s["current_location"], s["current_location"], reason)


# ---------- Templates ----------
def seed_template(experiment: str, doc_type: str, file_name: str | None, version: str = "A/0") -> None:
    if not file_name:
        return
    with connect() as c:
        c.execute(
            """INSERT OR IGNORE INTO template_versions(experiment,doc_type,file_name,version,
               effective_date,status,uploader,uploaded_at,change_note)
               VALUES(?,?,?,?,?,'现行','system',?,'系统初始化')""",
            (experiment, doc_type, file_name, version, str(china_today()), now()),
        )


def active_version(experiment: str, doc_type: str) -> dict[str, Any] | None:
    return _one(
        """SELECT * FROM template_versions WHERE experiment=? AND doc_type=? AND status='现行'
           ORDER BY id DESC LIMIT 1""",
        (experiment, doc_type),
    )


def all_template_versions() -> list[dict[str, Any]]:
    return _rows("SELECT * FROM template_versions ORDER BY experiment,doc_type,id DESC")


def add_template(experiment: str, doc_type: str, file_name: str, version: str, effective_date: str, uploader: str, note: str) -> None:
    with connect() as c:
        c.execute("UPDATE template_versions SET status='停用' WHERE experiment=? AND doc_type=? AND status='现行'", (experiment, doc_type))
        c.execute(
            """INSERT INTO template_versions(experiment,doc_type,file_name,version,effective_date,
               status,uploader,uploaded_at,change_note) VALUES(?,?,?,?,?,'现行',?,?,?)""",
            (experiment, doc_type, file_name, version, effective_date, uploader, now(), note),
        )


# ---------- Reports and signatures ----------
def report(report_no: str) -> dict[str, Any] | None:
    return _one("SELECT * FROM reports WHERE report_no=?", (report_no,))


def list_reports(role: str, username: str) -> list[dict[str, Any]]:
    if role == "实验人员":
        return _rows("SELECT * FROM reports WHERE tester=? ORDER BY updated_at DESC", (username,))
    if role == "复核实验员":
        return _rows("SELECT * FROM reports WHERE verifier=? ORDER BY updated_at DESC", (username,))
    if role == "批准人":
        return _rows("SELECT * FROM reports WHERE approver=? ORDER BY updated_at DESC", (username,))
    return _rows("SELECT * FROM reports ORDER BY updated_at DESC")


def update_report_roles(report_no: str, tester: str, verifier: str, approver: str, actor: str) -> None:
    with connect() as c:
        c.execute("UPDATE reports SET tester=?,verifier=?,approver=?,updated_at=? WHERE report_no=?", (tester, verifier, approver, now(), report_no))
        c.execute("INSERT INTO report_actions(report_no,actor,action,created_at) VALUES(?,?,?,?)", (report_no, actor, "调整报告签署人员", now()))


def tester_submit_report(report_no: str, actor: str, report_category: str, sample_statement: str, conclusion: str, notes: str) -> None:
    r = report(report_no)
    if not r or r["tester"] != actor or r["status"] != "待检测员确认":
        raise ValueError("报告不属于当前检测员或状态不允许提交")
    ts_now = now()
    with connect() as c:
        c.execute(
            """UPDATE reports SET status='待核验',report_category=?,sample_statement=?,conclusion=?,
               notes=?,tester_signed_at=?,updated_at=? WHERE report_no=?""",
            (report_category, sample_statement, conclusion, notes, ts_now, ts_now, report_no),
        )
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,?,?)", (report_no, actor, "检测员确认并签署", notes, ts_now))


def verifier_review_report(report_no: str, actor: str, decision: str, comment: str) -> None:
    r = report(report_no)
    if not r or r["verifier"] != actor or r["status"] != "待核验":
        raise ValueError("报告不属于当前核验员或状态不允许核验")
    ts_now = now()
    status = "待批准" if decision == "通过" else "待检测员确认"
    with connect() as c:
        c.execute("UPDATE reports SET status=?,tester_signed_at=?,verifier_signed_at=?,approver_signed_at=NULL,updated_at=? WHERE report_no=?", (status, r.get('tester_signed_at') if decision == '通过' else None, ts_now if decision == '通过' else None, ts_now, report_no))
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,?,?)", (report_no, actor, "报告核验" + decision, comment, ts_now))


def approver_review_report(report_no: str, actor: str, decision: str, comment: str) -> None:
    r = report(report_no)
    if not r or r["approver"] != actor or r["status"] != "待批准":
        raise ValueError("报告不属于当前批准人或状态不允许批准")
    ts_now = now()
    status = "已发布" if decision == "批准" else "待检测员确认"
    with connect() as c:
        if decision == "批准":
            c.execute(
                """UPDATE reports SET status='已发布',approver_signed_at=?,publish_date=?,updated_at=?
                   WHERE report_no=?""",
                (ts_now, str(china_today()), ts_now, report_no),
            )
        else:
            c.execute(
                """UPDATE reports SET status='待检测员确认',tester_signed_at=NULL,
                   verifier_signed_at=NULL,approver_signed_at=NULL,publish_date=NULL,updated_at=?
                   WHERE report_no=?""",
                (ts_now, report_no),
            )
        c.execute("UPDATE commissions SET status=?,updated_at=? WHERE commission_no=?", ("报告已发布" if decision == "批准" else "报告编制中", ts_now, r["commission_no"]))
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,?,?)", (report_no, actor, "报告" + decision, comment, ts_now))


def report_actions(report_no: str) -> list[dict[str, Any]]:
    return _rows("SELECT * FROM report_actions WHERE report_no=? ORDER BY id", (report_no,))


def save_signature(username: str, source_file: str, image_file: str | None, uploaded_by: str) -> None:
    with connect() as c:
        c.execute(
            """INSERT INTO signatures(username,source_file,image_file,uploaded_by,uploaded_at)
               VALUES(?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET source_file=excluded.source_file,
               image_file=excluded.image_file,uploaded_by=excluded.uploaded_by,uploaded_at=excluded.uploaded_at""",
            (username, source_file, image_file, uploaded_by, now()),
        )


def signature(username: str) -> dict[str, Any] | None:
    return _one("SELECT * FROM signatures WHERE username=?", (username,))


# ---------- Document helpers ----------
def task_samples(task_no: str) -> list[dict[str, Any]]:
    return _rows(
        """SELECT s.* FROM samples s JOIN task_samples ts ON ts.sample_no=s.sample_no
           WHERE ts.task_no=? ORDER BY s.sample_no""",
        (task_no,),
    )


def commission_tasks(commission_no: str) -> list[dict[str, Any]]:
    rows = _rows("SELECT * FROM tasks WHERE commission_no=? ORDER BY created_at", (commission_no,))
    for r in rows:
        r["sample_nos"] = [x["sample_no"] for x in _rows("SELECT sample_no FROM task_samples WHERE task_no=? ORDER BY sample_no", (r["task_no"],))]
    return rows


def commission_loans(commission_no: str) -> list[dict[str, Any]]:
    return _rows(
        """SELECT l.*,t.experiment FROM sample_loans l JOIN tasks t ON t.task_no=l.task_no
           WHERE t.commission_no=? ORDER BY l.borrowed_at,l.sample_no""",
        (commission_no,),
    )


def report_records(commission_no: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for t in commission_tasks(commission_no):
        r = latest_record_by_task(t["task_no"])
        if r and r["status"] == "已锁定":
            out[t["task_no"]] = r
    return out


def dashboard_counts() -> dict[str, int]:
    queries = {
        "samples": "SELECT COUNT(*) n FROM samples WHERE is_deleted=0",
        "pending_tasks": "SELECT COUNT(*) n FROM tasks WHERE status='待接收'",
        "testing": "SELECT COUNT(*) n FROM tasks WHERE status='检测中'",
        "reviews": "SELECT COUNT(*) n FROM records WHERE status IN('待复核','更正待复核')",
        "returns": "SELECT COUNT(DISTINCT task_no) n FROM sample_loans WHERE return_status='待回库确认'",
        "reports": "SELECT COUNT(*) n FROM reports WHERE status!='已发布'",
    }
    return {k: int((_one(sql) or {"n": 0})["n"]) for k, sql in queries.items()}

def template_for_version(experiment: str, doc_type: str, version: str | None) -> dict[str, Any] | None:
    if version:
        found = _one(
            "SELECT * FROM template_versions WHERE experiment=? AND doc_type=? AND version=? ORDER BY id DESC LIMIT 1",
            (experiment, doc_type, version),
        )
        if found:
            return found
    return active_version(experiment, doc_type)
