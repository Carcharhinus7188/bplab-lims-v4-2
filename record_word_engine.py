# -*- coding: utf-8 -*-

from __future__ import annotations
from pathlib import Path
from copy import deepcopy
import io,re
from docx import Document
from docx.shared import RGBColor, Pt
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).parent
TPL_DIR=ROOT/"templates"

def norm(v):
    return re.sub(r"\s+","",str(v or "")).replace("：",":")

def clear_cell(cell):
    for p in cell.paragraphs:
        for r in p.runs:
            r.text=""
    if not cell.paragraphs:
        cell.add_paragraph()

def put(cell,value,red=False,bold=False):
    clear_cell(cell)
    p=cell.paragraphs[0]
    r=p.add_run(str(value))
    if red:r.font.color.rgb=RGBColor(255,0,0)
    r.bold=bold or red
    return r

def common_mapping(common):
    return {
      "记录编号":common.get("record_no",""),
      "原始记录编号":common.get("record_no",""),
      "报告编号":common.get("report_no",""),
      "委托单位":common.get("client",""),
      "委托单号":common.get("task_no",""),
      "委托编号/任务单号":common.get("task_no",""),
      "样品名称":common.get("sample_name",""),
      "样品编号":common.get("sample_no",""),
      "样品编号/批号":common.get("sample_no",""),
      "样品批号/型号":common.get("model",""),
      "规格型号":common.get("model",""),
      "材料名称":common.get("material",""),
      "检测日期":common.get("test_date",""),
      "检测地点":common.get("location",""),
      "环境温度":f'{common.get("temperature","")} ℃',
      "相对湿度":f'{common.get("humidity","")} %RH',
      "检测人员":common.get("operator",""),
      "复核人员":common.get("reviewer",""),
    }

def fill_common(doc,common,changed):
    cmap=common_mapping(common)
    aliases={
      "记录编号":"common.record_no","原始记录编号":"common.record_no",
      "报告编号":"common.report_no","委托单位":"common.client",
      "委托单号":"common.task_no","委托编号/任务单号":"common.task_no",
      "样品名称":"common.sample_name","样品编号":"common.sample_no",
      "样品编号/批号":"common.sample_no","样品批号/型号":"common.model",
      "规格型号":"common.model","材料名称":"common.material",
      "检测日期":"common.test_date","检测地点":"common.location",
      "环境温度":"common.temperature","相对湿度":"common.humidity",
      "检测人员":"common.operator","复核人员":"common.reviewer",
    }
    for table in doc.tables:
        for row in table.rows:
            for i,cell in enumerate(row.cells[:-1]):
                txt=norm(cell.text)
                for label,val in cmap.items():
                    if val not in ("",None) and norm(label)==txt:
                        put(row.cells[i+1],val,aliases.get(label) in changed)
                        break

def header_index(table):
    best=(0,[])
    for ri,row in enumerate(table.rows[:4]):
        headers=[norm(c.text) for c in row.cells]
        score=sum(bool(h) for h in headers)
        if score>best[0]:best=(score,(ri,headers))
    return best[1] if best[1] else (0,[])

ALIASES={
 "试样编号":["试样编号","样品编号","样品编号/位置"],
 "样品编号":["样品编号","试样编号","样品编号/位置"],
 "样品编号/位置":["样品编号/位置","样品编号","试样编号"],
 "H1/mm":["H1（mm）","H1/mm"],
 "H2/mm":["H2（mm）","H2/mm"],
 "ΔH/mm":["ΔH=H1-H2（mm）","ΔH/mm"],
 "平均值/μm":["平均值(μm)","平均值/μm"],
 "测试面平均/HV":["测试面平均/HV"],
 "0.2%规定非比例弯曲应力/MPa":["0.2%规定非比例弯曲应力/MPa"],
 "τb/MPa":["τb=K×Ffail/MPa","τb/MPa"],
 "dM平均/mm":["dM平均/mm"],
 "ROI平均灰度":["ROI平均灰度值","ROI平均灰度"],
 "α/(10⁻⁶/K)":["α/(10⁻⁶/K)"],
 "ΔE*":["ΔE*","色差"],
 "判定":["判定","结论","单样结论","判定结果"],
}
def find_col(headers,key):
    candidates=ALIASES.get(key,[key])
    for c in candidates:
        nc=norm(c)
        for i,h in enumerate(headers):
            if nc==h or nc in h:
                return i
    return None

def fill_data(doc,data,changed):
    if not data:return
    keys=list(data[0].keys())
    best=None
    for ti,t in enumerate(doc.tables):
        ri,headers=header_index(t)
        matches=sum(find_col(headers,k) is not None for k in keys)
        if matches>=2 and (best is None or matches>best[0]):
            best=(matches,t,ri,headers)
    if not best:return
    _,table,ri,headers=best
    for di,rowdata in enumerate(data):
        target=ri+1+di
        if target>=len(table.rows):break
        row=table.rows[target]
        for k,v in rowdata.items():
            ci=find_col(headers,k)
            if ci is None or ci>=len(row.cells):continue
            red=f"data[{di}].{k}" in changed
            put(row.cells[ci],v,red)

def add_revision_appendix(doc,changes,record_no,version,reason,actor,reviewer=""):
    doc.add_page_break()
    p=doc.add_paragraph()
    r=p.add_run("原始记录修改说明")
    r.bold=True;r.font.size=Pt(16);r.font.color.rgb=RGBColor(192,0,0)
    doc.add_paragraph(f"记录编号：{record_no}    修订版本：R{version-1}")
    doc.add_paragraph(f"修改原因：{reason}")
    doc.add_paragraph(f"修改人：{actor}    复核人：{reviewer}")
    table=doc.add_table(rows=1,cols=4)
    table.style="Table Grid"
    for i,h in enumerate(["修改位置","原值","修改后","说明"]):
        rr=table.rows[0].cells[i].paragraphs[0].add_run(h);rr.bold=True
    for ch in changes:
        cells=table.add_row().cells
        cells[0].text=ch.get("field_name","")
        cells[1].text=ch.get("old_value","")
        rr=cells[2].paragraphs[0].add_run(ch.get("new_value",""))
        rr.font.color.rgb=RGBColor(255,0,0);rr.bold=True
        cells[3].text=ch.get("reason","") or reason

def fallback_doc(record,changes):
    doc=Document()
    doc.add_heading(record["experiment"],0)
    doc.add_paragraph("CMA电子原始记录表（模板待管理员上传DOCX后自动替换）")
    common=record["payload"].get("common",{})
    t=doc.add_table(rows=0,cols=2);t.style="Table Grid"
    for k,v in common.items():
        c=t.add_row().cells;c[0].text=k;c[1].text=str(v)
    data=record["payload"].get("data",[])
    if data:
        keys=list(data[0])
        t=doc.add_table(rows=1,cols=len(keys));t.style="Table Grid"
        for i,k in enumerate(keys):t.rows[0].cells[i].text=k
        for row in data:
            cells=t.add_row().cells
            for i,k in enumerate(keys):cells[i].text=str(row.get(k,""))
    if record["version"]>1:
        add_revision_appendix(doc,changes,record["record_no"],record["version"],
                              record.get("change_reason",""),record["owner"])
    out=io.BytesIO();doc.save(out);out.seek(0);return out

def export_record(record,template_name,changes):
    if not template_name or not (TPL_DIR/template_name).exists():
        return fallback_doc(record,changes)
    doc=Document(TPL_DIR/template_name)
    changed={x.get("field_name") for x in changes if x.get("action")=="字段修改"}
    payload=record["payload"]
    fill_common(doc,payload.get("common",{}),changed)
    fill_data(doc,payload.get("data",[]),changed)
    if record["version"]>1:
        add_revision_appendix(doc,changes,record["record_no"],record["version"],
                              record.get("change_reason",""),record["owner"])
    out=io.BytesIO();doc.save(out);out.seek(0);return out
