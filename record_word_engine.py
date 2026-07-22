# -*- coding: utf-8 -*-
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import Any
import re
from docx import Document
from docx.shared import Pt, RGBColor
from experiment_schemas import SCHEMAS

ROOT=Path(__file__).parent
TEMPLATE_DIR=ROOT/"templates"
BLACK=RGBColor(0,0,0);RED=RGBColor(255,0,0)


def norm(v):return re.sub(r"\s+","",str(v or "")).replace("：",":").replace("（","(").replace("）",")")


def _blacken(doc):
    for p in doc.paragraphs:
        for r in p.runs:r.font.color.rgb=BLACK
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:r.font.color.rgb=BLACK


def _put(cell,value,red=False,bold=False):
    cell.text="";p=cell.paragraphs[0];r=p.add_run("" if value is None else str(value));r.bold=bold or red;r.font.color.rgb=RED if red else BLACK


def _common_values(payload):
    c=payload.get("common",{});p=payload.get("parameters",{})
    return {
        "原始记录编号":c.get("record_no",""),"记录编号":c.get("record_no",""),"报告编号":c.get("report_no",""),
        "委托单位":c.get("client",""),"委托单编号":c.get("commission_no",""),"委托单号":c.get("commission_no",""),
        "样品名称":c.get("sample_name",""),"样品编号":c.get("sample_no",""),"样品编号/批号":c.get("sample_no",""),
        "规格型号":c.get("model",""),"型号/规格":c.get("model",""),"材料名称":c.get("material",""),
        "检测依据":c.get("standard",""),"检测方法":c.get("method_code",""),"检测日期":c.get("test_date",""),
        "检测地点":p.get("detection_location",c.get("location","")),"环境温度":p.get("temperature",c.get("temperature","")),
        "相对湿度":p.get("humidity",c.get("humidity","")),"检测人员":c.get("operator",""),"复核人员":c.get("reviewer",""),
        "设备名称":p.get("equipment_name",""),"型号/规格":p.get("equipment_model",c.get("model","")),
        "设备/器具编号":p.get("equipment_no",""),"管理编号":p.get("equipment_no",""),
        "校准/检定证书编号":p.get("calibration_certificate",""),"校准/核查有效期":p.get("calibration_due",""),
        "软件/版本":p.get("software",""),"数据保存路径":p.get("data_path",""),"原始图像保存路径":p.get("image_path",p.get("data_path","")),
    }


def _field_labels(kind):
    out={}
    for section in SCHEMAS[kind]["sections"]:
        for f in section["fields"]:out[f["key"]]=f["label"]
    return out


def _fill_label_values(doc,payload,kind,changed):
    values=_common_values(payload)
    params=payload.get("parameters",{})
    for key,label in _field_labels(kind).items():values[label]=params.get(key,"")
    for table in doc.tables:
        for row in table.rows:
            cells=row.cells
            for i,cell in enumerate(cells[:-1]):
                txt=norm(cell.text)
                for label,value in values.items():
                    nl=norm(label)
                    if value not in (None,"") and (txt==nl or txt.startswith(nl)):
                        red=f"parameters.{next((k for k,v in _field_labels(kind).items() if v==label),'')}" in changed
                        _put(cells[i+1],value,red);break


def _header_row(table,labels):
    best=None
    for ri,row in enumerate(table.rows[:5]):
        hs=[norm(c.text) for c in row.cells];score=sum(any(norm(label) in h or h in norm(label) for label in labels if h) for h in hs)
        if best is None or score>best[0]:best=(score,ri,hs)
    return best


def _fill_data(doc,payload,kind,changed):
    data=payload.get("data") or []
    if not data:return
    cols=SCHEMAS[kind]["columns"];labels={k:l for k,l,_ in cols};best=None
    for table in doc.tables:
        score,ri,hs=_header_row(table,list(labels.values()))
        if best is None or score>best[0]:best=(score,table,ri,hs)
    if not best or best[0]<2:return
    _,table,ri,hs=best
    while len(table.rows)<ri+1+len(data):table.add_row()
    for di,rowdata in enumerate(data):
        row=table.rows[ri+1+di]
        for key,label in labels.items():
            target=None;nl=norm(label)
            for ci,h in enumerate(hs):
                if h and (h==nl or h in nl or nl in h):target=ci;break
            if target is not None and target<len(row.cells):_put(row.cells[target],rowdata.get(key,""),f"data[{di}].{key}" in changed)


def _safe_table_grid(table):
    try:
        table.style="Table Grid"
    except Exception:
        pass


def _append_details(doc,payload,kind):
    doc.add_paragraph().add_run("补充过程数据与附件追溯").bold=True
    t=doc.add_table(rows=1,cols=2);_safe_table_grid(t);t.rows[0].cells[0].text="字段";t.rows[0].cells[1].text="记录值"
    labels=_field_labels(kind)
    for key,value in payload.get("parameters",{}).items():
        cells=t.add_row().cells;cells[0].text=labels.get(key,key);cells[1].text="" if value is None else str(value)
    a=doc.add_table(rows=1,cols=6);_safe_table_grid(a)
    for i,x in enumerate(["附件ID","类型","文件名","样品编号","SHA-256","说明"]):a.rows[0].cells[i].text=x
    for x in payload.get("attachments",[]):
        cells=a.add_row().cells
        vals=[x.get("attachment_id",""),x.get("attachment_type",""),x.get("original_name",""),x.get("sample_no",""),x.get("sha256",""),x.get("description","")]
        for i,v in enumerate(vals):cells[i].text=str(v)


def _revision(doc,changes,record):
    if record.get("version",1)<=1:return
    doc.add_page_break();p=doc.add_paragraph();r=p.add_run("原始记录修改说明");r.bold=True;r.font.size=Pt(16);r.font.color.rgb=RED
    doc.add_paragraph(f"记录编号：{record['record_no']}  版本：V{record['version']}  修改原因：{record.get('change_reason','')}")
    t=doc.add_table(rows=1,cols=4);_safe_table_grid(t)
    for i,h in enumerate(["修改位置","原值","修改后","原因"]):t.rows[0].cells[i].text=h
    for x in changes:
        c=t.add_row().cells;c[0].text=x.get("field_name","");c[1].text=x.get("old_value","");_put(c[2],x.get("new_value",""),True);c[3].text=x.get("reason","")


def _fallback(record,changes):
    payload=record["payload"];kind=record["kind"];doc=Document();doc.add_heading(SCHEMAS[kind]["title"],0)
    c=doc.add_table(rows=0,cols=2);_safe_table_grid(c)
    for label,value in _common_values(payload).items():
        if value not in (None,""):
            cells=c.add_row().cells;cells[0].text=label;cells[1].text=str(value)
    _append_details(doc,payload,kind)
    data=payload.get("data") or [];cols=SCHEMAS[kind]["columns"]
    if data:
        t=doc.add_table(rows=1,cols=len(cols));_safe_table_grid(t)
        for i,(_,label,_) in enumerate(cols):t.rows[0].cells[i].text=label
        for row in data:
            cells=t.add_row().cells
            for i,(key,_,_) in enumerate(cols):cells[i].text=str(row.get(key,""))
    _revision(doc,changes,record);_blacken(doc)
    # restore red revision values after blackening
    if record.get("version",1)>1:
        for table in doc.tables[-1:]:
            for row in table.rows[1:]:
                for run in row.cells[2].paragraphs[0].runs:run.font.color.rgb=RED
    b=BytesIO();doc.save(b);b.seek(0);return b


def export_record(record,template_name,changes):
    kind=record["kind"]
    path=TEMPLATE_DIR/template_name if template_name else None
    if not path or not path.exists():return _fallback(record,changes)
    doc=Document(path);_blacken(doc);changed={x.get("field_name") for x in changes if x.get("action")=="字段修改"}
    _fill_label_values(doc,record["payload"],kind,changed);_fill_data(doc,record["payload"],kind,changed);_append_details(doc,record["payload"],kind);_revision(doc,changes,record)
    _blacken(doc)
    if record.get("version",1)>1:
        # modification appendix is the only red content
        for table in doc.tables[-1:]:
            for row in table.rows[1:]:
                if len(row.cells)>=3:
                    for run in row.cells[2].paragraphs[0].runs:run.font.color.rgb=RED
    b=BytesIO();doc.save(b);b.seek(0);return b
