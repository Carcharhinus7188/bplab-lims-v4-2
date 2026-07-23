from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from .calculations import calculate, validate_record
from .config import EXPERIMENTS
from .db import audit, connect, json_load, now_iso, query, query_one


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def current_experiment_version(code: str, path: Path | None = None) -> dict[str, Any]:
    row = query_one(
        """SELECT * FROM experiment_versions
           WHERE experiment_code=? AND status='current'
           ORDER BY id DESC LIMIT 1""",
        (code,),
        path,
    )
    if not row:
        raise ValueError(f"实验 {code} 没有现行配置版本")
    row["config"] = json_load(row.pop("config_json"), {})
    return row


def equipment_snapshot(version_id: int, path: Path | None = None) -> list[dict[str, Any]]:
    return query(
        """SELECT e.*,b.role,b.required
           FROM experiment_equipment b
           JOIN equipment e ON e.id=b.equipment_id
           WHERE b.experiment_version_id=?
           ORDER BY b.required DESC,b.id""",
        (version_id,),
        path,
    )


def equipment_release_gaps(snapshot: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for item in snapshot:
        if not item.get("required"):
            continue
        prefix = f"{item.get('management_no')} {item.get('name')}"
        if item.get("status") != "启用":
            gaps.append(f"{prefix}当前状态为“{item.get('status')}”")
        for key, label in [
            ("model", "型号/规格"),
            ("calibration_certificate", "校准/核查证书编号"),
            ("traceability_body", "溯源机构"),
            ("valid_until", "有效期"),
        ]:
            if not str(item.get(key, "")).strip():
                gaps.append(f"{prefix}缺少{label}")
    return gaps


def _next_commission_no(conn) -> str:
    prefix = f"BP{date.today():%Y%m%d}"
    row = conn.execute(
        "SELECT commission_no FROM commissions WHERE commission_no LIKE ? ORDER BY commission_no DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    seq = int(row["commission_no"][-3:]) + 1 if row else 1
    return f"{prefix}{seq:03d}"


def create_commission(
    *,
    client_name: str,
    production_unit: str,
    production_address: str,
    received_date: str,
    due_date: str,
    groups: list[dict[str, Any]],
    main_tester_id: int,
    reviewer_id: int,
    approver_id: int,
    created_by: int,
    notes: str = "",
    path: Path | None = None,
) -> int:
    if not groups:
        raise ValueError("至少需要一个样品组")
    with connect(path) as conn:
        client = conn.execute("SELECT id FROM clients WHERE name=?", (client_name,)).fetchone()
        if client:
            client_id = client["id"]
        else:
            client_id = conn.execute(
                "INSERT INTO clients(name,created_at) VALUES(?,?)",
                (client_name, now_iso()),
            ).lastrowid
        commission_no = _next_commission_no(conn)
        commission_id = conn.execute(
            """INSERT INTO commissions(
                commission_no,client_id,production_unit,production_address,received_date,due_date,
                main_tester_id,reviewer_id,approver_id,status,notes,created_by,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                commission_no,
                client_id,
                production_unit,
                production_address,
                received_date,
                due_date,
                main_tester_id,
                reviewer_id,
                approver_id,
                "in_progress",
                notes,
                created_by,
                now_iso(),
            ),
        ).lastrowid
        task_seq = 1
        for group_no, group in enumerate(groups, start=1):
            quantity = max(1, int(group["quantity"]))
            sample_ids = [f"{commission_no}-{group_no:02d}-{idx:02d}" for idx in range(1, quantity + 1)]
            group_id = conn.execute(
                """INSERT INTO sample_groups(
                    commission_id,group_no,sample_name,specification,material,batch_no,quantity,
                    unit,receive_condition,receive_note,sample_ids_json,shelf_status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    commission_id,
                    group_no,
                    group["sample_name"],
                    group.get("specification", ""),
                    group.get("material", ""),
                    group.get("batch_no", ""),
                    quantity,
                    group.get("unit", "件"),
                    group.get("receive_condition", "完好"),
                    group.get("receive_note", ""),
                    _json(sample_ids),
                    "在库",
                ),
            ).lastrowid
            for code in group.get("experiments", []):
                version = conn.execute(
                    """SELECT * FROM experiment_versions WHERE experiment_code=? AND status='current'
                       ORDER BY id DESC LIMIT 1""",
                    (code,),
                ).fetchone()
                if not version:
                    raise ValueError(f"实验 {code} 无现行配置")
                cfg = json.loads(version["config_json"])
                equipment = [
                    dict(row)
                    for row in conn.execute(
                        """SELECT e.*,b.role,b.required FROM experiment_equipment b
                           JOIN equipment e ON e.id=b.equipment_id
                           WHERE b.experiment_version_id=? ORDER BY b.required DESC,b.id""",
                        (version["id"],),
                    ).fetchall()
                ]
                inherited = {
                    "commission_no": commission_no,
                    "client_name": client_name,
                    "production_unit": production_unit,
                    "production_address": production_address,
                    "received_date": received_date,
                    "due_date": due_date,
                    "sample_group_no": group_no,
                    "sample_name": group["sample_name"],
                    "specification": group.get("specification", ""),
                    "material": group.get("material", ""),
                    "batch_no": group.get("batch_no", ""),
                    "quantity": quantity,
                    "sample_ids": sample_ids,
                    "experiment_name": cfg["name"],
                    "method": cfg["method"],
                    "basis": cfg["basis"],
                    "location": cfg["location"],
                }
                conn.execute(
                    """INSERT INTO tasks(
                        task_no,commission_id,sample_group_id,experiment_code,experiment_version_id,
                        tester_id,reviewer_id,location,status,config_snapshot_json,equipment_snapshot_json,
                        inherited_snapshot_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        f"{commission_no}-T{task_seq:02d}",
                        commission_id,
                        group_id,
                        code,
                        version["id"],
                        main_tester_id,
                        reviewer_id,
                        cfg["location"],
                        "pending",
                        version["config_json"],
                        _json(equipment),
                        _json(inherited),
                        now_iso(),
                    ),
                )
                task_seq += 1
        conn.execute(
            "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (created_by, "create", "commission", str(commission_id), _json({"commission_no": commission_no}), now_iso()),
        )
        return int(commission_id)


def task_detail(task_id: int, path: Path | None = None) -> dict[str, Any]:
    row = query_one(
        """SELECT t.*,u.display_name AS tester_name,r.display_name AS reviewer_name,
                  c.commission_no,c.production_unit,cl.name AS client_name,
                  sg.sample_name,sg.specification,sg.material,sg.batch_no,sg.quantity,sg.sample_ids_json
           FROM tasks t
           JOIN commissions c ON c.id=t.commission_id
           JOIN clients cl ON cl.id=c.client_id
           JOIN sample_groups sg ON sg.id=t.sample_group_id
           LEFT JOIN users u ON u.id=t.tester_id
           LEFT JOIN users r ON r.id=t.reviewer_id
           WHERE t.id=?""",
        (task_id,),
        path,
    )
    if not row:
        raise ValueError("任务不存在")
    for source, target, default in [
        ("config_snapshot_json", "config", {}),
        ("equipment_snapshot_json", "equipment", []),
        ("inherited_snapshot_json", "inherited", {}),
        ("data_json", "data", {}),
        ("calculations_json", "calculations", {}),
    ]:
        row[target] = json_load(row.pop(source), default)
    row["sample_ids"] = json_load(row.get("sample_ids_json"), [])
    return row


def initial_record_data(task: dict[str, Any]) -> dict[str, Any]:
    config = task["config"]
    parameters = {item["key"]: item.get("default") for item in config.get("parameters", [])}
    environment = {item["key"]: item.get("default") for item in config.get("environment", [])}
    run = {item["key"]: item.get("default") for item in config.get("run_fields", [])}
    prechecks = {item["key"]: bool(item.get("default", False)) for item in config.get("prechecks", [])}
    sample_ids = task.get("sample_ids", task.get("inherited", {}).get("sample_ids", []))
    slots = min(len(sample_ids), int(config.get("sample_slots", len(sample_ids))))
    samples = []
    for sample_id in sample_ids[:slots]:
        sample = {"sample_id": sample_id}
        for item in config.get("sample_fields", []):
            sample[item["key"]] = item.get("default")
        samples.append(sample)
    return {
        "environment": environment,
        "parameters": parameters,
        "prechecks": prechecks,
        "run": run,
        "samples": samples,
        "parameter_deviation": False,
        "deviation_note": "",
        "has_exception": False,
        "exception_type": [],
        "exception_note": "",
        "retest": False,
        "retest_note": "",
        "completed_normally": True,
    }


def save_task_data(
    task_id: int,
    data: dict[str, Any],
    actor_id: int,
    path: Path | None = None,
) -> dict[str, Any]:
    task = task_detail(task_id, path)
    if task["status"] in {"locked", "returned"}:
        raise ValueError("记录已锁定，不能直接覆盖；请走数据更正流程")
    calculations = calculate(task["experiment_code"], data, task["config"])
    with connect(path) as conn:
        conn.execute(
            """UPDATE tasks SET data_json=?,calculations_json=?,judgment=?,
               status=CASE WHEN status='pending' THEN 'draft' ELSE status END,
               started_at=COALESCE(started_at,?) WHERE id=?""",
            (_json(data), _json(calculations), calculations.get("judgment", ""), now_iso(), task_id),
        )
        conn.execute(
            "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor_id, "save_draft", "task", str(task_id), _json({"data_hash": _hash(data)}), now_iso()),
        )
    return calculations


def submit_task(task_id: int, actor_id: int, path: Path | None = None) -> list[str]:
    task = task_detail(task_id, path)
    missing = validate_record(task["data"], task["config"])
    if missing:
        return missing
    calculations = calculate(task["experiment_code"], task["data"], task["config"])
    snapshot = {"data": task["data"], "calculations": calculations, "inherited": task["inherited"], "equipment": task["equipment"]}
    with connect(path) as conn:
        current = conn.execute("SELECT COALESCE(MAX(version),0) AS v FROM record_versions WHERE task_id=?", (task_id,)).fetchone()
        version = int(current["v"]) + 1
        conn.execute(
            """INSERT INTO record_versions(
                task_id,version,status,data_snapshot_json,data_hash,operator_id,created_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (task_id, version, "submitted", _json(snapshot), _hash(snapshot), actor_id, now_iso()),
        )
        conn.execute(
            "UPDATE tasks SET status='submitted',submitted_at=?,calculations_json=?,judgment=? WHERE id=?",
            (now_iso(), _json(calculations), calculations.get("judgment", ""), task_id),
        )
        conn.execute(
            "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor_id, "submit", "task", str(task_id), _json({"record_version": version}), now_iso()),
        )
    return []


def review_task(
    task_id: int,
    reviewer_id: int,
    approved: bool,
    comment: str,
    path: Path | None = None,
) -> None:
    task = task_detail(task_id, path)
    if task["status"] != "submitted":
        raise ValueError("只有已提交记录可以复核")
    target = "locked" if approved else "returned_for_correction"
    with connect(path) as conn:
        conn.execute("UPDATE tasks SET status=?,reviewed_at=? WHERE id=?", (target, now_iso() if approved else None, task_id))
        conn.execute(
            """UPDATE record_versions SET status=?,review_comment=?
               WHERE task_id=? AND version=(SELECT MAX(version) FROM record_versions WHERE task_id=?)""",
            ("locked" if approved else "returned", comment, task_id, task_id),
        )
        conn.execute(
            "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (reviewer_id, "review_pass" if approved else "review_return", "task", str(task_id), _json({"comment": comment}), now_iso()),
        )
    if approved:
        auto_build_missing_reports(path=path)


def confirm_return(
    task_id: int,
    actor_id: int,
    return_condition: str,
    note: str,
    path: Path | None = None,
) -> None:
    task = task_detail(task_id, path)
    if task["status"] != "locked":
        raise ValueError("只有复核锁定的任务可以确认回库")
    with connect(path) as conn:
        conn.execute(
            "UPDATE tasks SET returned_at=?,return_condition=?,return_note=? WHERE id=?",
            (now_iso(), return_condition, note, task_id),
        )
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE sample_group_id=? AND returned_at IS NULL",
            (task["sample_group_id"],),
        ).fetchone()["n"]
        if remaining == 0:
            conn.execute(
                "UPDATE sample_groups SET shelf_status=? WHERE id=?",
                ("留样保存" if return_condition != "全部消耗" else "全部消耗", task["sample_group_id"]),
            )
        conn.execute(
            "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor_id, "return_sample", "task", str(task_id), _json({"condition": return_condition, "note": note}), now_iso()),
        )
    auto_build_missing_reports(path=path)


def report_readiness(commission_id: int, path: Path | None = None) -> tuple[bool, list[str]]:
    tasks = query("SELECT status,returned_at FROM tasks WHERE commission_id=?", (commission_id,), path)
    gaps = []
    if not tasks:
        gaps.append("委托没有实验任务")
    if any(task["status"] != "locked" for task in tasks):
        gaps.append("仍有原始记录未复核锁定")
    if any(not task["returned_at"] for task in tasks):
        gaps.append("仍有任务未确认样品回库/消耗")
    return not gaps, gaps


def build_report_snapshot(commission_id: int, path: Path | None = None) -> dict[str, Any]:
    commission = query_one(
        """SELECT c.*,cl.name AS client_name,cl.address AS client_address,
                  t.display_name AS tester_name,r.display_name AS reviewer_name,a.display_name AS approver_name
           FROM commissions c JOIN clients cl ON cl.id=c.client_id
           LEFT JOIN users t ON t.id=c.main_tester_id
           LEFT JOIN users r ON r.id=c.reviewer_id
           LEFT JOIN users a ON a.id=c.approver_id
           WHERE c.id=?""",
        (commission_id,),
        path,
    )
    if not commission:
        raise ValueError("委托不存在")
    groups = query("SELECT * FROM sample_groups WHERE commission_id=? ORDER BY group_no", (commission_id,), path)
    tasks = query(
        """SELECT id,task_no,experiment_code,location,judgment,started_at,submitted_at,reviewed_at,
                  config_snapshot_json,equipment_snapshot_json,inherited_snapshot_json,data_json,calculations_json
           FROM tasks WHERE commission_id=? ORDER BY id""",
        (commission_id,),
        path,
    )
    for task in tasks:
        task["config"] = json_load(task.pop("config_snapshot_json"), {})
        task["equipment"] = json_load(task.pop("equipment_snapshot_json"), [])
        task["inherited"] = json_load(task.pop("inherited_snapshot_json"), {})
        task["data"] = json_load(task.pop("data_json"), {})
        task["calculations"] = json_load(task.pop("calculations_json"), {})
    dates = [task["started_at"][:10] for task in tasks if task.get("started_at")]
    equipment = {}
    environments = []
    for task in tasks:
        for item in task["equipment"]:
            equipment[item.get("management_no") or f"id-{item.get('id')}"] = item
        env = task["data"].get("environment", {})
        environments.append(
            {
                "experiment": task["config"].get("name", task["experiment_code"]),
                "location": task["location"],
                "temperature_before": env.get("temperature_before"),
                "temperature_after": env.get("temperature_after"),
                "humidity_before": env.get("humidity_before"),
                "humidity_after": env.get("humidity_after"),
                "other": "无异常" if not task["data"].get("has_exception") else task["data"].get("exception_note", ""),
            }
        )
    judgments = [task["calculations"].get("judgment", task.get("judgment")) for task in tasks]
    final = "不符合" if any(value == "不符合" for value in judgments) else (
        "需复检/补充" if any(value in {"需复试", "需复检", "无法判定", "需补足6个有效试样"} for value in judgments) else "符合"
    )
    sample_note = "；".join(
        f"样品组{g['group_no']}：{g['sample_name']}，{g['quantity']}{g['unit']}，接收状态{g['receive_condition']}，回库状态{g['shelf_status']}"
        for g in groups
    )
    conclusion = "；".join(
        f"{task['config'].get('name', task['experiment_code'])}{task['calculations'].get('judgment', '')}"
        for task in tasks
    )
    return {
        "commission": commission,
        "groups": groups,
        "tasks": tasks,
        "equipment": list(equipment.values()),
        "environments": environments,
        "test_date_start": min(dates) if dates else "",
        "test_date_end": max(dates) if dates else "",
        "sample_note": sample_note,
        "final_judgment": final,
        "final_conclusion": f"所检项目结果如下：{conclusion}。",
        "snapshot_created_at": now_iso(),
    }


def auto_build_missing_reports(path: Path | None = None) -> list[int]:
    candidates = query("SELECT id,commission_no,main_tester_id,reviewer_id,approver_id FROM commissions", path=path)
    created: list[int] = []
    with connect(path) as conn:
        for commission in candidates:
            existing = conn.execute("SELECT id FROM reports WHERE commission_id=?", (commission["id"],)).fetchone()
            ready, _ = report_readiness(commission["id"], path)
            if not ready or existing:
                continue
            snapshot = build_report_snapshot(commission["id"], path)
            report_no = f"{commission['commission_no']}-R"
            report_id = conn.execute(
                """INSERT INTO reports(
                    commission_id,report_no,status,tester_id,reviewer_id,approver_id,
                    snapshot_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    commission["id"],
                    report_no,
                    "待检测员确认",
                    commission["main_tester_id"],
                    commission["reviewer_id"],
                    commission["approver_id"],
                    _json(snapshot),
                    now_iso(),
                ),
            ).lastrowid
            conn.execute("UPDATE commissions SET status='reporting' WHERE id=?", (commission["id"],))
            conn.execute(
                "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(NULL,?,?,?,?,?)",
                ("auto_create", "report", str(report_id), _json({"report_no": report_no}), now_iso()),
            )
            created.append(int(report_id))
    return created


PENDING_REPORT_STATES = ["待检测员确认", "退回检测员", "待核验", "待批准"]


def dashboard_counts(user: dict[str, Any], path: Path | None = None) -> dict[str, int]:
    auto_build_missing_reports(path)
    role, user_id = user["role"], user["id"]
    task_filter = ""
    params: list[Any] = []
    if role == "tester":
        task_filter = " AND tester_id=?"
        params.append(user_id)
    elif role == "reviewer":
        task_filter = " AND reviewer_id=?"
        params.append(user_id)
    pending_tasks = query_one(
        f"SELECT COUNT(*) AS n FROM tasks WHERE status IN ('pending','draft','returned_for_correction'){task_filter}",
        params,
        path,
    )["n"]
    review_tasks = query_one(
        f"SELECT COUNT(*) AS n FROM tasks WHERE status='submitted'{task_filter}",
        params,
        path,
    )["n"]
    placeholders = ",".join("?" for _ in PENDING_REPORT_STATES)
    report_sql = f"SELECT COUNT(*) AS n FROM reports WHERE status IN ({placeholders})"
    report_params: list[Any] = list(PENDING_REPORT_STATES)
    if role == "tester":
        report_sql += " AND (tester_id=? OR tester_id IS NULL)"
        report_params.append(user_id)
    elif role == "reviewer":
        report_sql += " AND (reviewer_id=? OR reviewer_id IS NULL)"
        report_params.append(user_id)
    elif role == "approver":
        report_sql += " AND (approver_id=? OR approver_id IS NULL)"
        report_params.append(user_id)
    pending_reports = query_one(report_sql, report_params, path)["n"]
    return {
        "pending_tasks": int(pending_tasks),
        "pending_reviews": int(review_tasks),
        "pending_reports": int(pending_reports),
        "commissions": int(query_one("SELECT COUNT(*) AS n FROM commissions", path=path)["n"]),
    }


def advance_report(
    report_id: int,
    actor: dict[str, Any],
    action: str,
    comment: str = "",
    path: Path | None = None,
) -> str:
    report = query_one("SELECT * FROM reports WHERE id=?", (report_id,), path)
    if not report:
        raise ValueError("报告不存在")
    status = report["status"]
    target = status
    timestamp_field = None
    if action == "submit" and status in {"待检测员确认", "退回检测员"}:
        target, timestamp_field = "待核验", "tester_signed_at"
    elif action == "review_pass" and status == "待核验":
        target, timestamp_field = "待批准", "reviewer_signed_at"
    elif action == "approve" and status == "待批准":
        target, timestamp_field = "已发布", "approver_signed_at"
    elif action == "return" and status in {"待核验", "待批准"}:
        target = "退回检测员"
    else:
        raise ValueError("当前报告状态不能执行该操作")
    with connect(path) as conn:
        if timestamp_field:
            conn.execute(
                f"UPDATE reports SET status=?,{timestamp_field}=?,return_comment=? WHERE id=?",
                (target, now_iso(), comment, report_id),
            )
        else:
            conn.execute("UPDATE reports SET status=?,return_comment=? WHERE id=?", (target, comment, report_id))
        if target == "已发布":
            conn.execute("UPDATE reports SET published_at=? WHERE id=?", (now_iso(), report_id))
            conn.execute("UPDATE commissions SET status='completed' WHERE id=?", (report["commission_id"],))
        conn.execute(
            "INSERT INTO audit_log(actor_id,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            (actor["id"], action, "report", str(report_id), _json({"from": status, "to": target, "comment": comment}), now_iso()),
        )
    return target


def report_release_gaps(report_id: int, path: Path | None = None) -> list[str]:
    report = query_one("SELECT * FROM reports WHERE id=?", (report_id,), path)
    if not report:
        return ["报告不存在"]
    snapshot = json_load(report["snapshot_json"], {})
    gaps: list[str] = []
    for task in snapshot.get("tasks", []):
        cfg = task.get("config", {})
        calc = task.get("calculations", {})
        name = cfg.get("name", task.get("experiment_code", "实验"))
        if not calc.get("report_result") or "详见原始记录" in calc.get("report_result", ""):
            gaps.append(f"{name}缺少可独立表达的实际检验结果")
        if not calc.get("standard_requirement"):
            gaps.append(f"{name}缺少标准要求")
        if not task.get("data", {}).get("environment"):
            gaps.append(f"{name}缺少环境数据")
    gaps.extend(equipment_release_gaps(snapshot.get("equipment", [])))
    if not snapshot.get("test_date_start"):
        gaps.append("缺少检验日期")
    if not snapshot.get("sample_note"):
        gaps.append("缺少样品情况说明")
    if not snapshot.get("final_conclusion"):
        gaps.append("缺少最终检验结论")
    return gaps

