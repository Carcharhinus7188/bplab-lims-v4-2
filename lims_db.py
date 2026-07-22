# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Iterable
import base64, calendar, hashlib, json, os, re, secrets, sqlite3

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "bplab_trace_v52.db"
ATTACHMENT_DIR = ROOT / "data" / "attachments"
SIGNATURE_DIR = ROOT / "data" / "signatures"
CHINA_TZ = ZoneInfo("Asia/Shanghai")


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
    year, month_idx = divmod(total, 12)
    month = month_idx + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def rows(sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as c:
        return [dict(x) for x in c.execute(sql, tuple(args)).fetchall()]


def one(sql: str, args: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connect() as c:
        r = c.execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 240_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _password_verify(password: str, encoded: str) -> bool:
    try:
        method, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if method != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iterations)
        )
        return secrets.compare_digest(base64.b64encode(digest).decode(), digest_b64)
    except Exception:
        return False


def init_db() -> None:
    with connect() as c:
        c.executescript(
            """
CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY, display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS organizations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, org_code TEXT UNIQUE, org_name TEXT NOT NULL UNIQUE,
  short_name TEXT, is_client INTEGER DEFAULT 0, is_manufacturer INTEGER DEFAULT 0,
  is_contract_manufacturer INTEGER DEFAULT 0, address TEXT, contact TEXT, phone TEXT,
  credit_code TEXT, notes TEXT, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS experiment_methods(
  experiment_code TEXT PRIMARY KEY, experiment_name TEXT NOT NULL UNIQUE,
  method_code TEXT NOT NULL, standard TEXT, category TEXT, kind TEXT,
  enabled INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS sample_catalog(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sample_code TEXT UNIQUE, sample_name TEXT NOT NULL,
  model TEXT NOT NULL, material_name TEXT NOT NULL,
  category TEXT, unit TEXT DEFAULT '件', experiment_codes TEXT DEFAULT '[]',
  notes TEXT, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS device_presets(
  experiment TEXT PRIMARY KEY, equipment_name TEXT, equipment_model TEXT, equipment_no TEXT,
  calibration_certificate TEXT, calibration_due TEXT, software TEXT, default_location TEXT,
  extra_json TEXT DEFAULT '{}', updated_by TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS commissions(
  commission_no TEXT PRIMARY KEY, client_org_id INTEGER NOT NULL, client_name TEXT NOT NULL,
  client_address TEXT, contact TEXT, phone TEXT,
  production_org_id INTEGER NOT NULL, production_org_name TEXT NOT NULL, production_relation TEXT NOT NULL,
  commission_date TEXT, due_date TEXT, subcontract_allowed TEXT, report_medium TEXT,
  conformity_judgment TEXT, uncertainty TEXT, delivery_method TEXT, cnas_mark TEXT,
  capability TEXT, method_choices TEXT DEFAULT '[]', notes TEXT,
  status TEXT DEFAULT '已入库', created_by TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS sample_groups(
  id INTEGER PRIMARY KEY AUTOINCREMENT, group_no TEXT NOT NULL UNIQUE, commission_no TEXT NOT NULL,
  catalog_id INTEGER, sample_name TEXT, model TEXT, material_name TEXT, production_org_id INTEGER,
  production_org_name TEXT, production_relation TEXT, product_no TEXT, quantity INTEGER,
  unit TEXT, condition TEXT, condition_note TEXT, storage_area TEXT, notes TEXT,
  status TEXT DEFAULT '待分配', is_void INTEGER DEFAULT 0, void_by TEXT, void_at TEXT,
  void_reason TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS samples(
  sample_no TEXT PRIMARY KEY, group_id INTEGER NOT NULL, group_no TEXT NOT NULL,
  commission_no TEXT NOT NULL, sample_name TEXT, model TEXT, material_name TEXT,
  condition TEXT, condition_note TEXT, current_location TEXT, current_holder TEXT,
  status TEXT DEFAULT '待分配', created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS requested_tests(
  id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL,
  experiment_code TEXT NOT NULL, experiment TEXT NOT NULL,
  method_code TEXT NOT NULL, standard TEXT, status TEXT DEFAULT '待分配', task_no TEXT,
  UNIQUE(group_id, experiment_code)
);
CREATE TABLE IF NOT EXISTS task_packages(
  package_no TEXT PRIMARY KEY, commission_no TEXT NOT NULL, group_id INTEGER NOT NULL,
  group_no TEXT NOT NULL, assignee TEXT NOT NULL, reviewer TEXT NOT NULL,
  material_name TEXT, sample_nos TEXT, experiment_codes TEXT, experiments TEXT, status TEXT DEFAULT '待接收',
  assigned_by TEXT, assigned_at TEXT, notified_at TEXT, accepted_at TEXT,
  detection_location TEXT, acceptance_result TEXT, acceptance_note TEXT,
  return_submitted_at TEXT, return_confirmed_at TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS tasks(
  task_no TEXT PRIMARY KEY, package_no TEXT NOT NULL, commission_no TEXT NOT NULL,
  group_id INTEGER NOT NULL, group_no TEXT NOT NULL, sample_nos TEXT,
  experiment_code TEXT NOT NULL, experiment TEXT,
  method_code TEXT, standard TEXT, material_name TEXT, assignee TEXT, reviewer TEXT,
  status TEXT DEFAULT '待接收', created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY AUTOINCREMENT, record_no TEXT NOT NULL, task_no TEXT NOT NULL,
  version INTEGER NOT NULL, experiment TEXT, owner TEXT, status TEXT, payload TEXT,
  template_version TEXT, sop_version TEXT, change_reason TEXT, created_at TEXT, updated_at TEXT,
  UNIQUE(record_no, version)
);
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, record_no TEXT, version INTEGER, reviewer TEXT,
  decision TEXT, comment TEXT, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS package_loans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, package_no TEXT NOT NULL, sample_no TEXT NOT NULL,
  borrower TEXT, borrowed_at TEXT, purpose TEXT, detection_location TEXT, issue_note TEXT,
  return_condition TEXT, return_note TEXT, returned_by TEXT, returned_at TEXT,
  return_status TEXT DEFAULT '未归还', confirmed_by TEXT, confirmed_at TEXT,
  confirmed_location TEXT, UNIQUE(package_no, sample_no)
);
CREATE TABLE IF NOT EXISTS attachments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, attachment_id TEXT UNIQUE, commission_no TEXT,
  package_no TEXT, task_no TEXT, sample_no TEXT, attachment_type TEXT, original_name TEXT,
  stored_name TEXT, relative_path TEXT, sha256 TEXT, captured_at TEXT, uploader TEXT,
  equipment_software TEXT, description TEXT, is_original INTEGER DEFAULT 1,
  parent_attachment_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS reports(
  report_no TEXT PRIMARY KEY, commission_no TEXT UNIQUE, status TEXT DEFAULT '待检测员确认',
  tester TEXT, verifier TEXT, approver TEXT, report_category TEXT, sample_statement TEXT,
  conclusion TEXT, notes TEXT, tester_signed_at TEXT, verifier_signed_at TEXT,
  approver_signed_at TEXT, publish_date TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS report_actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, report_no TEXT, actor TEXT, action TEXT,
  comment TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS signatures(
  username TEXT PRIMARY KEY, source_file TEXT, image_file TEXT, uploaded_by TEXT, uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS template_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, experiment TEXT, doc_type TEXT, file_name TEXT,
  version TEXT, effective_date TEXT, status TEXT, uploader TEXT, uploaded_at TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS audit_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT, entity_id TEXT, actor TEXT,
  action TEXT, field_name TEXT, old_value TEXT, new_value TEXT, reason TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS sample_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sample_no TEXT, actor TEXT, action TEXT,
  from_status TEXT, to_status TEXT, from_location TEXT, to_location TEXT,
  details TEXT, created_at TEXT
);
"""
        )
        demo_users = [
            ("admin", "系统管理员", "admin123", "管理员"),
            ("receiver", "样品管理员王工", "receive123", "样品管理员"),
            ("store", "样品管理员赵工", "store123", "样品管理员"),
            ("tester", "实验员张工", "test123", "实验人员"),
            ("reviewer", "复核员李工", "review123", "复核实验员"),
            ("approver", "批准人刘工", "approve123", "批准人"),
        ]
        for username, name, password, role in demo_users:
            if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                c.execute(
                    "INSERT INTO users VALUES(?,?,?,?,1,?)",
                    (username, name, _password_hash(password), role, now()),
                )
        c.execute(
            """INSERT INTO organizations(
               org_code,org_name,short_name,is_client,is_manufacturer,
               is_contract_manufacturer,address,contact,phone,credit_code,notes,
               enabled,created_at,updated_at
               ) VALUES(
               'ORG-DEFAULT','测试委托客户（预设）','测试客户',1,0,0,
               '辽宁省大连市测试地址','测试联系人','13800000000','',
               '用于系统流程测试，可在单位信息库中修改或停用',1,?,?
               )
               ON CONFLICT(org_code) DO UPDATE SET
               org_name=excluded.org_name,short_name=excluded.short_name,
               is_client=1,is_manufacturer=0,is_contract_manufacturer=0,
               address=excluded.address,contact=excluded.contact,phone=excluded.phone,
               notes=excluded.notes,enabled=1,updated_at=excluded.updated_at""",
            (now(), now()),
        )
        c.execute(
            """INSERT INTO organizations(
               org_code,org_name,short_name,is_client,is_manufacturer,
               is_contract_manufacturer,address,contact,phone,credit_code,notes,
               enabled,created_at,updated_at
               ) VALUES(
               'ORG-TEST-MFR','测试生产单位（预设）','测试生产单位',0,1,0,
               '辽宁省大连市测试生产地址','生产联系人','13900000000','',
               '用于系统流程测试，可在单位信息库中修改或停用',1,?,?
               )
               ON CONFLICT(org_code) DO UPDATE SET
               org_name=excluded.org_name,short_name=excluded.short_name,
               is_client=0,is_manufacturer=1,is_contract_manufacturer=0,
               address=excluded.address,contact=excluded.contact,phone=excluded.phone,
               notes=excluded.notes,enabled=1,updated_at=excluded.updated_at""",
            (now(), now()),
        )
        from constants import EXPERIMENTS
        for order, (experiment_name, cfg) in enumerate(EXPERIMENTS.items(), 1):
            c.execute(
                """INSERT INTO experiment_methods(
                   experiment_code,experiment_name,method_code,standard,category,kind,enabled,
                   sort_order,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,1,?,?,?)
                   ON CONFLICT(experiment_code) DO UPDATE SET
                   experiment_name=excluded.experiment_name,method_code=excluded.method_code,
                   standard=excluded.standard,category=excluded.category,kind=excluded.kind,
                   sort_order=excluded.sort_order,updated_at=excluded.updated_at""",
                (cfg["key"], experiment_name, cfg["method"], cfg["std"], cfg["category"],
                 cfg["kind"], order, now(), now()),
            )
        test_experiments = [
            EXPERIMENTS["表面粗糙度试验"]["key"],
            EXPERIMENTS["弯曲性能试验"]["key"],
            EXPERIMENTS["维氏硬度试验"]["key"],
        ]
        c.execute(
            """INSERT INTO sample_catalog(
               sample_code,sample_name,model,material_name,category,unit,experiment_codes,
               notes,enabled,created_at,updated_at
               ) VALUES(
               'S-DEFAULT','测试金属试样（预设）','25 mm×2 mm×2 mm','钴铬合金',
               '金属试样','件',?,
               '测试预设：已关联表面粗糙度、弯曲性能和维氏硬度试验',1,?,?
               )
               ON CONFLICT(sample_code) DO UPDATE SET
               sample_name=excluded.sample_name,model=excluded.model,
               material_name=excluded.material_name,category=excluded.category,
               unit=excluded.unit,experiment_codes=excluded.experiment_codes,
               notes=excluded.notes,enabled=1,updated_at=excluded.updated_at""",
            (json.dumps(test_experiments, ensure_ascii=False), now(), now()),
        )


def audit(entity_type: str, entity_id: str, actor: str, action: str, field_name: str = "", old_value: Any = "", new_value: Any = "", reason: str = "") -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO audit_logs(entity_type,entity_id,actor,action,field_name,old_value,new_value,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (entity_type, entity_id, actor, action, field_name, str(old_value), str(new_value), reason, now()),
        )


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    r = one("SELECT username,display_name,password_hash,role,enabled FROM users WHERE username=?", (username.strip(),))
    if r and r["enabled"] and _password_verify(password, r["password_hash"]):
        return {k: r[k] for k in ("username", "display_name", "role")}
    return None


def create_session(username: str, days: int = 7) -> str:
    token = secrets.token_urlsafe(28)
    with connect() as c:
        c.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (token, username, (china_now() + timedelta(days=days)).isoformat(timespec="seconds"), now()),
        )
    return token


def session_user(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    return one(
        """SELECT u.username,u.display_name,u.role FROM sessions s JOIN users u ON u.username=s.username
           WHERE s.token=? AND s.expires_at>? AND u.enabled=1""",
        (token, now()),
    )


def delete_session(token: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


def list_users() -> list[dict[str, Any]]:
    return rows("SELECT username,display_name,role,enabled,created_at FROM users ORDER BY username")


def add_user(username: str, display_name: str, password: str, role: str) -> None:
    if not username or not display_name or not password:
        raise ValueError("用户名、姓名和密码不能为空")
    with connect() as c:
        c.execute(
            "INSERT INTO users VALUES(?,?,?,?,1,?)",
            (username.strip(), display_name.strip(), _password_hash(password), role, now()),
        )
    audit("user", username, "admin", "创建用户")


# ---------------------- Master data ----------------------
def list_organizations(include_disabled: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM organizations"
    if not include_disabled:
        q += " WHERE enabled=1"
    return rows(q + " ORDER BY org_name")


def add_organization(data: dict[str, Any], actor: str) -> None:
    if not data.get("org_name", "").strip():
        raise ValueError("单位名称不能为空")
    with connect() as c:
        c.execute(
            """INSERT INTO organizations(org_code,org_name,short_name,is_client,is_manufacturer,
               is_contract_manufacturer,address,contact,phone,credit_code,notes,enabled,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (
                data.get("org_code") or None, data["org_name"].strip(), data.get("short_name", ""),
                int(bool(data.get("is_client"))), int(bool(data.get("is_manufacturer"))),
                int(bool(data.get("is_contract_manufacturer"))), data.get("address", ""),
                data.get("contact", ""), data.get("phone", ""), data.get("credit_code", ""),
                data.get("notes", ""), now(), now(),
            ),
        )
    audit("organization", data["org_name"], actor, "新增单位")


def list_experiment_methods(include_disabled: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM experiment_methods"
    if not include_disabled:
        q += " WHERE enabled=1"
    return rows(q + " ORDER BY sort_order,experiment_name")


def experiment_method(experiment_code: str) -> dict[str, Any] | None:
    """Internal lookup retained for relational integrity; not shown to users."""
    return one("SELECT * FROM experiment_methods WHERE experiment_code=?", (experiment_code,))


def experiment_method_by_name(experiment_name: str) -> dict[str, Any] | None:
    return one("SELECT * FROM experiment_methods WHERE experiment_name=?", (experiment_name,))


def _next_internal_experiment_key() -> str:
    existing = rows("SELECT experiment_code FROM experiment_methods")
    used = []
    for item in existing:
        match = re.fullmatch(r"I(\d+)", str(item.get("experiment_code", "")))
        if match:
            used.append(int(match.group(1)))
    return f"I{(max(used) if used else 0) + 1:03d}"


def save_experiment_method(data: dict[str, Any], actor: str) -> None:
    name = str(data.get("experiment_name", "")).strip()
    method = str(data.get("method_code", "")).strip()
    if not name or not method:
        raise ValueError("实验名称和检测方法不能为空")
    if method == "其他方法":
        raise ValueError("检测方法库不允许使用“其他方法”")
    existing = experiment_method_by_name(name)
    internal_key = existing["experiment_code"] if existing else _next_internal_experiment_key()
    with connect() as c:
        c.execute(
            """INSERT INTO experiment_methods(
               experiment_code,experiment_name,method_code,standard,category,kind,enabled,
               sort_order,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(experiment_code) DO UPDATE SET
               experiment_name=excluded.experiment_name,method_code=excluded.method_code,
               standard=excluded.standard,category=excluded.category,kind=excluded.kind,
               enabled=excluded.enabled,sort_order=excluded.sort_order,updated_at=excluded.updated_at""",
            (
                internal_key, name, method, data.get("standard", ""),
                data.get("category", ""), data.get("kind", ""),
                int(bool(data.get("enabled", True))),
                int(data.get("sort_order", 0) or 0), now(), now(),
            ),
        )
    audit(
        "experiment_method", name, actor, "保存检测项目与方法",
        new_value=f"{name}｜{method}",
    )


def list_catalog(include_disabled: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM sample_catalog"
    if not include_disabled:
        q += " WHERE enabled=1"
    result = rows(q + " ORDER BY sample_name,model")
    mapping = {x["experiment_code"]: x for x in list_experiment_methods(True)}
    for x in result:
        x["experiment_codes_list"] = json.loads(x.get("experiment_codes") or "[]")
        x["experiment_labels"] = [
            f"{mapping[code]['experiment_name']}｜{mapping[code]['method_code']}"
            for code in x["experiment_codes_list"] if code in mapping
        ]
    return result


def add_catalog(data: dict[str, Any], actor: str) -> None:
    for field in ("sample_name", "model", "material_name"):
        if not str(data.get(field, "")).strip():
            raise ValueError(f"{field}不能为空")
    codes = list(dict.fromkeys(data.get("experiment_codes", [])))
    enabled_codes = {x["experiment_code"] for x in list_experiment_methods()}
    invalid = [x for x in codes if x not in enabled_codes]
    if invalid:
        raise ValueError("存在无效或停用的检测项目")
    with connect() as c:
        c.execute(
            """INSERT INTO sample_catalog(
               sample_code,sample_name,model,material_name,category,unit,experiment_codes,
               notes,enabled,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
            (data.get("sample_code") or None,data["sample_name"].strip(),data["model"].strip(),
             data["material_name"].strip(),data.get("category",""),data.get("unit","件"),
             json.dumps(codes,ensure_ascii=False),data.get("notes",""),now(),now()),
        )
    audit("sample_catalog", data["sample_name"], actor, "新增样品资料", new_value="、".join(codes))

def device_preset(experiment: str) -> dict[str, Any]:
    r = one("SELECT * FROM device_presets WHERE experiment=?", (experiment,)) or {}
    if r:
        r["extra"] = json.loads(r.get("extra_json") or "{}")
    return r


def save_device_preset(experiment: str, data: dict[str, Any], actor: str) -> None:
    with connect() as c:
        c.execute(
            """INSERT INTO device_presets(experiment,equipment_name,equipment_model,equipment_no,
               calibration_certificate,calibration_due,software,default_location,extra_json,updated_by,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(experiment) DO UPDATE SET
               equipment_name=excluded.equipment_name,equipment_model=excluded.equipment_model,
               equipment_no=excluded.equipment_no,calibration_certificate=excluded.calibration_certificate,
               calibration_due=excluded.calibration_due,software=excluded.software,
               default_location=excluded.default_location,extra_json=excluded.extra_json,
               updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
            (
                experiment, data.get("equipment_name", ""), data.get("equipment_model", ""),
                data.get("equipment_no", ""), data.get("calibration_certificate", ""),
                str(data.get("calibration_due") or ""), data.get("software", ""),
                data.get("default_location", ""), json.dumps(data.get("extra", {}), ensure_ascii=False),
                actor, now(),
            ),
        )
    audit("device_preset", experiment, actor, "更新设备预设")


# ---------------------- Numbering and intake ----------------------
def next_commission_no() -> str:
    prefix = china_now().strftime("WT%Y%m%d")
    r = one("SELECT commission_no FROM commissions WHERE commission_no LIKE ? ORDER BY commission_no DESC LIMIT 1", (prefix + "%",))
    seq = int(r["commission_no"][-3:]) + 1 if r and r["commission_no"][-3:].isdigit() else 1
    return f"{prefix}{seq:03d}"


def next_sample_base() -> str:
    prefix = china_now().strftime("BP%Y%m%d")
    result = rows("SELECT group_no FROM sample_groups WHERE group_no LIKE ?", (prefix + "%",))
    seqs = []
    for x in result:
        m = re.fullmatch(re.escape(prefix) + r"(\d{3})", x["group_no"])
        if m:
            seqs.append(int(m.group(1)))
    return f"{prefix}{max(seqs or [0]) + 1:03d}"


def create_commission(data: dict[str, Any], groups: list[dict[str, Any]], actor: str) -> str:
    if not groups:
        raise ValueError("至少添加一个样品组")
    commission_no = data["commission_no"].strip().upper().replace(" ", "")
    if not data.get("production_org_id"):
        raise ValueError("必须统一选择生产单位或受委托生产企业")
    ts = now()
    selected_methods: list[str] = []
    with connect() as c:
        c.execute(
            """INSERT INTO commissions(
               commission_no,client_org_id,client_name,client_address,contact,phone,
               production_org_id,production_org_name,production_relation,
               commission_date,due_date,subcontract_allowed,report_medium,conformity_judgment,
               uncertainty,delivery_method,cnas_mark,capability,method_choices,notes,status,
               created_by,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'已入库',?,?,?)""",
            (commission_no,data["client_org_id"],data["client_name"],data.get("client_address",""),
             data.get("contact",""),data.get("phone",""),data["production_org_id"],
             data["production_org_name"],data["production_relation"],str(data["commission_date"]),
             str(data["due_date"]),data.get("subcontract_allowed","否"),data.get("report_medium","电子档"),
             data.get("conformity_judgment","是"),data.get("uncertainty","否"),
             data.get("delivery_method","Email"),data.get("cnas_mark","否"),
             data.get("capability","完全满足"),"[]",data.get("notes",""),actor,ts,ts),
        )
        mapping = {x["experiment_code"]: x for x in list_experiment_methods()}
        for group_data in groups:
            group_no = group_data["group_no"].strip().upper().replace(" ", "")
            qty = int(group_data["quantity"])
            if qty < 1 or qty > 99:
                raise ValueError("每个样品组数量应为1～99")
            codes = list(dict.fromkeys(group_data.get("experiment_codes", [])))
            if not codes:
                raise ValueError(f"样品组{group_no}未选择检测项目与方法")
            missing = [code for code in codes if code not in mapping]
            if missing:
                raise ValueError("存在无效或已停用的检测项目")
            c.execute(
                """INSERT INTO sample_groups(
                   group_no,commission_no,catalog_id,sample_name,model,material_name,
                   production_org_id,production_org_name,production_relation,product_no,quantity,
                   unit,condition,condition_note,storage_area,notes,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, '待分配',?,?)""",
                (group_no,commission_no,group_data.get("catalog_id"),group_data["sample_name"],
                 group_data["model"],group_data["material_name"],data["production_org_id"],
                 data["production_org_name"],data["production_relation"],group_data.get("product_no",""),
                 qty,group_data.get("unit","件"),group_data.get("condition","完好"),
                 group_data.get("condition_note",""),group_data.get("storage_area","A区域"),
                 group_data.get("notes",""),ts,ts),
            )
            group_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            for i in range(1, qty + 1):
                sample_no = f"{group_no}-{i:02d}"
                c.execute(
                    """INSERT INTO samples(
                       sample_no,group_id,group_no,commission_no,sample_name,model,material_name,
                       condition,condition_note,current_location,current_holder,status,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'待分配',?,?)""",
                    (sample_no,group_id,group_no,commission_no,group_data["sample_name"],group_data["model"],
                     group_data["material_name"],group_data.get("condition","完好"),
                     group_data.get("condition_note",""),group_data.get("storage_area","A区域"),actor,ts,ts),
                )
                c.execute(
                    """INSERT INTO sample_events(
                       sample_no,actor,action,from_status,to_status,from_location,to_location,details,created_at
                       ) VALUES(?,?,?,'','待分配','',?,?,?)""",
                    (sample_no,actor,"样品接收并入库",group_data.get("storage_area","A区域"),
                     f"委托编号:{commission_no};生产单位:{data['production_org_name']};关系:{data['production_relation']};"
                     f"样品状态:{group_data.get('condition','完好')};备注:{group_data.get('condition_note','')}",ts),
                )
            for code in codes:
                item = mapping[code]
                selected_methods.append(item["method_code"])
                c.execute(
                    """INSERT INTO requested_tests(
                       group_id,experiment_code,experiment,method_code,standard,status
                       ) VALUES(?,?,?,?,?,'待分配')""",
                    (group_id,code,item["experiment_name"],item["method_code"],item.get("standard","")),
                )
        method_choices = list(dict.fromkeys(selected_methods))
        c.execute("UPDATE commissions SET method_choices=?,updated_at=? WHERE commission_no=?",
                  (json.dumps(method_choices,ensure_ascii=False),ts,commission_no))
    audit("commission", commission_no, actor, "新建委托并入库", new_value=len(groups))
    return commission_no

def list_commissions() -> list[dict[str, Any]]:
    return rows("SELECT * FROM commissions ORDER BY created_at DESC")


def commission(commission_no: str) -> dict[str, Any] | None:
    r = one("SELECT * FROM commissions WHERE commission_no=?", (commission_no,))
    if r:
        r["method_choices_list"] = json.loads(r.get("method_choices") or "[]")
    return r


def commission_groups(commission_no: str, include_void: bool = False) -> list[dict[str, Any]]:
    q = "SELECT * FROM sample_groups WHERE commission_no=?"
    args: list[Any] = [commission_no]
    if not include_void:
        q += " AND is_void=0"
    return rows(q + " ORDER BY group_no", args)


def group(group_id: int) -> dict[str, Any] | None:
    return one("SELECT * FROM sample_groups WHERE id=?", (group_id,))


def group_samples(group_id: int) -> list[dict[str, Any]]:
    return rows("SELECT * FROM samples WHERE group_id=? ORDER BY sample_no", (group_id,))


def commission_samples(commission_no: str) -> list[dict[str, Any]]:
    return rows("SELECT s.* FROM samples s JOIN sample_groups g ON g.id=s.group_id WHERE s.commission_no=? AND g.is_void=0 ORDER BY s.sample_no", (commission_no,))


def requested_tests(group_id: int) -> list[dict[str, Any]]:
    return rows("SELECT * FROM requested_tests WHERE group_id=? ORDER BY experiment_code", (group_id,))


def void_group(group_id: int, actor: str, reason: str) -> None:
    g = group(group_id)
    if not g:
        raise ValueError("样品组不存在")
    if one("SELECT COUNT(*) n FROM task_packages WHERE group_id=?", (group_id,))["n"]:
        raise ValueError("该样品组已下发任务，不能删除，只能作废并另行处理")
    with connect() as c:
        c.execute("UPDATE sample_groups SET is_void=1,void_by=?,void_at=?,void_reason=?,status='已删除',updated_at=? WHERE id=?", (actor, now(), reason, now(), group_id))
        c.execute("UPDATE samples SET status='已删除',updated_at=? WHERE group_id=?", (now(), group_id))
    audit("sample_group", str(group_id), actor, "删除错误入库", reason=reason)


# ---------------------- Task packages ----------------------
def available_groups_for_assignment() -> list[dict[str, Any]]:
    return rows(
        """SELECT g.*,COUNT(CASE WHEN r.status='待分配' THEN 1 END) pending_count
           FROM sample_groups g JOIN requested_tests r ON r.group_id=g.id
           WHERE g.is_void=0 GROUP BY g.id HAVING pending_count>0 ORDER BY g.created_at"""
    )


def _next_package_no(group_no: str) -> str:
    r = one("SELECT package_no FROM task_packages WHERE group_no=? ORDER BY package_no DESC LIMIT 1", (group_no,))
    seq = int(r["package_no"].rsplit("P", 1)[-1]) + 1 if r else 1
    return f"{group_no}-P{seq:02d}"


def create_task_package(group_id: int, experiment_codes: list[str], assignee: str, reviewer: str, actor: str) -> str:
    if not experiment_codes:
        raise ValueError("至少选择一个实验")
    g = group(group_id)
    if not g or g["is_void"]:
        raise ValueError("样品组不可用")
    available = {
        x["experiment_code"]: x
        for x in requested_tests(group_id)
        if x["status"] == "待分配"
    }
    missing = [x for x in experiment_codes if x not in available]
    if missing:
        raise ValueError("部分实验已分配或不属于该样品组")
    package_no = _next_package_no(g["group_no"])
    sample_nos = [x["sample_no"] for x in group_samples(group_id)]
    selected = [available[key] for key in experiment_codes]
    experiment_names = [x["experiment"] for x in selected]
    ts = now()
    with connect() as c:
        c.execute(
            """INSERT INTO task_packages(
               package_no,commission_no,group_id,group_no,assignee,reviewer,material_name,
               sample_nos,experiment_codes,experiments,status,assigned_by,assigned_at,
               notified_at,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,'待接收',?,?,?,?,?)""",
            (
                package_no, g["commission_no"], group_id, g["group_no"],
                assignee, reviewer, g["material_name"],
                json.dumps(sample_nos, ensure_ascii=False),
                json.dumps(experiment_codes, ensure_ascii=False),
                json.dumps(experiment_names, ensure_ascii=False),
                actor, ts, ts, ts, ts,
            ),
        )
        for index, req in enumerate(selected, 1):
            task_no = f"{package_no}-T{index:02d}"
            c.execute(
                """INSERT INTO tasks(
                   task_no,package_no,commission_no,group_id,group_no,sample_nos,
                   experiment_code,experiment,method_code,standard,material_name,
                   assignee,reviewer,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'待接收',?,?)""",
                (
                    task_no, package_no, g["commission_no"], group_id, g["group_no"],
                    json.dumps(sample_nos, ensure_ascii=False),
                    req["experiment_code"], req["experiment"], req["method_code"],
                    req["standard"], g["material_name"], assignee, reviewer, ts, ts,
                ),
            )
            c.execute(
                "UPDATE requested_tests SET status='已分配',task_no=? WHERE id=?",
                (task_no, req["id"]),
            )
        c.execute(
            "UPDATE sample_groups SET status='等待实验员接收',updated_at=? WHERE id=?",
            (ts, group_id),
        )
        c.execute(
            "UPDATE samples SET status='等待实验员接收',updated_at=? WHERE group_id=?",
            (ts, group_id),
        )
        for sample_no in sample_nos:
            current = one(
                "SELECT current_location FROM samples WHERE sample_no=?",
                (sample_no,),
            ) or {}
            c.execute(
                """INSERT INTO sample_events(
                   sample_no,actor,action,from_status,to_status,from_location,
                   to_location,details,created_at
                   ) VALUES(?,?,'任务包下发','待分配','等待实验员接收',?,?,?,?)""",
                (
                    sample_no, actor, current.get("current_location", ""),
                    current.get("current_location", ""),
                    f"任务包:{package_no};实验:{'、'.join(experiment_names)};实验员:{assignee}",
                    ts,
                ),
            )
    audit(
        "task_package", package_no, actor, "下发任务包",
        new_value="、".join(experiment_names),
    )
    return package_no


def list_packages(role: str | None = None, username: str | None = None, statuses: list[str] | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM task_packages WHERE 1=1"
    args: list[Any] = []
    if role == "实验人员" and username:
        q += " AND assignee=?"; args.append(username)
    elif role == "复核实验员" and username:
        q += " AND reviewer=?"; args.append(username)
    if statuses:
        q += " AND status IN (" + ",".join("?" * len(statuses)) + ")"; args.extend(statuses)
    result = rows(q + " ORDER BY updated_at DESC", args)
    for x in result:
        x["sample_nos_list"] = json.loads(x.get("sample_nos") or "[]")
        x["experiment_codes_list"] = json.loads(x.get("experiment_codes") or "[]")
        x["experiments_list"] = json.loads(x.get("experiments") or "[]")
    return result


def package(package_no: str) -> dict[str, Any] | None:
    r = one("SELECT * FROM task_packages WHERE package_no=?", (package_no,))
    if r:
        r["sample_nos_list"] = json.loads(r.get("sample_nos") or "[]")
        r["experiment_codes_list"] = json.loads(r.get("experiment_codes") or "[]")
        r["experiments_list"] = json.loads(r.get("experiments") or "[]")
    return r


def package_tasks(package_no: str) -> list[dict[str, Any]]:
    result = rows("SELECT * FROM tasks WHERE package_no=? ORDER BY task_no", (package_no,))
    for x in result:
        x["sample_nos_list"] = json.loads(x.get("sample_nos") or "[]")
    return result


def task(task_no: str) -> dict[str, Any] | None:
    r = one("SELECT * FROM tasks WHERE task_no=?", (task_no,))
    if r:
        r["sample_nos_list"] = json.loads(r.get("sample_nos") or "[]")
    return r


def accept_package(package_no: str, actor: str, result: str, detection_location: str, note: str) -> None:
    p = package(package_no)
    if not p or p["assignee"] != actor:
        raise ValueError("只能由被指定的实验员接收任务包")
    if p["status"] != "待接收":
        raise ValueError("任务包当前状态不能接收")
    if result != "样品已收到，确认完好":
        with connect() as c:
            c.execute("UPDATE task_packages SET status='接收异常',accepted_at=?,acceptance_result=?,acceptance_note=?,updated_at=? WHERE package_no=?", (now(), result, note, now(), package_no))
        audit("task_package", package_no, actor, "接收异常", reason=note)
        return
    ts = now()
    purpose = "、".join(p["experiments_list"])
    with connect() as c:
        c.execute(
            """UPDATE task_packages SET status='检测中',accepted_at=?,detection_location=?,
               acceptance_result=?,acceptance_note=?,updated_at=? WHERE package_no=?""",
            (ts, detection_location, result, note, ts, package_no),
        )
        c.execute("UPDATE tasks SET status='检测中',updated_at=? WHERE package_no=?", (ts, package_no))
        c.execute("UPDATE sample_groups SET status='检测中',updated_at=? WHERE id=?", (ts, p["group_id"]))
        for sample_no in p["sample_nos_list"]:
            old = one("SELECT status,current_location FROM samples WHERE sample_no=?", (sample_no,)) or {}
            c.execute("UPDATE samples SET status='检测中',current_location=?,current_holder=?,updated_at=? WHERE sample_no=?", (detection_location, actor, ts, sample_no))
            c.execute(
                """INSERT OR REPLACE INTO package_loans(package_no,sample_no,borrower,borrowed_at,purpose,
                   detection_location,issue_note,return_status) VALUES(?,?,?,?,?,?,?,'未归还')""",
                (package_no, sample_no, actor, ts, purpose, detection_location, note),
            )
            c.execute(
                """INSERT INTO sample_events(sample_no,actor,action,from_status,to_status,from_location,
                   to_location,details,created_at) VALUES(?,?,'实验员领用',?,'检测中',?,?,?,?)""",
                (sample_no, actor, old.get("status", ""), old.get("current_location", ""), detection_location, f"任务包:{package_no};用途:{purpose};{note}", ts),
            )
    audit("task_package", package_no, actor, "确认领用", new_value=detection_location)


# ---------------------- Records and review ----------------------
def latest_record(task_no: str) -> dict[str, Any] | None:
    r = one("SELECT * FROM records WHERE task_no=? ORDER BY version DESC LIMIT 1", (task_no,))
    if r:
        r["payload"] = json.loads(r.get("payload") or "{}")
    return r


def record(record_no: str, version: int) -> dict[str, Any] | None:
    r = one("SELECT * FROM records WHERE record_no=? AND version=?", (record_no, version))
    if r:
        r["payload"] = json.loads(r.get("payload") or "{}")
    return r


def record_versions(record_no: str) -> list[dict[str, Any]]:
    result = rows("SELECT * FROM records WHERE record_no=? ORDER BY version", (record_no,))
    for x in result:
        x["payload"] = json.loads(x.get("payload") or "{}")
    return result


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


def save_record(task_no: str, version: int, payload: dict[str, Any], owner: str, status: str, template_version: str = "A/0", sop_version: str = "A/0", reason: str = "", compare_payload: dict[str, Any] | None = None) -> None:
    t = task(task_no)
    if not t:
        raise ValueError("任务不存在")
    ts = now()
    with connect() as c:
        c.execute(
            """INSERT INTO records(record_no,task_no,version,experiment,owner,status,payload,
               template_version,sop_version,change_reason,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(record_no,version) DO UPDATE SET
               owner=excluded.owner,status=excluded.status,payload=excluded.payload,
               template_version=excluded.template_version,sop_version=excluded.sop_version,
               change_reason=excluded.change_reason,updated_at=excluded.updated_at""",
            (
                task_no, task_no, version, t["experiment"], owner, status,
                json.dumps(payload, ensure_ascii=False, default=str), template_version, sop_version,
                reason, ts, ts,
            ),
        )
        c.execute("UPDATE tasks SET status=?,updated_at=? WHERE task_no=?", (status if status != "草稿" else "检测中", ts, task_no))
    if compare_payload is not None:
        old, new = _flatten(compare_payload), _flatten(payload)
        for field in sorted(set(old) | set(new)):
            if str(old.get(field, "")) != str(new.get(field, "")):
                audit("record", task_no, owner, "字段修改", field, old.get(field, ""), new.get(field, ""), reason)
    audit("record", task_no, owner, "提交复核" if "待复核" in status else "保存草稿", reason=reason)


def pending_reviews(username: str | None = None) -> list[dict[str, Any]]:
    q = """SELECT r.*,t.package_no,t.commission_no,t.group_no,t.sample_nos,t.experiment,t.reviewer
           FROM records r JOIN tasks t ON t.task_no=r.task_no
           WHERE r.status IN ('待复核','更正待复核')"""
    args: list[Any] = []
    if username:
        q += " AND t.reviewer=?"; args.append(username)
    result = rows(q + " ORDER BY r.updated_at", args)
    for x in result:
        x["payload"] = json.loads(x.get("payload") or "{}")
    return result


def review_record(record_no: str, version: int, reviewer: str, decision: str, comment: str) -> None:
    r = record(record_no, version)
    if not r:
        raise ValueError("记录不存在")
    t = task(record_no)
    if t and t["reviewer"] != reviewer:
        raise ValueError("当前人员不是该任务的复核人")
    ts = now()
    status = "已锁定" if decision == "通过" else "退回修改"
    with connect() as c:
        c.execute("UPDATE records SET status=?,updated_at=? WHERE record_no=? AND version=?", (status, ts, record_no, version))
        c.execute("INSERT INTO reviews(record_no,version,reviewer,decision,comment,reviewed_at) VALUES(?,?,?,?,?,?)", (record_no, version, reviewer, decision, comment, ts))
        c.execute("UPDATE tasks SET status=?,updated_at=? WHERE task_no=?", ("已完成" if decision == "通过" else "退回修改", ts, record_no))
    audit("record", record_no, reviewer, "复核" + decision, reason=comment)
    if decision == "通过" and t:
        _refresh_package_and_report(t["package_no"], t["commission_no"])


def _refresh_package_and_report(package_no: str, commission_no: str) -> None:
    unfinished = one("SELECT COUNT(*) n FROM tasks WHERE package_no=? AND status!='已完成'", (package_no,))["n"]
    if unfinished == 0:
        with connect() as c:
            c.execute("UPDATE task_packages SET status='待归还',updated_at=? WHERE package_no=?", (now(), package_no))
    commission_unfinished = one("SELECT COUNT(*) n FROM tasks WHERE commission_no=? AND status!='已完成'", (commission_no,))["n"]
    requested_unassigned = one("""SELECT COUNT(*) n FROM requested_tests r JOIN sample_groups g ON g.id=r.group_id
                                  WHERE g.commission_no=? AND g.is_void=0 AND r.status='待分配'""", (commission_no,))["n"]
    if commission_unfinished == 0 and requested_unassigned == 0:
        ensure_report(commission_no)


def create_revision(record_no: str, actor: str, reason: str) -> int:
    if not reason.strip():
        raise ValueError("修改原因不能为空")
    versions = record_versions(record_no)
    if not versions or versions[-1]["status"] != "已锁定":
        raise ValueError("只有已锁定记录可以创建修改版")
    base = versions[-1]
    version = base["version"] + 1
    save_record(record_no, version, base["payload"], actor, "草稿", base.get("template_version") or "A/0", base.get("sop_version") or "A/0", reason, base["payload"])
    return version


def audit_logs(entity_id: str | None = None) -> list[dict[str, Any]]:
    if entity_id:
        return rows("SELECT * FROM audit_logs WHERE entity_id=? ORDER BY id", (entity_id,))
    return rows("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 500")


# ---------------------- Return ----------------------
def return_candidates(username: str) -> list[dict[str, Any]]:
    return list_packages("实验人员", username, ["待归还"])


def package_loan_rows(package_no: str) -> list[dict[str, Any]]:
    return rows("SELECT * FROM package_loans WHERE package_no=? ORDER BY sample_no", (package_no,))


def submit_package_return(package_no: str, actor: str, items: list[dict[str, Any]]) -> None:
    p = package(package_no)
    if not p or p["assignee"] != actor or p["status"] != "待归还":
        raise ValueError("当前任务包不能提交归还")
    ts = now()
    with connect() as c:
        for item in items:
            sample_no = item["sample_no"]
            c.execute(
                """UPDATE package_loans SET return_condition=?,return_note=?,returned_by=?,returned_at=?,
                   return_status='待回库确认' WHERE package_no=? AND sample_no=?""",
                (item.get("condition", "完好"), item.get("note", ""), actor, ts, package_no, sample_no),
            )
            old = one("SELECT status,current_location FROM samples WHERE sample_no=?", (sample_no,)) or {}
            c.execute("UPDATE samples SET status='待回库确认',current_location='回库交接区',current_holder='',updated_at=? WHERE sample_no=?", (ts, sample_no))
            c.execute(
                """INSERT INTO sample_events(sample_no,actor,action,from_status,to_status,from_location,to_location,details,created_at)
                   VALUES(?,?,'实验员归还',?,'待回库确认',?,'回库交接区',?,?)""",
                (sample_no, actor, old.get("status", ""), old.get("current_location", ""), f"任务包:{package_no};状态:{item.get('condition','')};备注:{item.get('note','')}", ts),
            )
        c.execute("UPDATE task_packages SET status='待回库确认',return_submitted_at=?,updated_at=? WHERE package_no=?", (ts, ts, package_no))
    audit("task_package", package_no, actor, "提交整组样品归还")


def pending_return_packages() -> list[dict[str, Any]]:
    return list_packages(statuses=["待回库确认"])


def confirm_package_return(package_no: str, actor: str, items: list[dict[str, Any]]) -> None:
    p = package(package_no)
    if not p or p["status"] != "待回库确认":
        raise ValueError("任务包不在待回库确认状态")
    ts = now()
    with connect() as c:
        for item in items:
            sample_no, location = item["sample_no"], item["location"]
            loan = one("SELECT return_condition FROM package_loans WHERE package_no=? AND sample_no=?", (package_no, sample_no)) or {}
            c.execute(
                """UPDATE package_loans SET return_status='已回库',confirmed_by=?,confirmed_at=?,confirmed_location=?
                   WHERE package_no=? AND sample_no=?""",
                (actor, ts, location, package_no, sample_no),
            )
            status = "全部消耗，记录归档" if loan.get("return_condition") == "全部消耗" else "留样保存"
            c.execute("UPDATE samples SET status=?,current_location=?,current_holder=?,updated_at=? WHERE sample_no=?", (status, location, actor, ts, sample_no))
            c.execute(
                """INSERT INTO sample_events(sample_no,actor,action,from_status,to_status,from_location,to_location,details,created_at)
                   VALUES(?,?,'回库确认','待回库确认',?,'回库交接区',?,?,?)""",
                (sample_no, actor, status, location, package_no, ts),
            )
        c.execute("UPDATE task_packages SET status='已回库',return_confirmed_at=?,updated_at=? WHERE package_no=?", (ts, ts, package_no))
        c.execute("UPDATE sample_groups SET status='留样保存',updated_at=? WHERE id=?", (ts, p["group_id"]))
    audit("task_package", package_no, actor, "确认整组样品回库")


# ---------------------- Attachments ----------------------
def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)
    return stem[:160] or "file"


def save_attachment(meta: dict[str, Any], content: bytes, actor: str) -> str:
    sha = hashlib.sha256(content).hexdigest()
    prefix = china_now().strftime("ATT%Y%m%d")
    last = one("SELECT attachment_id FROM attachments WHERE attachment_id LIKE ? ORDER BY attachment_id DESC LIMIT 1", (prefix + "%",))
    seq = int(last["attachment_id"][-4:]) + 1 if last else 1
    attachment_id = f"{prefix}{seq:04d}"
    task_part = _safe_name(meta.get("task_no") or "unassigned")
    folder = ATTACHMENT_DIR / task_part
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{sha[:12]}_{_safe_name(meta.get('original_name','file'))}"
    path = folder / stored
    path.write_bytes(content)
    relative = path.relative_to(ROOT).as_posix()
    with connect() as c:
        c.execute(
            """INSERT INTO attachments(attachment_id,commission_no,package_no,task_no,sample_no,
               attachment_type,original_name,stored_name,relative_path,sha256,captured_at,uploader,
               equipment_software,description,is_original,parent_attachment_id,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                attachment_id, meta.get("commission_no"), meta.get("package_no"), meta.get("task_no"),
                meta.get("sample_no"), meta.get("attachment_type"), meta.get("original_name"), stored,
                relative, sha, str(meta.get("captured_at") or now()), actor,
                meta.get("equipment_software", ""), meta.get("description", ""),
                int(bool(meta.get("is_original", True))), meta.get("parent_attachment_id"), now(),
            ),
        )
    audit("attachment", attachment_id, actor, "上传附件", new_value=meta.get("original_name", ""))
    return attachment_id


def list_attachments(task_no: str | None = None, commission_no: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM attachments WHERE 1=1"; args: list[Any] = []
    if task_no:
        q += " AND task_no=?"; args.append(task_no)
    if commission_no:
        q += " AND commission_no=?"; args.append(commission_no)
    return rows(q + " ORDER BY created_at DESC", args)


def attachment_file(meta: dict[str, Any]) -> Path:
    return ROOT / meta["relative_path"]


# ---------------------- Events and dashboard ----------------------
def sample_events(sample_no: str) -> list[dict[str, Any]]:
    return rows("SELECT * FROM sample_events WHERE sample_no=? ORDER BY id", (sample_no,))


def list_samples() -> list[dict[str, Any]]:
    return rows("SELECT * FROM samples ORDER BY updated_at DESC")


def dashboard_counts() -> dict[str, int]:
    return {
        "commissions": one("SELECT COUNT(*) n FROM commissions")["n"],
        "samples": one("SELECT COUNT(*) n FROM samples WHERE status!='已删除'")["n"],
        "packages": one("SELECT COUNT(*) n FROM task_packages WHERE status='待接收'")["n"],
        "testing": one("SELECT COUNT(*) n FROM task_packages WHERE status='检测中'")["n"],
        "reviews": one("SELECT COUNT(*) n FROM records WHERE status IN ('待复核','更正待复核')")["n"],
        "returns": one("SELECT COUNT(*) n FROM task_packages WHERE status='待回库确认'")["n"],
        "reports": one("SELECT COUNT(*) n FROM reports WHERE status!='已发布'")["n"],
    }


# ---------------------- Report ----------------------
def ensure_report(commission_no: str) -> None:
    if one("SELECT report_no FROM reports WHERE commission_no=?", (commission_no,)):
        return
    tasks0 = rows("SELECT * FROM tasks WHERE commission_no=?", (commission_no,))
    if not tasks0 or any(x["status"] != "已完成" for x in tasks0):
        return
    first = tasks0[0]
    approver = one("SELECT username FROM users WHERE role='批准人' AND enabled=1 ORDER BY username LIMIT 1")
    ts = now()
    with connect() as c:
        c.execute(
            """INSERT INTO reports(report_no,commission_no,status,tester,verifier,approver,created_at,updated_at)
               VALUES(?,?,'待检测员确认',?,?,?,?,?)""",
            (commission_no, commission_no, first["assignee"], first["reviewer"], approver["username"] if approver else "", ts, ts),
        )
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,'',?)", (commission_no, "system", "生成半成品报告", ts))


def report(report_no: str) -> dict[str, Any] | None:
    return one("SELECT * FROM reports WHERE report_no=?", (report_no,))


def list_reports(role: str, username: str) -> list[dict[str, Any]]:
    if role == "实验人员":
        return rows("SELECT * FROM reports WHERE tester=? ORDER BY updated_at DESC", (username,))
    if role == "复核实验员":
        return rows("SELECT * FROM reports WHERE verifier=? ORDER BY updated_at DESC", (username,))
    if role == "批准人":
        return rows("SELECT * FROM reports WHERE approver=? ORDER BY updated_at DESC", (username,))
    return rows("SELECT * FROM reports ORDER BY updated_at DESC")


def update_report_roles(report_no: str, tester: str, verifier: str, approver: str, actor: str) -> None:
    with connect() as c:
        c.execute("UPDATE reports SET tester=?,verifier=?,approver=?,updated_at=? WHERE report_no=?", (tester, verifier, approver, now(), report_no))
    audit("report", report_no, actor, "设置签署人员")


def tester_submit_report(report_no: str, actor: str, category: str, statement: str, conclusion: str, notes: str) -> None:
    r = report(report_no)
    if not r or r["tester"] != actor or r["status"] not in ("待检测员确认", "退回检测员"):
        raise ValueError("当前报告不能由该人员确认")
    with connect() as c:
        c.execute("UPDATE reports SET status='待核验',report_category=?,sample_statement=?,conclusion=?,notes=?,tester_signed_at=?,updated_at=? WHERE report_no=?", (category, statement, conclusion, notes, now(), now(), report_no))
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,'',?)", (report_no, actor, "检测员确认并签署", now()))


def verifier_review_report(report_no: str, actor: str, decision: str, comment: str) -> None:
    r = report(report_no)
    if not r or r["verifier"] != actor or r["status"] != "待核验":
        raise ValueError("当前报告不能核验")
    status = "待批准" if decision == "通过" else "退回检测员"
    with connect() as c:
        c.execute("UPDATE reports SET status=?,verifier_signed_at=?,updated_at=? WHERE report_no=?", (status, now() if decision == "通过" else None, now(), report_no))
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,?,?)", (report_no, actor, "核验" + decision, comment, now()))


def approver_review_report(report_no: str, actor: str, decision: str, comment: str) -> None:
    r = report(report_no)
    if not r or r["approver"] != actor or r["status"] != "待批准":
        raise ValueError("当前报告不能批准")
    status = "已发布" if decision == "批准" else "退回检测员"
    with connect() as c:
        c.execute("UPDATE reports SET status=?,approver_signed_at=?,publish_date=?,updated_at=? WHERE report_no=?", (status, now() if decision == "批准" else None, str(china_today()) if decision == "批准" else None, now(), report_no))
        c.execute("INSERT INTO report_actions(report_no,actor,action,comment,created_at) VALUES(?,?,?,?,?)", (report_no, actor, decision, comment, now()))


def report_actions(report_no: str) -> list[dict[str, Any]]:
    return rows("SELECT * FROM report_actions WHERE report_no=? ORDER BY id", (report_no,))


def report_records(commission_no: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for t in rows("SELECT task_no FROM tasks WHERE commission_no=? ORDER BY task_no", (commission_no,)):
        r = one("SELECT * FROM records WHERE task_no=? AND status='已锁定' ORDER BY version DESC LIMIT 1", (t["task_no"],))
        if r:
            r["payload"] = json.loads(r.get("payload") or "{}")
            result[t["task_no"]] = r
    return result


# ---------------------- Templates/signatures ----------------------
def seed_template(experiment: str, doc_type: str, file_name: str | None, version: str = "A/0") -> None:
    if not file_name:
        return
    with connect() as c:
        if not c.execute("SELECT 1 FROM template_versions WHERE experiment=? AND doc_type=? AND version=?", (experiment, doc_type, version)).fetchone():
            c.execute("INSERT INTO template_versions(experiment,doc_type,file_name,version,effective_date,status,uploader,uploaded_at,note) VALUES(?,?,?,?,?,'现行','system',?,'初始化')", (experiment, doc_type, file_name, version, str(china_today()), now()))


def active_version(experiment: str, doc_type: str) -> dict[str, Any] | None:
    return one("SELECT * FROM template_versions WHERE experiment=? AND doc_type=? AND status='现行' ORDER BY id DESC LIMIT 1", (experiment, doc_type))


def template_for_version(experiment: str, doc_type: str, version: str) -> dict[str, Any] | None:
    return one("SELECT * FROM template_versions WHERE experiment=? AND doc_type=? AND version=? ORDER BY id DESC LIMIT 1", (experiment, doc_type, version))


def all_template_versions() -> list[dict[str, Any]]:
    return rows("SELECT * FROM template_versions ORDER BY experiment,doc_type,id DESC")


def add_template(experiment: str, doc_type: str, file_name: str, version: str, effective_date: str, actor: str, note: str) -> None:
    with connect() as c:
        c.execute("UPDATE template_versions SET status='停用' WHERE experiment=? AND doc_type=? AND status='现行'", (experiment, doc_type))
        c.execute("INSERT INTO template_versions(experiment,doc_type,file_name,version,effective_date,status,uploader,uploaded_at,note) VALUES(?,?,?,?,?,'现行',?,?,?)", (experiment, doc_type, file_name, version, effective_date, actor, now(), note))
    audit("template", experiment + "/" + doc_type, actor, "启用新版本", new_value=version)


def save_signature(username: str, source_file: str, image_file: str | None, actor: str) -> None:
    with connect() as c:
        c.execute("INSERT INTO signatures(username,source_file,image_file,uploaded_by,uploaded_at) VALUES(?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET source_file=excluded.source_file,image_file=excluded.image_file,uploaded_by=excluded.uploaded_by,uploaded_at=excluded.uploaded_at", (username, source_file, image_file, actor, now()))
    audit("signature", username, actor, "更新电子签名")


def signature(username: str) -> dict[str, Any] | None:
    return one("SELECT * FROM signatures WHERE username=?", (username,))


# ---------------------- Document helpers ----------------------
def commission_tasks(commission_no: str) -> list[dict[str, Any]]:
    result = rows("SELECT * FROM tasks WHERE commission_no=? ORDER BY group_no,task_no", (commission_no,))
    for x in result:
        x["sample_nos_list"] = json.loads(x.get("sample_nos") or "[]")
    return result


def commission_tests(commission_no: str) -> list[dict[str, Any]]:
    return rows("""SELECT r.*,g.group_no,g.sample_name,g.model,g.material_name,g.quantity
                   FROM requested_tests r JOIN sample_groups g ON g.id=r.group_id
                   WHERE g.commission_no=? AND g.is_void=0 ORDER BY g.group_no,r.id""", (commission_no,))


def commission_loans(commission_no: str) -> list[dict[str, Any]]:
    return rows("""SELECT l.*,p.commission_no,p.experiments FROM package_loans l JOIN task_packages p ON p.package_no=l.package_no
                   WHERE p.commission_no=? ORDER BY l.borrowed_at,l.sample_no""", (commission_no,))
