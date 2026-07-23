# -*- coding: utf-8 -*-
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import Any
import json
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from experiment_engine import result_summary

ROOT=Path(__file__).parent
TEMPLATE_DIR=ROOT/"templates"
SIGNATURE_DIR=ROOT/"data"/"signatures"
BLACK=RGBColor(0,0,0)


def _blacken(doc):
    for p in doc.paragraphs:
        for r in p.runs:r.font.color.rgb=BLACK
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:r.font.color.rgb=BLACK


def _save(doc):
    _blacken(doc);b=BytesIO();doc.save(b);b.seek(0);return b


def _setp(p,text,bold=False):
    p.clear();r=p.add_run(str(text));r.bold=bold;r.font.color.rgb=BLACK


def _prefix(p,prefix,value):
    if p.text.strip().startswith(prefix):_setp(p,prefix+("" if value is None else str(value)));return True
    return False


def _fill(table,data,header_rows=1):
    while len(table.rows)<header_rows+len(data):table.add_row()
    for i,vals in enumerate(data,start=header_rows):
        for j,v in enumerate(vals):
            if j<len(table.rows[i].cells):table.rows[i].cells[j].text="" if v is None else str(v)
    for i in range(header_rows+len(data),len(table.rows)):
        for cell in table.rows[i].cells:cell.text=""


def group_range(g):
    q=int(g.get("quantity") or 1)
    return f"{g['group_no']}-01" if q==1 else f"{g['group_no']}-01～{g['group_no']}-{q:02d}"


def commission_document(c,groups,tests,receiver_name):
    d=Document(TEMPLATE_DIR/"FORM_COMMISSION.docx")
    methods=json.loads(c.get("method_choices") or "[]")
    options=["YY/T 1936","YY 0300","YY 0621.1","YY 0621.2","YY/T 1702","GB 17168","GB/T 4340.1","GB/T 3851","GB/T 18876.1","YY/T 1937","YY 0270.1","T/GDMDMA 0003","YY 0710"]
    method_line1="  ".join(("☑" if x in methods else "□")+x for x in options[:7])
    method_line2="  ".join(("☑" if x in methods else "□")+x for x in options[7:])
    bad=[g for g in groups if g.get("condition")!="完好"]
    bad_note="；".join(f"{g['group_no']}:{g.get('condition_note','')}" for g in bad)
    for p in d.paragraphs:
        _prefix(p,"委托方名称：",c.get("client_name",""));_prefix(p,"委托方地址：",c.get("client_address",""))
        if p.text.strip().startswith("联系人："):_setp(p,f"联系人：{c.get('contact','')}    联系电话：{c.get('phone','')}    委托日期：{c.get('commission_date','')}")
        if "样品外观检查良好" in p.text:_setp(p,f"{'□' if bad else '☑'}样品外观检查良好； {'☑' if bad else '□'}样品外观异常。异常情况说明：{bad_note}")
        if p.text.strip().startswith("检测方法："):_setp(p,"检测方法：")
        elif "YY/T 1936" in p.text:_setp(p,method_line1)
        elif "GB/T 3851" in p.text:_setp(p,method_line2)
        if p.text.strip().startswith("1、标普检测资源不满足时"):
            yes=c.get("subcontract_allowed")=="是";_setp(p,f"1、标普检测资源不满足时，是否允许分包？ {'☑是  □否' if yes else '□是  ☑否'}")
        if p.text.strip().startswith("2、样品、相关资料是否保密"):_setp(p,"2、样品、相关资料是否保密？ □是  ☑无要求")
        if p.text.strip().startswith("报告载体："):_setp(p,f"报告载体：{c.get('report_medium','')}    符合性判定：{c.get('conformity_judgment','')}")
        if p.text.strip().startswith("考虑不确定度："):_setp(p,f"考虑不确定度：{c.get('uncertainty','')}    递送方式：{c.get('delivery_method','')}")
        if "CNAS" in p.text and "章" in p.text:_setp(p,f"加盖 CNAS 章：{c.get('cnas_mark','')}")
        if p.text.strip().startswith("检测能力："):_setp(p,f"检测能力：{c.get('capability','')}")
    tm={}
    for t in tests:tm.setdefault(t["group_no"],[]).append(t["experiment"])
    data=[]
    for i,g in enumerate(groups,1):
        prod=c.get("production_org_name","")+("（受委托生产企业）" if c.get("production_relation")=="受委托生产企业" else "")
        data.append([i,f"{g['sample_name']}（{g['model']}）",group_range(g),prod,"、".join(tm.get(g["group_no"],[])),g.get("quantity",1),g.get("notes","") or g.get("condition_note","")])
    _fill(d.tables[0],data)
    return _save(d)


def sample_register_document(c,groups,samples,tests,receiver_name):
    """Generate DLBP-CX-P10-R01 sample registration form.

    Column order follows the controlled template exactly:
    laboratory sample number, commissioning unit, sample name, model/specification,
    production unit, sample number/batch, inspection items, quantity, receiver,
    date and remarks.
    """
    d=Document(TEMPLATE_DIR/"FORM_SAMPLE_REGISTER.docx")
    gm={g["group_no"]:g for g in groups}
    tm={}
    for t in tests:
        tm.setdefault(t["group_no"],[]).append(t["experiment"])

    production_unit=c.get("production_org_name","")
    if c.get("production_relation")=="受委托生产企业" and production_unit:
        production_unit += "（受委托生产企业）"

    data=[]
    for s in samples:
        g=gm[s["group_no"]]
        remarks=s.get("condition_note","") or g.get("notes","") or ""
        data.append([
            s["sample_no"],
            c.get("client_name",""),
            s["sample_name"],
            s["model"],
            production_unit,
            g.get("product_no",""),
            "、".join(tm.get(s["group_no"],[])),
            1,
            receiver_name,
            c.get("commission_date",""),
            remarks,
        ])
    _fill(d.tables[0],data)
    return _save(d)


def loan_return_document(loans,user_names):
    d=Document(TEMPLATE_DIR/"FORM_SAMPLE_LOAN_RETURN.docx");data=[]
    for i,x in enumerate(loans,1):
        purpose=x.get("purpose") or "、".join(json.loads(x.get("experiments") or "[]"))
        data.append([i,x["sample_no"],user_names.get(x.get("borrower"),x.get("borrower","")),x.get("borrowed_at",""),purpose,x.get("returned_at",""),user_names.get(x.get("returned_by"),x.get("returned_by","")),x.get("return_note","") or x.get("issue_note","")])
    _fill(d.tables[0],data);return _save(d)


def _sig(meta):
    if not meta or not meta.get("image_file"):return None
    p=SIGNATURE_DIR/meta["image_file"];return p if p.exists() else None


def report_document(c,groups,samples,tasks,records,report,user_names,signatures):
    d=Document(TEMPLATE_DIR/"FORM_REPORT.docx")
    names="、".join(dict.fromkeys(g["sample_name"] for g in groups));models="、".join(dict.fromkeys(g["model"] for g in groups));ranges="；".join(group_range(g) for g in groups);products="、".join(dict.fromkeys(g.get("product_no","") for g in groups if g.get("product_no")));prods=c.get("production_org_name","")+("（受委托生产企业）" if c.get("production_relation")=="受委托生产企业" else "");conds="；".join(f"{g['group_no']}:{g['condition']}" for g in groups)
    for p in d.paragraphs:
        _prefix(p,"报告编号：",report.get("report_no",""));_prefix(p,"委 托 单 位：",c.get("client_name",""));_prefix(p,"地       址：",c.get("client_address",""));_prefix(p,"样 品 名 称：",names);_prefix(p,"型 号/规 格：",models);_prefix(p,"样 品 编 号：",ranges);_prefix(p,"产品编号/批号：",products);_prefix(p,"生 产 单 位：",prods);_prefix(p,"接 收 日 期：",c.get("commission_date",""));_prefix(p,"接 收 状 态：",conds);_prefix(p,"检 验 类 别：",report.get("report_category") or "委托检验");_prefix(p,"报告发布日期：",report.get("publish_date") or "")
        if p.text.strip().startswith("样品情况说明："):_setp(p,"样品情况说明："+(report.get("sample_statement") or ""))
        if p.text.strip().startswith("检验结论："):_setp(p,"检验结论："+(report.get("conclusion") or ""))
    eq=[];env=[];results=[]
    for i,t in enumerate(tasks,1):
        rec=records.get(t["task_no"])
        if not rec:continue
        payload=rec["payload"];common=payload.get("common",{});params=payload.get("parameters",{})
        summary=payload.get("report_summary","")
        conclusion=payload.get("report_conclusion","")
        if not summary or not conclusion:
            legacy_summary,legacy_conclusion=result_summary(t["kind"],payload.get("data",[]))
            summary=summary or legacy_summary;conclusion=conclusion or legacy_conclusion
        equipment_rows=payload.get("equipment_snapshot",[])
        used=[x for x in equipment_rows if x.get("本次使用")=="是"]
        eq_names="；".join(f"{x.get('设备名称','')}（{x.get('管理编号','')}）" for x in used)
        eq_models="；".join(x.get("型号规格","") for x in used if x.get("型号规格"))
        eq.append([eq_names,eq_models,"","","",""])
        location=(payload.get("configuration_snapshot",{}) or {}).get("default_location","") or params.get("detection_location",common.get("location",""))
        env.append([location,params.get("temperature",common.get("temperature","")),params.get("humidity",common.get("humidity","")),payload.get("deviation","")])
        item=f"{t['group_no']} {t.get('sample_name','')}：{t['experiment']}";results.append([i,item,t.get("standard",""),summary,conclusion,payload.get("deviation","")])
    if len(d.tables)>0:_fill(d.tables[0],eq)
    if len(d.tables)>1:_fill(d.tables[1],env)
    if len(d.tables)>2:_fill(d.tables[2],results,2)
    for label,field,signed in [("批 准 人","approver","approver_signed_at"),("核 验 员","verifier","verifier_signed_at"),("检 测 员","tester","tester_signed_at")]:
        u=report.get(field);name=user_names.get(u,u or "")
        for p in d.paragraphs:
            if p.text.strip().startswith(label):
                p.add_run("    "+name)
                if report.get(signed):
                    path=_sig(signatures.get(u))
                    if path:
                        try:p.add_run().add_picture(str(path),width=Inches(.85))
                        except:pass
                break
    return _save(d)
