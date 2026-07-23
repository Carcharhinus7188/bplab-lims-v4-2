# -*- coding: utf-8 -*-
from pathlib import Path
import tempfile
import lims_db
from constants import DETECTION_LOCATIONS
from experiment_engine import initial_parameters, initial_rows, calculate_rows
from record_word_engine import export_record


def main():
    with tempfile.TemporaryDirectory() as td_raw:
        td=Path(td_raw)
        lims_db.DB_PATH=td/"test.db";lims_db.ATTACHMENT_DIR=td/"attachments";lims_db.SIGNATURE_DIR=td/"signatures"
        lims_db.init_db()
        assert lims_db.authenticate("admin","admin123")
        equipment=lims_db.list_equipment(True)
        assert len(equipment)==88
        assert len(lims_db.current_config_overview())==10
        assert all(x["config_version"]=="V1.0" for x in lims_db.current_config_overview())

        # Add a future device and a future experiment without changing program code.
        lims_db.save_equipment({"seq":89,"equipment_name":"动态测试设备","model":"T-1","measuring_range":"0～100","manufacturer":"测试厂家","serial_no":"SN001","management_no":"BPGL-A999","purchase_time":"2026.7","calibration_time":"2026.7","responsible":"测试员","equipment_class":"A类","lifecycle_status":"启用","status_note":"","enabled":True,"notes":"动态配置测试"},"admin")
        lims_db.save_experiment_method({"experiment_name":"动态通用实验","method_code":"TEST-001","standard":"测试方法第一版","category":"动态测试","kind":"generic","sort_order":99,"enabled":True},"admin")
        method=lims_db.experiment_method_by_name("动态通用实验")
        cid=lims_db.create_experiment_config_version(method["experiment_code"],"V1.0","admin",False)
        lims_db.save_experiment_config(cid,{"experiment_name":"动态通用实验","method_code":"TEST-001","standard":"测试方法第一版","category":"动态测试","kind":"generic","default_location":"性能检测室","sop_version":"","record_template_version":"","software":"TestSoft 1.0","effective_date":"2026-07-23","note":"首版"},"admin")
        lims_db.bind_config_equipment(cid,"BPGL-A999","主设备",True,1,"动态主设备","admin")
        lims_db.publish_experiment_config(cid,"admin","测试发布")
        assert lims_db.current_experiment_config(method["experiment_code"])["version"]=="V1.0"

        lims_db.add_organization({"org_code":"C001","org_name":"测试客户","short_name":"客户","is_client":True,"is_manufacturer":False,"is_contract_manufacturer":False,"address":"测试地址","contact":"联系人","phone":"13800000000","credit_code":"","notes":""},"admin")
        lims_db.add_organization({"org_code":"M001","org_name":"测试生产单位","short_name":"生产单位","is_client":False,"is_manufacturer":True,"is_contract_manufacturer":False,"address":"","contact":"","phone":"","credit_code":"","notes":""},"admin")
        orgs=lims_db.list_organizations();client=next(x for x in orgs if x["org_code"]=="C001");producer=next(x for x in orgs if x["org_code"]=="M001")
        lims_db.add_catalog({"sample_code":"S001","sample_name":"动态试样","model":"10×10","material_name":"测试材料","category":"测试","unit":"件","experiment_codes":[method["experiment_code"]],"notes":""},"admin")
        catalog=next(x for x in lims_db.list_catalog() if x["sample_code"]=="S001")
        cn="WT20260723001"
        lims_db.create_commission({"commission_no":cn,"client_org_id":client["id"],"client_name":client["org_name"],"client_address":client["address"],"contact":client["contact"],"phone":client["phone"],"production_org_id":producer["id"],"production_org_name":producer["org_name"],"production_relation":"生产单位","commission_date":"2026-07-23","due_date":"2026-08-23","subcontract_allowed":"否","report_medium":"电子档","conformity_judgment":"是","uncertainty":"否","delivery_method":"Email","cnas_mark":"否","capability":"完全满足","notes":""},[{"group_no":"BP20260723001","catalog_id":catalog["id"],"sample_name":catalog["sample_name"],"model":catalog["model"],"material_name":catalog["material_name"],"product_no":"B001","quantity":2,"unit":"件","condition":"完好","condition_note":"","storage_area":"A区域","notes":"","experiment_codes":[method["experiment_code"]]}],"receiver")
        group=lims_db.commission_groups(cn)[0]
        pn=lims_db.create_task_package(group["id"],[method["experiment_code"]],"tester","reviewer","receiver")
        task=lims_db.package_tasks(pn)[0]
        snap=lims_db.task_config_snapshot(task["task_no"])
        assert snap["config_version"]=="V1.0"
        assert snap["equipment"][0]["management_no"]=="BPGL-A999"
        assert len(snap["snapshot_hash"])==64

        # Publish V2 after task creation. The task must retain V1 snapshot.
        cid2=lims_db.create_experiment_config_version(method["experiment_code"],"V2.0","admin",True)
        lims_db.save_experiment_config(cid2,{"experiment_name":"动态通用实验","method_code":"TEST-002","standard":"测试方法第二版","category":"动态测试","kind":"generic","default_location":"显微检测室","sop_version":"","record_template_version":"","software":"TestSoft 2.0","effective_date":"2026-08-01","note":"方法升级"},"admin")
        lims_db.publish_experiment_config(cid2,"admin","第二版")
        snap_after=lims_db.task_config_snapshot(task["task_no"])
        assert snap_after["config_version"]=="V1.0"
        assert snap_after["method_code"]=="TEST-001"
        assert lims_db.current_experiment_config(method["experiment_code"])["version"]=="V2.0"

        lims_db.accept_package(pn,"tester","样品已收到，确认完好","性能检测室","正常")
        rows=initial_rows("generic",task["sample_nos_list"])
        for row in rows:row.update(measurement_item="测试值",raw_value="12.3",unit="mm",calculated_value="12.3",conclusion="符合")
        payload={"common":{"record_no":task["task_no"],"task_no":task["task_no"],"commission_no":cn,"report_no":cn,"client":"测试客户","sample_name":"动态试样","sample_no":"、".join(task["sample_nos_list"]),"model":"10×10","material":"测试材料","method_code":snap["method_code"],"standard":snap["standard"],"test_date":"2026-07-23","operator":"实验员","reviewer":"复核员"},"parameters":initial_parameters("generic",{"software":snap["software"]},"性能检测室"),"equipment_snapshot":[{"管理编号":"BPGL-A999","设备名称":"动态测试设备","型号规格":"T-1","设备角色":"主设备","必需设备":"是","台账校准时间":"2026.7","任务快照状态":"启用","本次使用":"是","使用前状态":"正常","异常说明":""}],"data":calculate_rows("generic",rows),"deviation":"","retest":"否","attachments":[],"configuration_snapshot":snap}
        lims_db.save_record(task["task_no"],1,payload,"tester","待复核",snap.get("record_template_version") or "A/0",snap.get("sop_version") or "A/0")
        lims_db.review_record(task["task_no"],1,"reviewer","通过","通过")
        rec=lims_db.record(task["task_no"],1);rec["kind"]="generic"
        buf=export_record(rec,"",[])
        assert len(buf.getvalue())>5000

        # Disabled/repair required equipment blocks new config publication.
        lims_db.save_equipment({**lims_db.equipment_item("BPGL-A999"),"equipment_name":"动态测试设备","lifecycle_status":"维修","enabled":False},"admin")
        cid3=lims_db.create_experiment_config_version(method["experiment_code"],"V3.0","admin",True)
        try:
            lims_db.publish_experiment_config(cid3,"admin","应失败")
            raise AssertionError("publication should fail")
        except ValueError:
            pass

    print("SMOKE TEST PASSED: dynamic experiments, equipment, version publication and immutable task snapshots")

if __name__=="__main__":main()
