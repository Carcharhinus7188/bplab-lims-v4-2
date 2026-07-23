# -*- coding: utf-8 -*-
from pathlib import Path
import tempfile, zipfile
from docx import Document
import lims_db
from constants import EXPERIMENTS
from template_record_engine import template_manifest,prefill_template_fields,complete_demo_values,validate_template_fields,completion_summary
from record_word_engine import export_record
from trace_excel_engine import build_internal_trace_workbook


def _structure(path):
    doc=Document(path)
    return {"paragraphs":len(doc.paragraphs),"tables":len(doc.tables),"sections":len(doc.sections),"table_rows":[len(t.rows) for t in doc.tables],"table_cols":[len(t.columns) for t in doc.tables]}


def _demo_context(experiment):
    return {"client_name":"测试委托客户","client_address":"测试地址","production_unit":"测试生产单位","product_no":"TEST-BATCH-001","sample_name":"测试试样","model":"25 mm×2 mm×2 mm","material":"钴铬合金","sample_nos":["BP20260723001-01","BP20260723001-02","BP20260723001-03"],"sample_quantity":3,"received_date":"2026-07-23","report_no":"WT20260723001","task_no":"BP20260723001-P01-T01","test_date":"2026-07-23","detection_location":"性能检测室","standard":EXPERIMENTS[experiment]["std"],"operator":"测试实验员","reviewer":"测试复核员"}


def main():
    assert len(EXPERIMENTS)==10
    assert len({cfg["template"] for cfg in EXPERIMENTS.values()})==10
    demo_equipment=[
        {"management_no":"BPGL-A021","equipment_name":"电子万能试验机","model":"STS50K","measuring_range":"（0～50）kN；（0～2000）N","calibration_time":"2026.7","lifecycle_status":"启用","binding_role":"主设备","required":1},
        {"management_no":"BPGL-A035","equipment_name":"数显维氏硬度计","model":"HV-30Z","measuring_range":"HV10","calibration_time":"2026.7","lifecycle_status":"启用","binding_role":"主设备","required":1},
        {"management_no":"BPGL-A036","equipment_name":"粗糙度仪","model":"TR200","measuring_range":"±160 μm","calibration_time":"2026.7","lifecycle_status":"启用","binding_role":"主设备","required":1},
    ]
    with tempfile.TemporaryDirectory() as td_raw:
        td=Path(td_raw)
        for experiment,cfg in EXPERIMENTS.items():
            template=cfg["template"];template_path=Path(__file__).parent/"templates"/template
            before=_structure(template_path);manifest=template_manifest(template);assert manifest,template
            defaults=prefill_template_fields(template,_demo_context(experiment),demo_equipment,{})
            completed=complete_demo_values(template,defaults)
            assert not validate_template_fields(template,completed),template
            summary=completion_summary(template,completed);assert summary["completed"]==summary["total"] and summary["missing"]==0
            record={"record_no":"DEMO-"+cfg["key"],"task_no":"DEMO-"+cfg["key"],"version":1,"experiment":experiment,"payload":{"template_fields":completed}}
            buffer=export_record(record,template,[]);generated=td/f"{cfg['key']}_{template}";generated.write_bytes(buffer.getvalue())
            assert generated.stat().st_size>5000
            assert before==_structure(generated),(template,before,_structure(generated))

        lims_db.DB_PATH=td/"test.db";lims_db.ATTACHMENT_DIR=td/"attachments";lims_db.SIGNATURE_DIR=td/"signatures";lims_db.init_db()
        assert lims_db.authenticate("admin","admin123");assert len(lims_db.list_equipment(True))==88;assert len(lims_db.current_config_overview())==10
        lims_db.add_organization({"org_code":"C001","org_name":"测试客户","short_name":"客户","is_client":True,"is_manufacturer":False,"is_contract_manufacturer":False,"address":"测试地址","contact":"联系人","phone":"13800000000","credit_code":"","notes":""},"admin")
        lims_db.add_organization({"org_code":"M001","org_name":"测试生产单位","short_name":"生产单位","is_client":False,"is_manufacturer":True,"is_contract_manufacturer":False,"address":"","contact":"","phone":"","credit_code":"","notes":""},"admin")
        orgs=lims_db.list_organizations();client=next(x for x in orgs if x["org_code"]=="C001");producer=next(x for x in orgs if x["org_code"]=="M001");method=lims_db.experiment_method_by_name("维氏硬度试验")
        lims_db.add_catalog({"sample_code":"S001","sample_name":"测试金属试样","model":"10 mm×10 mm×1 mm","material_name":"钴铬合金","category":"金属","unit":"件","experiment_codes":[method["experiment_code"]],"notes":""},"admin")
        catalog=next(x for x in lims_db.list_catalog() if x["sample_code"]=="S001");cn="WT20260723001"
        lims_db.create_commission({"commission_no":cn,"client_org_id":client["id"],"client_name":client["org_name"],"client_address":client["address"],"contact":client["contact"],"phone":client["phone"],"production_org_id":producer["id"],"production_org_name":producer["org_name"],"production_relation":"生产单位","commission_date":"2026-07-23","due_date":"2026-08-23","subcontract_allowed":"否","report_medium":"电子档","conformity_judgment":"是","uncertainty":"否","delivery_method":"Email","cnas_mark":"否","capability":"完全满足","notes":""},[{"group_no":"BP20260723001","catalog_id":catalog["id"],"sample_name":catalog["sample_name"],"model":catalog["model"],"material_name":catalog["material_name"],"product_no":"B001","quantity":3,"unit":"件","condition":"完好","condition_note":"","storage_area":"A区域","notes":"","experiment_codes":[method["experiment_code"]]}],"receiver")
        group=lims_db.commission_groups(cn)[0];pn=lims_db.create_task_package(group["id"],[method["experiment_code"]],"tester","reviewer","receiver");task=lims_db.package_tasks(pn)[0];lims_db.accept_package(pn,"tester","样品已收到，确认完好","性能检测室","正常")
        snapshot=lims_db.task_config_snapshot(task["task_no"]);assert snapshot["record_template_file"]=="RECORD_R011_VICKERS.docx";assert len(snapshot["snapshot_hash"])==64
        context=_demo_context("维氏硬度试验");context.update({"task_no":task["task_no"],"sample_nos":task["sample_nos_list"],"sample_quantity":len(task["sample_nos_list"])})
        fields=complete_demo_values(snapshot["record_template_file"],prefill_template_fields(snapshot["record_template_file"],context,snapshot["equipment"],{}))
        payload={"common":{"record_no":task["task_no"],"task_no":task["task_no"],"commission_no":cn,"report_no":cn,"client":"测试客户","sample_name":"测试金属试样","sample_no":"、".join(task["sample_nos_list"]),"model":"10 mm×10 mm×1 mm","material":"钴铬合金","method_code":snapshot["method_code"],"standard":snapshot["standard"],"test_date":"2026-07-23","operator":"测试实验员","reviewer":"测试复核员"},"template_name":snapshot["record_template_file"],"template_fields":fields,"equipment_snapshot":snapshot["equipment"],"deviation":"无","retest":"否","report_summary":"维氏硬度试验结果详见原始记录。","report_conclusion":"合格","attachments":[],"configuration_snapshot":snapshot}
        lims_db.save_record(task["task_no"],1,payload,"tester","待复核",snapshot["record_template_version"] or "A/0",snapshot["sop_version"] or "A/0");lims_db.review_record(task["task_no"],1,"reviewer","通过","通过")
        rec=lims_db.record(task["task_no"],1);rec["kind"]=snapshot["kind"];exported=export_record(rec,snapshot["record_template_file"],[]);final_doc=td/"final_record.docx";final_doc.write_bytes(exported.getvalue());assert _structure(final_doc)==_structure(Path(__file__).parent/"templates"/snapshot["record_template_file"])
        attachment_id=lims_db.save_attachment({"commission_no":cn,"package_no":pn,"task_no":task["task_no"],"sample_no":task["sample_nos_list"][0],"attachment_type":"实验过程照片","original_name":"test.jpg","captured_at":"2026-07-23 10:00:00","description":"过程照片","is_original":True},b"test-image-content","tester")
        attachments=lims_db.list_attachments(task_no=task["task_no"]);assert attachments and attachments[0]["attachment_id"]==attachment_id;assert "equipment_software" not in attachments[0]
        xlsx=Path(__file__).parent/"templates"/"INTERNAL_TRACE_WORKBOOK.xlsx"
        with zipfile.ZipFile(xlsx) as archive:
            combined="".join(archive.read(name).decode("utf-8","ignore") for name in archive.namelist() if name.endswith(".xml"))
        assert "设备或软件" not in combined and "软件或设备" not in combined
        dynamic=build_internal_trace_workbook(cn)
        dynamic_path=td/"trace.xlsx";dynamic_path.write_bytes(dynamic.getvalue())
        with zipfile.ZipFile(dynamic_path) as archive:
            assert archive.testzip() is None
            combined="".join(archive.read(name).decode("utf-8","ignore") for name in archive.namelist() if name.endswith(".xml"))
        assert "设备或软件" not in combined and "软件或设备" not in combined
        assert "附件编号" in combined and "实验总台账" in combined
    print("SMOKE TEST PASSED: exact templates, complete fields, attachment separation, Excel trace and full workflow")

if __name__=="__main__":main()
