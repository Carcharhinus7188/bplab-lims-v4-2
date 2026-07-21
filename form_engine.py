# -*- coding: utf-8 -*-
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).parent
TEMPLATE_DIR = ROOT / "templates"
SIGNATURE_DIR = ROOT / "data" / "signatures"


def _save(doc: Document) -> BytesIO:
    out = BytesIO()
    doc.save(out)
    out.seek(0)
    return out


def _set_paragraph(paragraph, text: str, bold: bool = False, red: bool = False) -> None:
    paragraph.clear()
    run = paragraph.add_run(text)
    run.bold = bold
    if red:
        run.font.color.rgb = RGBColor(192, 0, 0)


def _replace_prefix(paragraph, prefix: str, value: Any) -> bool:
    if paragraph.text.strip().startswith(prefix):
        _set_paragraph(paragraph, f"{prefix}{'' if value is None else value}")
        return True
    return False


def _ensure_rows(table, count: int, header_rows: int = 1) -> None:
    while len(table.rows) < header_rows + count:
        table.add_row()


def _fill_rows(table, rows: list[list[Any]], header_rows: int = 1) -> None:
    _ensure_rows(table, len(rows), header_rows)
    for i, values in enumerate(rows, start=header_rows):
        for j, value in enumerate(values):
            if j < len(table.rows[i].cells):
                table.rows[i].cells[j].text = "" if value is None else str(value)
    # Clear unused original rows so old placeholders never remain.
    for i in range(header_rows + len(rows), len(table.rows)):
        for cell in table.rows[i].cells:
            cell.text = ""


def commission_document(
    commission: dict[str, Any],
    samples: list[dict[str, Any]],
    tests: list[dict[str, Any]],
    receiver_name: str,
) -> BytesIO:
    doc = Document(TEMPLATE_DIR / "FORM_COMMISSION.docx")
    tests_text = "、".join(t["experiment"] for t in tests)
    methods_text = "；".join(dict.fromkeys(t.get("standard") or "" for t in tests if t.get("standard")))

    for p in doc.paragraphs:
        _replace_prefix(p, "委托方名称：", commission.get("customer_name", ""))
        _replace_prefix(p, "委托方地址：", commission.get("customer_address", ""))
        if p.text.strip().startswith("联系人："):
            _set_paragraph(
                p,
                f"联系人：{commission.get('contact','')}    联系电话：{commission.get('phone','')}    委托日期：{commission.get('commission_date','')}",
            )
        if "样品外观检查良好" in p.text:
            if commission.get("sample_condition") == "完好":
                _set_paragraph(p, "☑样品外观检查良好； □样品外观异常。异常情况说明：")
            else:
                _set_paragraph(p, f"□样品外观检查良好； ☑样品外观异常。异常情况说明：{commission.get('condition_note','')}")
        if p.text.strip().startswith("检测方法："):
            _set_paragraph(p, "检测方法：" + methods_text)
        if p.text.strip().startswith("1、标普检测资源不满足时"):
            yes = commission.get("subcontract_allowed") == "是"
            _set_paragraph(p, f"1、标普检测资源不满足时，是否允许分包？ {'☑是  □否' if yes else '□是  ☑否'}")
        if p.text.strip().startswith("2、样品、相关资料是否保密"):
            yes = commission.get("confidentiality") == "是"
            _set_paragraph(p, f"2、样品、相关资料是否保密？ {'☑是  □无要求' if yes else '□是  ☑无要求'}")
        if p.text.strip().startswith("报告载体："):
            _set_paragraph(
                p,
                f"报告载体：{commission.get('report_medium','')}    符合性判定：{commission.get('conformity_judgment','')}",
            )
        if p.text.strip().startswith("考虑不确定度："):
            _set_paragraph(
                p,
                f"考虑不确定度：{commission.get('uncertainty','')}    递送方式：{commission.get('delivery_method','')}",
            )
        if p.text.strip().startswith("加盖CNAS章："):
            _set_paragraph(p, f"加盖CNAS章：{commission.get('cnas_mark','')}")
        if p.text.strip().startswith("检测能力："):
            _set_paragraph(p, f"检测能力：{commission.get('capability','')}")

    # Every physical sample receives one row. Requested tests are shown for each row.
    rows = [
        [i, s["sample_name"], s["sample_no"], s.get("production_unit", ""), tests_text, 1, s.get("condition_note", "")]
        for i, s in enumerate(samples, 1)
    ]
    _fill_rows(doc.tables[0], rows)

    if len(doc.tables) > 1:
        confirm_table = doc.tables[1]
        if confirm_table.rows:
            left = confirm_table.rows[0].cells[0]
            right = confirm_table.rows[0].cells[1]
            left.paragraphs[-1].add_run(f"\n委托方：{commission.get('customer_name','')}\n日期：{commission.get('commission_date','')}")
            right.paragraphs[-1].add_run(f"\n样品接收人：{receiver_name}\n日期：{commission.get('commission_date','')}")
        if len(confirm_table.rows) > 2:
            confirm_table.rows[2].cells[0].text = "备注：" + (commission.get("notes") or "")
            confirm_table.rows[2].cells[1].text = "备注：" + (commission.get("notes") or "")
    return _save(doc)


def sample_register_document(
    commission: dict[str, Any],
    samples: list[dict[str, Any]],
    tests: list[dict[str, Any]],
    receiver_name: str,
) -> BytesIO:
    doc = Document(TEMPLATE_DIR / "FORM_SAMPLE_REGISTER.docx")
    tests_text = "、".join(t["experiment"] for t in tests)
    rows = [
        [
            s["sample_no"], commission.get("customer_name", ""), s["sample_name"], s["model"],
            s.get("product_no", ""), tests_text, 1, receiver_name,
            commission.get("commission_date", ""), s.get("condition_note", ""),
        ]
        for s in samples
    ]
    _fill_rows(doc.tables[0], rows)
    return _save(doc)


def loan_return_document(loans: list[dict[str, Any]], user_names: dict[str, str]) -> BytesIO:
    doc = Document(TEMPLATE_DIR / "FORM_SAMPLE_LOAN_RETURN.docx")
    rows = []
    for i, x in enumerate(loans, 1):
        rows.append(
            [
                i,
                x["sample_no"],
                user_names.get(x.get("borrower"), x.get("borrower", "")),
                x.get("borrowed_at", ""),
                x.get("experiment", x.get("purpose", "")),
                x.get("returned_at", ""),
                user_names.get(x.get("returned_by"), x.get("returned_by", "")),
                x.get("return_note", "") or x.get("issue_note", ""),
            ]
        )
    _fill_rows(doc.tables[0], rows)
    return _save(doc)


def _result_text(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("data") or []
    summaries: list[str] = []
    conclusions: list[str] = []
    for row in data:
        sample_id = row.get("试样编号") or row.get("样品编号") or row.get("样品编号/位置") or ""
        chosen = []
        for key, value in row.items():
            if key in ("试样编号", "样品编号", "样品编号/位置", "判定"):
                continue
            if value not in ("", None, 0, 0.0):
                chosen.append(f"{key}={value}")
        if chosen:
            summaries.append((sample_id + "：" if sample_id else "") + "，".join(chosen[-3:]))
        if row.get("判定"):
            conclusions.append(str(row["判定"]))
    result = "；".join(summaries) or "详见原始记录"
    conclusion = "符合" if conclusions and all(x == "符合" for x in conclusions) else ("；".join(dict.fromkeys(conclusions)) or "见检验结果")
    return result, conclusion


def _signature_path(signature_meta: dict[str, Any] | None) -> Path | None:
    if not signature_meta or not signature_meta.get("image_file"):
        return None
    p = SIGNATURE_DIR / signature_meta["image_file"]
    return p if p.exists() else None


def report_document(
    commission: dict[str, Any],
    samples: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    report: dict[str, Any],
    user_names: dict[str, str],
    signatures: dict[str, dict[str, Any] | None],
) -> BytesIO:
    doc = Document(TEMPLATE_DIR / "FORM_REPORT.docx")
    sample_names = "、".join(dict.fromkeys(s["sample_name"] for s in samples))
    models = "、".join(dict.fromkeys(s["model"] for s in samples))
    sample_nos = "、".join(s["sample_no"] for s in samples)
    product_nos = "、".join(dict.fromkeys(s.get("product_no", "") for s in samples if s.get("product_no")))
    production_units = "、".join(dict.fromkeys(s.get("production_unit", "") for s in samples if s.get("production_unit")))
    status_label = "正式报告" if report.get("status") == "已发布" else f"半成品报告（{report.get('status','')}）"

    for p in doc.paragraphs:
        text = p.text.strip()
        _replace_prefix(p, "报告编号：", report.get("report_no", ""))
        _replace_prefix(p, "委 托 单 位：", commission.get("customer_name", ""))
        _replace_prefix(p, "地       址：", commission.get("customer_address", ""))
        _replace_prefix(p, "样 品 名 称：", sample_names)
        _replace_prefix(p, "型 号/规 格：", models)
        _replace_prefix(p, "样 品 编 号：", sample_nos)
        _replace_prefix(p, "产品编号/批号：", product_nos)
        if text.startswith("生 产 单 位："):
            _set_paragraph(p, f"生 产 单 位：{production_units}\n接 收 日 期：{commission.get('commission_date','')}")
        _replace_prefix(p, "接 收 状 态：", commission.get("sample_condition", ""))
        _replace_prefix(p, "检 验 类 别：", report.get("report_category", "委托检验"))
        _replace_prefix(p, "报告发布日期：", report.get("publish_date", "") or "")
        if text.startswith("检验日期 ："):
            dates = [r["payload"].get("common", {}).get("test_date") for r in records.values()]
            dates = [d for d in dates if d]
            _set_paragraph(p, "检验日期 ：" + (f"{min(dates)} 至 {max(dates)}" if dates else ""))
        if text.startswith("样品情况说明："):
            _set_paragraph(p, "样品情况说明：" + (report.get("sample_statement") or ""))
        if text.startswith("检验结论："):
            _set_paragraph(p, "检验结论：" + (report.get("conclusion") or ""))

    # Place a clear draft/final status under the title.
    if len(doc.paragraphs) > 2:
        p = doc.paragraphs[2]
        run = p.add_run(f"\n{status_label}")
        run.bold = True
        run.font.size = Pt(11)
        if report.get("status") != "已发布":
            run.font.color.rgb = RGBColor(192, 0, 0)

    equipment_rows: list[list[Any]] = []
    environment_rows: list[list[Any]] = []
    result_rows: list[list[Any]] = []
    seen_equipment: set[tuple[str, str]] = set()
    seen_env: set[tuple[str, str, str]] = set()
    for index, t in enumerate(tasks, 1):
        rec = records.get(t["task_no"])
        if not rec:
            continue
        payload = rec["payload"]
        common = payload.get("common", {})
        eq_key = (str(common.get("equipment", "")), str(common.get("calibration", "")))
        if any(eq_key) and eq_key not in seen_equipment:
            seen_equipment.add(eq_key)
            equipment_rows.append([common.get("equipment", ""), common.get("equipment_model", ""), "", common.get("calibration", ""), "", common.get("calibration_due", "")])
        env_key = (str(common.get("location", "")), str(common.get("temperature", "")), str(common.get("humidity", "")))
        if env_key not in seen_env:
            seen_env.add(env_key)
            environment_rows.append([common.get("location", ""), common.get("temperature", ""), common.get("humidity", ""), payload.get("deviation", "")])
        result_text, single_conclusion = _result_text(payload)
        result_rows.append([index, t["experiment"], t.get("standard", ""), result_text, single_conclusion, payload.get("deviation", "")])

    if len(doc.tables) > 0:
        _fill_rows(doc.tables[0], equipment_rows)
    if len(doc.tables) > 1:
        _fill_rows(doc.tables[1], environment_rows)
    if len(doc.tables) > 2:
        _fill_rows(doc.tables[2], result_rows, header_rows=2)

    # Add names and signature images only after the corresponding workflow action.
    stages = [
        ("批 准 人", "approver", "approver_signed_at"),
        ("核 验 员", "verifier", "verifier_signed_at"),
        ("检 测 员", "tester", "tester_signed_at"),
    ]
    for label, user_field, signed_field in stages:
        username = report.get(user_field)
        display_name = user_names.get(username, username or "")
        for p in doc.paragraphs:
            if p.text.strip().startswith(label):
                p.add_run(f"    {display_name}")
                if report.get(signed_field):
                    image_path = _signature_path(signatures.get(username))
                    if image_path:
                        try:
                            p.add_run().add_picture(str(image_path), width=Inches(0.85))
                        except Exception:
                            p.add_run("（签名图加载失败）")
                    else:
                        p.add_run("（电子签名待配置）")
                break

    return _save(doc)
