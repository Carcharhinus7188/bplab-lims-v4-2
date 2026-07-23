from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from bplab.attachments import ATTACHMENT_TYPES, save_attachment
from bplab.config import (
    COMPANY_CN,
    COMPANY_EN,
    EXPERIMENTS,
    ROLE_LABELS,
    SYSTEM_NAME,
    VERSION,
    active_experiment_options,
)
from bplab.db import (
    authenticate,
    create_session,
    delete_session,
    execute,
    init_db,
    json_load,
    query,
    query_one,
    session_user,
)
from bplab.excel_trace import export_trace_excel
from bplab.record_export import export_record
from bplab.report_export import export_report, official_template_available
from bplab.services import (
    PENDING_REPORT_STATES,
    advance_report,
    auto_build_missing_reports,
    confirm_return,
    create_commission,
    dashboard_counts,
    initial_record_data,
    report_release_gaps,
    review_task,
    save_task_data,
    submit_task,
    task_detail,
)


st.set_page_config(
    page_title=f"{SYSTEM_NAME} {VERSION}",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
:root { --bp-blue:#0B63CE; --bp-navy:#10243E; --bp-soft:#EAF1F9; --bp-green:#16845B; }
.stApp { background: #F5F8FC; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#10243E 0%,#173B63 100%); }
[data-testid="stSidebar"] * { color: #F5FAFF; }
.bp-header { padding:1rem 1.2rem; border-radius:16px; color:white;
  background:linear-gradient(120deg,#0B63CE,#124A83); box-shadow:0 8px 26px rgba(16,36,62,.16); }
.bp-header h1 { margin:0; font-size:1.7rem; }
.bp-header p { margin:.25rem 0 0; opacity:.86; }
.bp-card { background:white; padding:1rem 1.1rem; border:1px solid #DCE6F2; border-radius:14px;
  box-shadow:0 5px 18px rgba(15,45,75,.06); margin-bottom:.8rem; }
.bp-readonly { background:#EEF4FA; border-left:4px solid #0B63CE; padding:.7rem 1rem; border-radius:8px; }
.bp-good { color:#0F7652; font-weight:700; }
.bp-warn { color:#B05A00; font-weight:700; }
.bp-muted { color:#66768A; font-size:.9rem; }
div[data-testid="stMetric"] { background:white; padding:12px; border:1px solid #DCE6F2; border-radius:12px; }
.stButton button { border-radius:10px; }
</style>
""",
    unsafe_allow_html=True,
)

init_db()


def header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="bp-header"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )
    st.write("")


def current_user() -> dict[str, Any] | None:
    token = st.query_params.get("session", "")
    if isinstance(token, list):
        token = token[0] if token else ""
    return session_user(str(token))


def login_page() -> None:
    left, middle, right = st.columns([1, 1.15, 1])
    with middle:
        st.write("")
        st.write("")
        header(COMPANY_CN, f"{COMPANY_EN} · {SYSTEM_NAME} {VERSION}")
        with st.container(border=True):
            st.subheader("登录 / Sign in")
            username = st.text_input("用户名", value="")
            password = st.text_input("密码", type="password")
            if st.button("登录", type="primary", width="stretch"):
                user = authenticate(username.strip(), password)
                if not user:
                    st.error("用户名或密码错误。")
                else:
                    token = create_session(user["id"])
                    st.query_params["session"] = token
                    st.rerun()
            st.caption("刷新浏览器不会退出；主动点击“退出登录”才会结束当前会话。")


def role_users(role: str) -> dict[str, int]:
    rows = query("SELECT id,display_name FROM users WHERE role=? AND active=1 ORDER BY id", (role,))
    return {row["display_name"]: row["id"] for row in rows}


def download_button(label: str, path: Path, mime: str, key: str) -> None:
    st.download_button(label, path.read_bytes(), file_name=path.name, mime=mime, key=key)


def page_home(user: dict[str, Any]) -> None:
    header("工作台", f"{user['display_name']} · {ROLE_LABELS.get(user['role'], user['role'])}")
    counts = dashboard_counts(user)
    cols = st.columns(4)
    items = [
        ("待处理实验", counts["pending_tasks"]),
        ("待复核记录", counts["pending_reviews"]),
        ("待发布报告", counts["pending_reports"]),
        ("累计委托", counts["commissions"]),
    ]
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)
    if counts["pending_reports"]:
        st.info("已有报告进入待发布流程。报告中心会显示待检测员确认、待核验、待批准和退回修改的明细。")
    st.subheader("流程状态")
    st.markdown(
        """
<div class="bp-card">
委托登记 → 样品组与任务 → 实验员简洁记录 → 原始记录复核锁定 → 样品回库 →
自动生成报告草稿 → 检测员确认 → 核验 → 批准发布
</div>
""",
        unsafe_allow_html=True,
    )
    template_rows = []
    for code, cfg in EXPERIMENTS.items():
        status = {"controlled": "可精准回填", "blocked_pages": "待补DOCX", "missing": "母版缺失"}[cfg["template_status"]]
        template_rows.append({"实验": cfg["name"], "原始记录母版": status, "说明": cfg.get("template_note", "受控DOCX已纳入")})
    with st.expander("受控母版状态"):
        st.dataframe(pd.DataFrame(template_rows), width="stretch", hide_index=True)


def page_commissions(user: dict[str, Any]) -> None:
    header("委托与样品", "一次委托可包含多个样品组；生产单位保存在委托层级。")
    tester_options = role_users("tester")
    reviewer_options = role_users("reviewer")
    approver_options = role_users("approver")
    if not tester_options or not reviewer_options or not approver_options:
        st.error("请先建立实验员、复核员和批准人账号。")
        return
    with st.form("commission_form"):
        c1, c2 = st.columns(2)
        client_name = c1.text_input("委托单位 *")
        production_unit = c2.text_input("生产单位 *")
        production_address = st.text_input("生产单位地址")
        d1, d2 = st.columns(2)
        received_date = d1.date_input("收样日期", value=date.today())
        due_date = d2.date_input("要求完成日期", value=date.today())
        p1, p2, p3 = st.columns(3)
        tester_name = p1.selectbox("报告主检/实验员", list(tester_options))
        reviewer_name = p2.selectbox("复核员", list(reviewer_options))
        approver_name = p3.selectbox("批准人", list(approver_options))
        group_count = st.number_input("样品组数量", min_value=1, max_value=6, value=1, step=1)
        group_values = []
        experiment_names = list(active_experiment_options())
        for idx in range(int(group_count)):
            with st.expander(f"样品组 {idx + 1}", expanded=idx == 0):
                a, b = st.columns(2)
                sample_name = a.text_input("样品名称 *", key=f"g_name_{idx}")
                specification = b.text_input("规格型号", key=f"g_spec_{idx}")
                c, d = st.columns(2)
                material = c.text_input("材料名称", key=f"g_mat_{idx}")
                batch_no = d.text_input("批号/生产日期", key=f"g_batch_{idx}")
                e, f = st.columns(2)
                quantity = e.number_input("数量", min_value=1, max_value=100, value=6, key=f"g_qty_{idx}")
                receive_condition = f.radio("接收状态", ["完好", "异常"], horizontal=True, key=f"g_cond_{idx}")
                experiments = st.multiselect("检测项目 *", experiment_names, key=f"g_exp_{idx}")
                receive_note = st.text_input("异常/备注", key=f"g_note_{idx}") if receive_condition == "异常" else ""
                group_values.append(
                    {
                        "sample_name": sample_name,
                        "specification": specification,
                        "material": material,
                        "batch_no": batch_no,
                        "quantity": int(quantity),
                        "receive_condition": receive_condition,
                        "receive_note": receive_note,
                        "experiments": [active_experiment_options()[name] for name in experiments],
                    }
                )
        notes = st.text_area("委托备注")
        submitted = st.form_submit_button("建立委托并下发任务", type="primary")
    if submitted:
        problems = []
        if not client_name.strip():
            problems.append("委托单位")
        if not production_unit.strip():
            problems.append("生产单位")
        for idx, group in enumerate(group_values, start=1):
            if not group["sample_name"].strip():
                problems.append(f"样品组{idx}名称")
            if not group["experiments"]:
                problems.append(f"样品组{idx}检测项目")
        if problems:
            st.error("请补充：" + "、".join(problems))
        else:
            commission_id = create_commission(
                client_name=client_name.strip(),
                production_unit=production_unit.strip(),
                production_address=production_address.strip(),
                received_date=received_date.isoformat(),
                due_date=due_date.isoformat(),
                groups=group_values,
                main_tester_id=tester_options[tester_name],
                reviewer_id=reviewer_options[reviewer_name],
                approver_id=approver_options[approver_name],
                created_by=user["id"],
                notes=notes,
            )
            st.success(f"委托已建立，系统编号：{query_one('SELECT commission_no FROM commissions WHERE id=?',(commission_id,))['commission_no']}")
    st.subheader("现有委托")
    rows = query(
        """SELECT c.id,c.commission_no,cl.name AS client,c.production_unit,c.received_date,c.status,
                  COUNT(DISTINCT sg.id) AS sample_groups,COUNT(DISTINCT t.id) AS tasks
           FROM commissions c JOIN clients cl ON cl.id=c.client_id
           LEFT JOIN sample_groups sg ON sg.commission_id=c.id
           LEFT JOIN tasks t ON t.commission_id=c.id
           GROUP BY c.id ORDER BY c.id DESC"""
    )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_field(item: dict[str, Any], value: Any, key: str, disabled: bool = False) -> Any:
    label = f"{item['label']}{' (' + item['unit'] + ')' if item.get('unit') else ''}"
    kind = item.get("kind", "text")
    kwargs = {"key": key, "disabled": disabled, "help": item.get("help") or None}
    if kind == "number":
        return st.number_input(
            label,
            value=float(value) if value not in (None, "") else None,
            min_value=float(item["min"]) if item.get("min") is not None else None,
            max_value=float(item["max"]) if item.get("max") is not None else None,
            step=float(item.get("step") or 0.001),
            **kwargs,
        )
    if kind == "integer":
        return st.number_input(label, value=int(value) if value not in (None, "") else None, step=1, **kwargs)
    if kind == "select":
        options = item.get("options", [])
        index = options.index(value) if value in options else 0
        return st.selectbox(label, options, index=index, **kwargs)
    if kind == "multiselect":
        return st.multiselect(label, item.get("options", []), default=value or item.get("default") or [], **kwargs)
    if kind == "textarea":
        return st.text_area(label, value=str(value or ""), **kwargs)
    if kind == "date":
        default = date.fromisoformat(str(value)[:10]) if value else date.today()
        return st.date_input(label, value=default, **kwargs).isoformat()
    if kind == "time":
        return st.text_input(label, value=str(value or ""), placeholder="HH:MM", **kwargs)
    if kind == "json":
        initial = value if isinstance(value, str) else json.dumps(value or {}, ensure_ascii=False, indent=2)
        return st.text_area(label, value=initial, height=150, **kwargs)
    return st.text_input(label, value=str(value or ""), **kwargs)


def render_task_editor(task: dict[str, Any], user: dict[str, Any]) -> None:
    cfg = task["config"]
    prefix = f"task_{task['id']}"
    draft_key = f"{prefix}_session_draft"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = deepcopy(task["data"] or initial_record_data(task))
    data = st.session_state[draft_key]
    inherited = task["inherited"]
    st.markdown(
        f"""
<div class="bp-readonly">
<b>{cfg['name']}</b>｜{cfg['method']}<br>
委托：{inherited['commission_no']}　样品：{inherited['sample_name']}　
编号：{'、'.join(inherited['sample_ids'])}<br>
材料：{inherited.get('material','')}　规格：{inherited.get('specification','')}　
地点：{task['location']}　配置版本快照：{task['experiment_version_id']}
</div>
""",
        unsafe_allow_html=True,
    )
    if cfg.get("template_status") != "controlled":
        st.warning(cfg.get("template_note"))
    tabs = st.tabs(["1 任务确认", "2 设备与实验前检查", "3 环境与参数", "4 原始数据", "5 异常与提交"])
    with tabs[0]:
        st.subheader("前序数据（只读）")
        cols = st.columns(3)
        readonly = [
            ("委托单位", inherited.get("client_name")),
            ("生产单位", inherited.get("production_unit")),
            ("样品名称", inherited.get("sample_name")),
            ("规格型号", inherited.get("specification")),
            ("材料名称", inherited.get("material")),
            ("样品数量", inherited.get("quantity")),
            ("检测依据", inherited.get("method")),
            ("检测地点", inherited.get("location")),
            ("实验员", task.get("tester_name")),
        ]
        for idx, (label, val) in enumerate(readonly):
            cols[idx % 3].text_input(label, value=str(val or ""), disabled=True, key=f"{prefix}_ro_{idx}")
        st.caption("这些数据来自委托、样品和任务配置快照，实验员不能在本页面修改。")
    with tabs[1]:
        st.subheader("本次设备快照")
        if not task["equipment"]:
            st.error("当前实验配置尚未关联设备。")
        for item in task["equipment"]:
            st.markdown(
                f"""<div class="bp-card"><b>{item.get('role','设备')}｜{item.get('name','')}</b><br>
型号：{item.get('model') or '待补充'}　管理编号：{item.get('management_no') or '待补充'}　
有效期：{item.get('valid_until') or '待补充'}　状态：{item.get('status')}</div>""",
                unsafe_allow_html=True,
            )
        st.subheader("一键正常确认")
        checks = {}
        for item in cfg.get("prechecks", []):
            current = data.get("prechecks", {}).get(item["key"], item.get("default", True))
            checks[item["key"]] = st.checkbox(item["label"], value=bool(current), key=f"{prefix}_check_{item['key']}")
        data["prechecks"] = checks
        if not all(checks.values()):
            st.warning("有检查项未通过。请在“异常与提交”中记录原因和处置。")
    with tabs[2]:
        st.subheader("环境条件")
        environment = {}
        env_cols = st.columns(2)
        for idx, item in enumerate(cfg.get("environment", [])):
            with env_cols[idx % 2]:
                environment[item["key"]] = render_field(item, data.get("environment", {}).get(item["key"], item.get("default")), f"{prefix}_env_{item['key']}")
        data["environment"] = environment
        st.subheader("受控默认参数")
        deviation = st.toggle("本次存在参数偏离", value=bool(data.get("parameter_deviation")), key=f"{prefix}_deviation")
        data["parameter_deviation"] = deviation
        parameters = {}
        param_cols = st.columns(3)
        for idx, item in enumerate(cfg.get("parameters", [])):
            with param_cols[idx % 3]:
                parameters[item["key"]] = render_field(
                    item,
                    data.get("parameters", {}).get(item["key"], item.get("default")),
                    f"{prefix}_param_{item['key']}",
                    disabled=not deviation,
                )
        data["parameters"] = parameters
        if deviation:
            data["deviation_note"] = st.text_area("偏离内容、批准依据和影响评估 *", value=data.get("deviation_note", ""), key=f"{prefix}_dev_note")
        else:
            data["deviation_note"] = ""
        st.subheader("本次过程数据")
        run = {}
        regular = [item for item in cfg.get("run_fields", []) if item.get("kind") != "json"]
        special = [item for item in cfg.get("run_fields", []) if item.get("kind") == "json"]
        run_cols = st.columns(2)
        for idx, item in enumerate(regular):
            with run_cols[idx % 2]:
                run[item["key"]] = render_field(item, data.get("run", {}).get(item["key"], item.get("default")), f"{prefix}_run_{item['key']}")
        for item in special:
            with st.expander(item["label"], expanded=False):
                run[item["key"]] = render_field(item, data.get("run", {}).get(item["key"], item.get("default")), f"{prefix}_run_{item['key']}")
                st.caption(item.get("help", ""))
        data["run"] = run
    with tabs[3]:
        samples = data.get("samples") or initial_record_data(task)["samples"]
        if not samples:
            st.error("任务中没有样品编号。")
        else:
            completed = 0
            required_keys = [item["key"] for item in cfg.get("sample_fields", []) if item.get("required")]
            for sample in samples:
                if all(sample.get(key) not in (None, "", []) for key in required_keys):
                    completed += 1
            st.progress(completed / len(samples), text=f"已完成 {completed}/{len(samples)} 个样品")
            labels = [sample["sample_id"] + (" ✓" if all(sample.get(key) not in (None, "", []) for key in required_keys) else "") for sample in samples]
            selected_label = st.selectbox("当前样品", labels, key=f"{prefix}_sample_select")
            sample_index = labels.index(selected_label)
            sample = dict(samples[sample_index])
            st.markdown(f"### {sample['sample_id']}")
            field_cols = st.columns(2)
            for idx, item in enumerate(cfg.get("sample_fields", [])):
                with field_cols[idx % 2]:
                    sample[item["key"]] = render_field(item, sample.get(item["key"], item.get("default")), f"{prefix}_sample_{sample_index}_{item['key']}")
            samples[sample_index] = sample
            data["samples"] = samples
            st.caption("使用上方“当前样品”切换；系统会保留本任务内各样品已输入的数据。")
    with tabs[4]:
        data["completed_normally"] = st.radio(
            "实验完成状态",
            [True, False],
            format_func=lambda value: "正常完成" if value else "存在异常",
            horizontal=True,
            index=0 if data.get("completed_normally", True) else 1,
            key=f"{prefix}_normal",
        )
        data["has_exception"] = not data["completed_normally"] or not all(data.get("prechecks", {}).values())
        if data["has_exception"]:
            data["exception_type"] = st.multiselect(
                "异常类型",
                ["设备异常", "样品异常", "环境异常", "参数偏离", "数据异常", "其他"],
                default=data.get("exception_type", []),
                key=f"{prefix}_exception_type",
            )
            data["exception_note"] = st.text_area("异常情况、处置措施和影响评估 *", value=data.get("exception_note", ""), key=f"{prefix}_exception_note")
            data["retest"] = st.checkbox("需要复测/重新制样", value=bool(data.get("retest")), key=f"{prefix}_retest")
            if data["retest"]:
                data["retest_note"] = st.text_area("复测/重新制样说明", value=data.get("retest_note", ""), key=f"{prefix}_retest_note")
        # Preserve all sample cards and prior steps across Streamlit reruns,
        # including when the operator switches the current sample.
        st.session_state[draft_key] = data
        b1, b2 = st.columns(2)
        if b1.button("保存草稿并计算", type="primary", width="stretch", key=f"{prefix}_save"):
            calculations = save_task_data(task["id"], data, user["id"])
            st.success(f"草稿已保存。当前系统判定：{calculations.get('judgment','')}")
            with st.expander("查看计算结果", expanded=True):
                st.json(calculations, expanded=False)
        if b2.button("提交复核", width="stretch", key=f"{prefix}_submit"):
            save_task_data(task["id"], data, user["id"])
            missing = submit_task(task["id"], user["id"])
            if missing:
                st.error("仍有业务必填项未完成：")
                for item in missing[:30]:
                    st.write(f"- {item}")
            else:
                st.session_state.pop(draft_key, None)
                st.success("原始记录已提交复核。")
                st.rerun()


def page_tasks(user: dict[str, Any]) -> None:
    header("我的实验", "只确认真实状态并填写现场原始数据；前序信息、固定参数和计算结果由系统处理。")
    sql = """SELECT t.id,t.task_no,t.status,t.experiment_code,sg.sample_name,
                    c.commission_no,u.display_name AS tester
             FROM tasks t JOIN sample_groups sg ON sg.id=t.sample_group_id
             JOIN commissions c ON c.id=t.commission_id
             LEFT JOIN users u ON u.id=t.tester_id"""
    params = []
    if user["role"] == "tester":
        sql += " WHERE t.tester_id=?"
        params.append(user["id"])
    sql += " ORDER BY t.id DESC"
    rows = query(sql, params)
    if not rows:
        st.info("当前没有实验任务。")
        return
    options = {f"{r['task_no']}｜{EXPERIMENTS[r['experiment_code']]['name']}｜{r['sample_name']}｜{r['status']}": r["id"] for r in rows}
    selected = st.selectbox("选择任务", list(options))
    task = task_detail(options[selected])
    if task["status"] in {"submitted", "locked"}:
        st.info(f"当前状态：{task['status']}。已提交或锁定的记录不能直接覆盖。")
        st.json(task["calculations"], expanded=False)
        return
    render_task_editor(task, user)


def page_reviews(user: dict[str, Any]) -> None:
    header("原始记录复核", "复核通过后锁定快照；退回时保留上一版本和退回意见。")
    sql = """SELECT t.id,t.task_no,t.experiment_code,sg.sample_name,u.display_name AS tester
             FROM tasks t JOIN sample_groups sg ON sg.id=t.sample_group_id
             LEFT JOIN users u ON u.id=t.tester_id WHERE t.status='submitted'"""
    params = []
    if user["role"] == "reviewer":
        sql += " AND t.reviewer_id=?"
        params.append(user["id"])
    rows = query(sql + " ORDER BY t.submitted_at", params)
    if not rows:
        st.success("没有待复核的原始记录。")
        return
    options = {f"{r['task_no']}｜{EXPERIMENTS[r['experiment_code']]['name']}｜{r['sample_name']}": r["id"] for r in rows}
    task = task_detail(options[st.selectbox("待复核记录", list(options))])
    st.markdown(f"### {task['task_no']} · {task['config']['name']}")
    st.write(task["calculations"].get("report_result", ""))
    st.json({"环境": task["data"].get("environment"), "原始数据和计算": task["calculations"].get("samples"), "异常": task["data"].get("exception_note")}, expanded=False)
    comment = st.text_area("复核意见")
    a, b = st.columns(2)
    if a.button("复核通过并锁定", type="primary", width="stretch"):
        review_task(task["id"], user["id"], True, comment)
        st.success("已锁定。")
        st.rerun()
    if b.button("退回修改", width="stretch"):
        if not comment.strip():
            st.error("退回时必须填写原因。")
        else:
            review_task(task["id"], user["id"], False, comment)
            st.warning("已退回实验员。")
            st.rerun()


def page_returns(user: dict[str, Any]) -> None:
    header("样品回库", "整组任务完成复核后确认回库、留样保存或全部消耗；确认后触发报告补建检查。")
    rows = query(
        """SELECT t.id,t.task_no,t.experiment_code,sg.sample_name,sg.sample_ids_json
           FROM tasks t JOIN sample_groups sg ON sg.id=t.sample_group_id
           WHERE t.status='locked' AND t.returned_at IS NULL ORDER BY t.reviewed_at"""
    )
    if not rows:
        st.success("没有待确认回库的任务。")
        return
    options = {f"{r['task_no']}｜{EXPERIMENTS[r['experiment_code']]['name']}｜{r['sample_name']}": r["id"] for r in rows}
    task_id = options[st.selectbox("待回库任务", list(options))]
    condition = st.radio("回库状态", ["留样保存", "部分消耗后回库", "全部消耗"], horizontal=True)
    note = st.text_area("回库/消耗说明")
    if st.button("确认回库", type="primary"):
        confirm_return(task_id, user["id"], condition, note)
        st.success("已确认回库并完成报告补建检查。")
        st.rerun()


def page_reports(user: dict[str, Any]) -> None:
    header("报告中心", "报告直接输出实际结果、标准要求、设备、环境、日期、样品说明和最终结论。")
    auto_build_missing_reports()
    sql = """SELECT r.*,c.commission_no,cl.name AS client_name
             FROM reports r JOIN commissions c ON c.id=r.commission_id
             JOIN clients cl ON cl.id=c.client_id"""
    params = []
    if user["role"] == "tester":
        sql += " WHERE r.tester_id=? OR r.tester_id IS NULL"
        params.append(user["id"])
    elif user["role"] == "reviewer":
        sql += " WHERE r.reviewer_id=? OR r.reviewer_id IS NULL"
        params.append(user["id"])
    elif user["role"] == "approver":
        sql += " WHERE r.approver_id=? OR r.approver_id IS NULL"
        params.append(user["id"])
    rows = query(sql + " ORDER BY r.id DESC", params)
    if not rows:
        st.info("暂无报告。系统仅在全部原始记录锁定且样品全部回库后建立报告草稿。")
        return
    options = {f"{r['report_no']}｜{r['client_name']}｜{r['status']}": r["id"] for r in rows}
    report_id = options[st.selectbox("选择报告", list(options))]
    report = query_one("SELECT * FROM reports WHERE id=?", (report_id,))
    report["snapshot"] = json_load(report["snapshot_json"], {})
    snapshot = report["snapshot"]
    st.subheader(report["report_no"])
    st.write(snapshot.get("final_conclusion", ""))
    result_rows = [
        {
            "检验项目": task["config"].get("name"),
            "标准要求": task["calculations"].get("standard_requirement"),
            "实际结果": task["calculations"].get("report_result"),
            "结论": task["calculations"].get("judgment"),
        }
        for task in snapshot.get("tasks", [])
    ]
    st.dataframe(pd.DataFrame(result_rows), width="stretch", hide_index=True)
    gaps = report_release_gaps(report_id)
    if not official_template_available():
        gaps.append("工作区未收到实验室正式检验报告受控母版")
    if gaps:
        st.warning("正式发布前仍需解决：")
        for item in gaps:
            st.write(f"- {item}")
    preview, _ = export_report(report, official=False)
    download_button("下载非受控报告测试预览", preview, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"report_preview_{report_id}")
    if official_template_available() and not gaps:
        official, _ = export_report(report, official=True)
        download_button("下载正式检验报告", official, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"report_official_{report_id}")
    comment = st.text_area("意见/退回原因", key=f"report_comment_{report_id}")
    status = report["status"]
    if status in {"待检测员确认", "退回检测员"} and user["role"] in {"tester", "admin"}:
        if st.button("检测员确认并提交核验", type="primary"):
            if gaps:
                st.error("报告数据或受控母版不完整，不能提交。")
            else:
                advance_report(report_id, user, "submit", comment)
                st.rerun()
    elif status == "待核验" and user["role"] in {"reviewer", "admin"}:
        a, b = st.columns(2)
        if a.button("核验通过", type="primary"):
            advance_report(report_id, user, "review_pass", comment)
            st.rerun()
        if b.button("退回检测员"):
            if not comment.strip():
                st.error("退回必须填写原因。")
            else:
                advance_report(report_id, user, "return", comment)
                st.rerun()
    elif status == "待批准" and user["role"] in {"approver", "admin"}:
        a, b = st.columns(2)
        if a.button("批准发布", type="primary"):
            if gaps:
                st.error("正式发布条件未满足。")
            else:
                advance_report(report_id, user, "approve", comment)
                st.rerun()
        if b.button("退回检测员"):
            if not comment.strip():
                st.error("退回必须填写原因。")
            else:
                advance_report(report_id, user, "return", comment)
                st.rerun()


def page_attachments(user: dict[str, Any]) -> None:
    header("附件追溯", "只管理图片、截图、曲线和原始数据文件；不设置软件或设备字段。")
    commissions = query("SELECT id,commission_no FROM commissions ORDER BY id DESC")
    if not commissions:
        st.info("请先建立委托。")
        return
    commission_map = {row["commission_no"]: row["id"] for row in commissions}
    commission_no = st.selectbox("委托编号", list(commission_map))
    commission_id = commission_map[commission_no]
    tasks = query("SELECT id,task_no,sample_group_id,inherited_snapshot_json FROM tasks WHERE commission_id=? ORDER BY id", (commission_id,))
    task_map = {"不绑定具体任务": None} | {row["task_no"]: row["id"] for row in tasks}
    task_label = st.selectbox("关联任务", list(task_map))
    task_id = task_map[task_label]
    selected_task = next((row for row in tasks if row["id"] == task_id), None)
    inherited = json_load(selected_task["inherited_snapshot_json"], {}) if selected_task else {}
    sample_options = ["不绑定具体样品"] + inherited.get("sample_ids", [])
    sample_id = st.selectbox("关联样品", sample_options)
    attachment_type = st.selectbox("附件类型", ATTACHMENT_TYPES)
    uploaded = st.file_uploader("选择文件")
    description = st.text_area("内容说明")
    source_relation = st.radio("文件关系", ["原始文件", "处理文件"], horizontal=True)
    if st.button("上传并建立追溯索引", type="primary"):
        if not uploaded:
            st.error("请选择文件。")
        else:
            save_attachment(
                commission_id=commission_id,
                task_id=task_id,
                sample_group_id=selected_task["sample_group_id"] if selected_task else None,
                sample_id="" if sample_id == "不绑定具体样品" else sample_id,
                attachment_type=attachment_type,
                original_filename=uploaded.name,
                content=uploaded.getvalue(),
                uploaded_by=user["id"],
                description=description,
                source_relation=source_relation,
            )
            st.success("附件已保存，SHA-256已生成。")
    rows = query(
        """SELECT attachment_no,attachment_type,original_filename,sample_id,generated_at,description,sha256,review_status
           FROM attachments WHERE commission_id=? ORDER BY id DESC""",
        (commission_id,),
    )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def page_documents(user: dict[str, Any]) -> None:
    header("单据中心", "原始记录、报告和内部追溯Excel从同一数据快照生成。")
    auto_build_missing_reports()
    commissions = query(
        """SELECT c.id,c.commission_no,cl.name AS client FROM commissions c
           JOIN clients cl ON cl.id=c.client_id ORDER BY c.id DESC"""
    )
    if not commissions:
        st.info("暂无委托。")
        return
    options = {f"{r['commission_no']}｜{r['client']}": r["id"] for r in commissions}
    commission_id = options[st.selectbox("选择委托", list(options))]
    st.subheader("内部实验数据追溯Excel")
    trace = export_trace_excel(commission_id)
    download_button("下载内部实验数据追溯工作簿", trace, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"trace_{commission_id}")
    st.subheader("原始记录")
    tasks = query("SELECT id,task_no,status,experiment_code FROM tasks WHERE commission_id=? ORDER BY id", (commission_id,))
    for row in tasks:
        cfg = EXPERIMENTS[row["experiment_code"]]
        with st.expander(f"{row['task_no']}｜{cfg['name']}｜{row['status']}"):
            if row["status"] not in {"submitted", "locked"}:
                st.info("记录尚未提交。")
                continue
            task = task_detail(row["id"])
            if cfg["template_status"] != "controlled":
                st.warning(cfg.get("template_note"))
                continue
            try:
                output, manifest = export_record(task)
                download_button("下载原始记录Word", output, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"record_{row['id']}")
                st.caption(f"母版结构校验：{'通过' if manifest['structure_preserved'] else '失败'}")
            except Exception as exc:
                st.error(str(exc))
    report = query_one("SELECT * FROM reports WHERE commission_id=?", (commission_id,))
    if report:
        st.subheader("检验报告")
        report["snapshot"] = json_load(report["snapshot_json"], {})
        preview, _ = export_report(report, official=False)
        download_button("下载非受控报告测试预览", preview, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"docs_report_{commission_id}")


def page_config(user: dict[str, Any]) -> None:
    header("基础配置", "实验、设备和关联关系动态维护；新任务冻结现行配置快照，历史记录不被覆盖。")
    tabs = st.tabs(["设备库", "实验配置版本", "用户"])
    with tabs[0]:
        equipment = query("SELECT * FROM equipment ORDER BY management_no")
        st.dataframe(pd.DataFrame(equipment), width="stretch", hide_index=True)
        with st.expander("新增设备"):
            with st.form("add_equipment"):
                cols = st.columns(3)
                management_no = cols[0].text_input("管理编号")
                name = cols[1].text_input("设备名称")
                model = cols[2].text_input("型号/规格")
                measurement_range = cols[0].text_input("量程/准确度")
                certificate = cols[1].text_input("校准/核查证书编号")
                traceability = cols[2].text_input("溯源机构")
                valid_until = cols[0].text_input("有效期至 YYYY-MM-DD")
                status = cols[1].selectbox("状态", ["启用", "停用", "维修", "报废"])
                if st.form_submit_button("保存设备"):
                    execute(
                        """INSERT INTO equipment(
                            management_no,name,model,measurement_range,calibration_certificate,
                            traceability_body,valid_until,status,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,datetime('now'))""",
                        (management_no, name, model, measurement_range, certificate, traceability, valid_until, status),
                    )
                    st.success("设备已新增。")
                    st.rerun()
    with tabs[1]:
        versions = query("SELECT id,experiment_code,version,status,change_note,approved_at FROM experiment_versions ORDER BY experiment_code,id DESC")
        for row in versions:
            row["实验名称"] = EXPERIMENTS.get(row["experiment_code"], {}).get("name", row["experiment_code"])
        st.dataframe(pd.DataFrame(versions), width="stretch", hide_index=True)
        st.caption("V5.7保留版本化配置表和设备关联表。发布新版本后，只影响后续新任务；历史任务继续使用原快照。")
    with tabs[2]:
        users = query("SELECT username,display_name,role,active,created_at FROM users ORDER BY id")
        for row in users:
            row["role"] = ROLE_LABELS.get(row["role"], row["role"])
        st.dataframe(pd.DataFrame(users), width="stretch", hide_index=True)


def main() -> None:
    user = current_user()
    if not user:
        login_page()
        return
    with st.sidebar:
        st.markdown(f"## {SYSTEM_NAME} {VERSION}")
        st.caption(COMPANY_CN)
        st.caption(COMPANY_EN)
        st.divider()
        st.write(f"**{user['display_name']}**")
        st.caption(ROLE_LABELS.get(user["role"], user["role"]))
        pages = {"工作台": page_home}
        if user["role"] in {"admin", "sample_manager"}:
            pages["委托与样品"] = page_commissions
        if user["role"] in {"admin", "tester"}:
            pages["我的实验"] = page_tasks
        if user["role"] in {"admin", "reviewer"}:
            pages["原始记录复核"] = page_reviews
        if user["role"] in {"admin", "sample_manager"}:
            pages["样品回库"] = page_returns
        pages["报告中心"] = page_reports
        pages["附件追溯"] = page_attachments
        pages["单据中心"] = page_documents
        if user["role"] == "admin":
            pages["基础配置"] = page_config
        selected = st.radio("导航", list(pages), label_visibility="collapsed")
        st.divider()
        if st.button("退出登录", width="stretch"):
            token = st.query_params.get("session", "")
            delete_session(str(token))
            st.query_params.clear()
            st.rerun()
    pages[selected](user)


if __name__ == "__main__":
    main()
