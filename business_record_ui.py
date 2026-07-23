# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from typing import Any

import streamlit as st

from business_record_engine import (
    AUTO_ROW_KEYS,
    OPTIONAL_ROW_KEYS,
    calculate_business_record,
    fixed_and_manual_fields,
    visible_row_fields,
)
from experiment_engine import schema


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _widget(field: dict[str, Any], value: Any, key: str):
    typ = field.get("type", "text")
    label = field.get("label", field.get("key", "字段"))
    help_text = field.get("help")
    if typ == "number":
        return st.number_input(label, value=_safe_number(value, field.get("default", 0.0)), key=key, help=help_text)
    if typ == "select":
        options = field.get("options") or [""]
        selected = value if value in options else options[0]
        return st.selectbox(label, options, index=options.index(selected), key=key, help=help_text)
    if typ == "multiselect":
        options = field.get("options") or []
        default = value if isinstance(value, list) else []
        return st.multiselect(label, options, default=default, key=key, help=help_text)
    if typ == "checkbox":
        return st.checkbox(label, value=bool(value), key=key, help=help_text)
    if typ in ("textarea",):
        return st.text_area(label, value=str(value or ""), key=key, help=help_text)
    return st.text_input(label, value=str(value or ""), key=key, help=help_text)


def render_readonly_summary(task: dict[str, Any], group: dict[str, Any], commission: dict[str, Any], package: dict[str, Any], config: dict[str, Any]):
    st.subheader("任务信息")
    cols = st.columns(3)
    values = [
        ("委托单位", commission.get("client_name", "")),
        ("生产单位", commission.get("production_org_name", "")),
        ("样品名称", group.get("sample_name", "")),
        ("规格型号", group.get("model", "")),
        ("材料名称", task.get("material_name", "")),
        ("实体样品编号", "、".join(task.get("sample_nos_list") or [])),
        ("检测方法", task.get("method_code", "")),
        ("检测依据", task.get("standard", "")),
        ("检测地点", package.get("detection_location", "")),
    ]
    for index, (label, value) in enumerate(values):
        with cols[index % 3]:
            st.text_input(label, value=str(value or ""), disabled=True, key=f"readonly_{task['task_no']}_{index}")
    st.caption(f"实验配置版本：{config.get('config_version','')}｜原始记录模板：{config.get('record_template_file','')}。以上信息来自委托、入库、任务和配置快照，实验员不可修改。")


def render_task_confirmations(record: dict[str, Any], key_prefix: str) -> dict[str, bool]:
    st.subheader("样品接收确认")
    st.caption("正常情况下保持默认选中；发现问题时取消对应项，并在异常说明中记录。")
    current = record.get("task_confirmations") or {}
    cols = st.columns(3)
    output = {}
    labels = [
        ("sample_received", "样品已收到"),
        ("number_match", "样品编号一致"),
        ("sample_condition", "样品状态正常"),
    ]
    for i, (key, label) in enumerate(labels):
        with cols[i]:
            output[key] = st.checkbox(label, value=bool(current.get(key, True)), key=f"{key_prefix}_confirm_{key}")
    return output


def render_equipment_confirmation(equipment: list[dict[str, Any]], existing: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    st.subheader("设备确认")
    st.caption("设备由任务配置自动带入，不需要重新选择。正常情况下仅确认状态；选择异常后才填写说明。")
    existing_map = {x.get("management_no") or x.get("管理编号"): x for x in existing}
    output = []
    if not equipment:
        st.info("该实验配置尚未绑定设备。")
        return output
    for index, item in enumerate(equipment):
        no = item.get("management_no") or item.get("管理编号") or ""
        prior = existing_map.get(no, {})
        with st.container(border=True):
            a, b, c = st.columns([1.3, 1, 1])
            a.markdown(f"**{item.get('equipment_name') or item.get('设备名称','')}**  \n{item.get('model') or item.get('型号规格','')}  \n管理编号：`{no}`")
            b.caption(f"角色：{item.get('binding_role') or item.get('设备角色','')}  \n测量范围：{item.get('measuring_range') or item.get('测量范围','')}  \n校准时间：{item.get('calibration_time') or item.get('台账校准时间','未填写')}")
            status_options = ["正常", "异常"]
            status = prior.get("status") or prior.get("使用前状态") or "正常"
            with c:
                status = st.radio("使用前状态", status_options, index=status_options.index(status) if status in status_options else 0, horizontal=True, key=f"{key_prefix}_eq_{index}")
            note = prior.get("note") or prior.get("异常说明") or ""
            if status == "异常":
                note = st.text_area("异常说明及处理", value=str(note), key=f"{key_prefix}_eq_note_{index}")
            output.append({
                "management_no": no,
                "equipment_name": item.get("equipment_name") or item.get("设备名称", ""),
                "status": status,
                "note": note,
                "required": bool(item.get("required") or item.get("必需设备") == "是"),
            })
    return output


def render_prechecks(kind: str, record: dict[str, Any], key_prefix: str) -> tuple[list[str], str]:
    st.subheader("实验前检查")
    all_items = record.get("all_prechecks") or []
    selected = record.get("prechecks") or list(all_items)
    selected = st.multiselect(
        "已确认项目",
        all_items,
        default=[x for x in selected if x in all_items],
        key=f"{key_prefix}_prechecks",
        help="默认全部选中。取消任一项时，系统会要求填写说明。",
    )
    note = record.get("precheck_note", "")
    if set(selected) != set(all_items):
        note = st.text_area("未通过项目说明及处理", value=str(note), key=f"{key_prefix}_precheck_note")
    else:
        st.success("实验前检查默认全部正常。")
    return selected, note


def render_parameters(kind: str, record: dict[str, Any], key_prefix: str) -> tuple[dict[str, Any], str]:
    params = dict(record.get("parameters") or {})
    fixed_fields, manual_fields = fixed_and_manual_fields(kind)
    st.subheader("环境与实验参数")

    # Actual environmental/time data are always entered or confirmed by the experimenter.
    env_fields = [x for x in manual_fields if x["key"] in {"temperature", "humidity", "start_time", "end_time"}]
    other_manual = [x for x in manual_fields if x not in env_fields]
    if env_fields:
        cols = st.columns(min(4, len(env_fields)))
        for index, field in enumerate(env_fields):
            with cols[index % len(cols)]:
                params[field["key"]] = _widget(field, params.get(field["key"]), f"{key_prefix}_param_{field['key']}")

    fixed_mode = record.get("fixed_parameter_mode", "按默认参数执行")
    if fixed_fields:
        st.markdown("**固定参数**")
        summary_cols = st.columns(3)
        for index, field in enumerate(fixed_fields):
            with summary_cols[index % 3]:
                st.text_input(field["label"], value=str(params.get(field["key"], field.get("default", ""))), disabled=True, key=f"{key_prefix}_fixed_display_{field['key']}")
        fixed_mode = st.radio("固定参数执行情况", ["按默认参数执行", "存在偏离"], index=0 if fixed_mode != "存在偏离" else 1, horizontal=True, key=f"{key_prefix}_fixed_mode")
        if fixed_mode == "存在偏离":
            st.warning("仅修改实际发生偏离的参数，并在异常与偏离说明中记录原因。")
            cols = st.columns(3)
            for index, field in enumerate(fixed_fields):
                with cols[index % 3]:
                    params[field["key"]] = _widget(field, params.get(field["key"]), f"{key_prefix}_fixed_edit_{field['key']}")

    if other_manual:
        st.markdown("**本次实际记录**")
        cols = st.columns(3)
        for index, field in enumerate(other_manual):
            with cols[index % 3]:
                params[field["key"]] = _widget(field, params.get(field["key"]), f"{key_prefix}_manual_{field['key']}")
    return params, fixed_mode


def _render_row_field(kind: str, field: tuple[str, str, str], row: dict[str, Any], key_prefix: str):
    key, label, typ = field
    value = row.get(key)
    if typ == "calc":
        st.metric(label, value if value not in (None, "") else "—")
        return value
    if typ == "number":
        return st.number_input(label, value=_safe_number(value), key=f"{key_prefix}_{key}")
    if typ.startswith("select:"):
        options = typ.split(":", 1)[1].split("|")
        selected = value if value in options else options[0]
        return st.selectbox(label, options, index=options.index(selected), key=f"{key_prefix}_{key}")
    if key == "note":
        return st.text_area(label, value=str(value or ""), key=f"{key_prefix}_{key}")
    return st.text_input(label, value=str(value or ""), key=f"{key_prefix}_{key}")


def render_sample_data(kind: str, record: dict[str, Any], key_prefix: str) -> list[dict[str, Any]]:
    st.subheader("原始测量数据")
    st.caption("按样品逐个填写。计算项由系统自动生成；图片、曲线和原始文件编号由附件追溯自动关联。")
    rows = [dict(x) for x in record.get("rows") or []]
    fields = visible_row_fields(kind)
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[str(row.get("sample_no") or f"第{index+1}条")].append((index, row))

    sample_names = list(groups.keys())
    tabs = st.tabs(sample_names) if len(sample_names) > 1 else [st.container()]
    output = [dict(x) for x in rows]
    for tab, sample_no in zip(tabs, sample_names):
        with tab:
            st.markdown(f"### {sample_no}")
            for row_index, row in groups[sample_no]:
                face = row.get("face")
                container = st.expander(str(face), expanded=True) if face else st.container(border=True)
                with container:
                    visible = [f for f in fields if f[0] != "note"]
                    cols = st.columns(3)
                    abnormal = False
                    for field_index, field in enumerate(visible):
                        with cols[field_index % 3]:
                            row[field[0]] = _render_row_field(kind, field, row, f"{key_prefix}_row_{row_index}")
                        if str(row.get(field[0], "")) in {"异常", "有", "无效", "不符合", "不合格", "需复检", "超出适用范围", "无法判定"}:
                            abnormal = True
                    # Notes stay hidden for normal data and appear only when needed.
                    if abnormal or st.checkbox("补充说明", value=bool(row.get("note")), key=f"{key_prefix}_row_note_toggle_{row_index}"):
                        row["note"] = st.text_area("备注/异常说明", value=str(row.get("note", "")), key=f"{key_prefix}_row_note_{row_index}")
                    output[row_index] = row
    return output


def render_exception_and_summary(kind: str, record: dict[str, Any], key_prefix: str) -> dict[str, Any]:
    output = dict(record)
    st.subheader("异常与结果")
    status_options = ["正常完成", "存在异常"]
    status = output.get("overall_status", "正常完成")
    output["overall_status"] = st.radio("实验完成状态", status_options, index=status_options.index(status) if status in status_options else 0, horizontal=True, key=f"{key_prefix}_overall_status")
    if output["overall_status"] == "存在异常" or output.get("fixed_parameter_mode") == "存在偏离":
        output["deviation"] = st.text_area("异常、偏离、影响评估及处理措施", value=str(output.get("deviation", "")), key=f"{key_prefix}_deviation")
    else:
        output["deviation"] = output.get("deviation") or "无"
    retest_options = ["否", "是"]
    output["retest"] = st.radio("是否复测/重制", retest_options, index=1 if output.get("retest") == "是" else 0, horizontal=True, key=f"{key_prefix}_retest")
    output = calculate_business_record(kind, output)
    output["report_summary"] = st.text_area("检验报告用结果摘要", value=str(output.get("report_summary", "")), key=f"{key_prefix}_summary")
    conclusion_options = ["符合", "不符合", "仅描述结果", "需复测/技术评审"]
    current = output.get("report_conclusion") or conclusion_options[0]
    if current not in conclusion_options:
        current = "符合" if current in {"合格", "符合"} else ("不符合" if current in {"不合格", "不符合"} else "仅描述结果")
    output["report_conclusion"] = st.selectbox("检验报告用单项结论", conclusion_options, index=conclusion_options.index(current), key=f"{key_prefix}_conclusion")
    return output


def render_completion(summary: dict[str, Any]):
    st.subheader("提交前检查")
    for label, passed in summary.get("sections", {}).items():
        st.markdown(("✅ " if passed else "⚠️ ") + label)
    issues = summary.get("issues") or []
    if issues:
        st.warning("仍有需要处理的项目：")
        for item in issues[:30]:
            st.write("- " + item)
    else:
        st.success("实验记录已完整，可提交复核。")
