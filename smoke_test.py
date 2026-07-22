# -*- coding: utf-8 -*-
from pathlib import Path
import tempfile

import lims_db
from constants import EXPERIMENTS
from experiment_engine import initial_parameters, initial_rows, calculate_rows
from form_engine import commission_document, sample_register_document, loan_return_document, report_document
from record_word_engine import export_record


def main() -> None:
    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        lims_db.DB_PATH = td / "test.db"
        lims_db.ATTACHMENT_DIR = td / "attachments"
        lims_db.SIGNATURE_DIR = td / "signatures"
        lims_db.init_db()

        assert lims_db.authenticate("admin", "admin123")
        lims_db.add_organization({
            "org_code": "C001", "org_name": "测试客户", "short_name": "客户",
            "is_client": True, "is_manufacturer": False, "is_contract_manufacturer": False,
            "address": "测试地址", "contact": "联系人", "phone": "13800000000",
            "credit_code": "", "notes": "",
        }, "admin")
        lims_db.add_organization({
            "org_code": "M001", "org_name": "测试生产单位", "short_name": "生产单位",
            "is_client": False, "is_manufacturer": True, "is_contract_manufacturer": False,
            "address": "", "contact": "", "phone": "", "credit_code": "", "notes": "",
        }, "admin")
        orgs = lims_db.list_organizations()
        client = next(x for x in orgs if x["org_code"] == "C001")
        producer = next(x for x in orgs if x["org_code"] == "M001")

        lims_db.add_catalog({
            "sample_code": "S001", "sample_name": "钴铬合金试样", "model": "25×2×2 mm",
            "material_name": "钴铬合金", "default_org_id": producer["id"], "category": "金属",
            "unit": "件", "default_experiments": ["维氏硬度试验", "弯曲性能试验"],
            "default_methods": ["GB/T 4340.1", "YY/T 1702"], "notes": "",
        }, "admin")
        catalog = next(x for x in lims_db.list_catalog() if x["sample_code"] == "S001")

        commission_no = "WT20260722001"
        lims_db.create_commission({
            "commission_no": commission_no, "client_org_id": client["id"],
            "client_name": client["org_name"], "client_address": client["address"],
            "contact": client["contact"], "phone": client["phone"],
            "commission_date": "2026-07-22", "due_date": "2026-08-22",
            "subcontract_allowed": "否", "report_medium": "电子档",
            "conformity_judgment": "是", "uncertainty": "否",
            "delivery_method": "Email", "cnas_mark": "否", "capability": "完全满足",
            "method_choices": ["GB/T 4340.1", "YY/T 1702"], "notes": "",
        }, [{
            "group_no": "BP20260722001", "catalog_id": catalog["id"],
            "sample_name": catalog["sample_name"], "model": catalog["model"],
            "material_name": catalog["material_name"], "production_org_id": producer["id"],
            "production_org_name": producer["org_name"], "production_relation": "生产单位",
            "product_no": "B001", "quantity": 3, "unit": "件", "condition": "完好",
            "condition_note": "", "storage_area": "A区域", "notes": "",
            "experiments": ["维氏硬度试验", "弯曲性能试验"],
            "methods": ["GB/T 4340.1", "YY/T 1702"],
            "experiment_methods": {"维氏硬度试验": "GB/T 4340.1", "弯曲性能试验": "YY/T 1702"},
            "standards": {
                "维氏硬度试验": EXPERIMENTS["维氏硬度试验"]["std"],
                "弯曲性能试验": EXPERIMENTS["弯曲性能试验"]["std"],
            },
        }], "receiver")

        group = lims_db.commission_groups(commission_no)[0]
        sample_numbers = [x["sample_no"] for x in lims_db.group_samples(group["id"])]
        assert sample_numbers == [
            "BP20260722001-01", "BP20260722001-02", "BP20260722001-03"
        ]

        package_no = lims_db.create_task_package(
            group["id"], ["维氏硬度试验", "弯曲性能试验"], "tester", "reviewer", "receiver"
        )
        lims_db.accept_package(package_no, "tester", "样品已收到，确认完好", "力学实验室", "正常")

        for task in lims_db.package_tasks(package_no):
            kind = EXPERIMENTS[task["experiment"]]["kind"]
            data_rows = initial_rows(kind, task["sample_nos_list"])
            if kind == "hv":
                for row in data_rows:
                    row.update(indent1=500, indent2=510, indent3=520)
            if kind == "bend":
                for row in data_rows:
                    row.update(stress_02=900)
            data_rows = calculate_rows(kind, data_rows)
            payload = {
                "common": {
                    "record_no": task["task_no"], "task_no": task["task_no"],
                    "commission_no": commission_no, "report_no": commission_no,
                    "client": client["org_name"], "sample_name": catalog["sample_name"],
                    "sample_no": "、".join(task["sample_nos_list"]), "model": catalog["model"],
                    "material": catalog["material_name"], "method_code": task["method_code"],
                    "standard": task["standard"], "test_date": "2026-07-22",
                    "operator": "实验员张工", "reviewer": "复核员李工",
                },
                "parameters": initial_parameters(kind, {}, "力学实验室"),
                "data": data_rows, "deviation": "", "attachments": [],
            }
            lims_db.save_record(task["task_no"], 1, payload, "tester", "待复核")
            lims_db.review_record(task["task_no"], 1, "reviewer", "通过", "通过")

        assert lims_db.package(package_no)["status"] == "待归还"
        assert lims_db.report(commission_no)["status"] == "待检测员确认"

        loans = lims_db.package_loan_rows(package_no)
        lims_db.submit_package_return(package_no, "tester", [
            {"sample_no": x["sample_no"], "condition": "完好", "note": ""} for x in loans
        ])
        lims_db.confirm_package_return(package_no, "store", [
            {"sample_no": x["sample_no"], "location": "B区域"} for x in loans
        ])
        assert lims_db.package(package_no)["status"] == "已回库"

        c = lims_db.commission(commission_no)
        groups = lims_db.commission_groups(commission_no)
        samples = lims_db.commission_samples(commission_no)
        tests = lims_db.commission_tests(commission_no)
        users = {x["username"]: x["display_name"] for x in lims_db.list_users()}

        documents = {
            "commission.docx": commission_document(c, groups, tests, users["receiver"]),
            "sample_register.docx": sample_register_document(c, groups, samples, tests, users["receiver"]),
            "loan_return.docx": loan_return_document(lims_db.commission_loans(commission_no), users),
        }
        tasks = lims_db.commission_tasks(commission_no)
        group_map = {g["id"]: g for g in groups}
        for task in tasks:
            task["kind"] = EXPERIMENTS[task["experiment"]]["kind"]
            task["sample_name"] = group_map[task["group_id"]]["sample_name"]
            record = lims_db.record(task["task_no"], 1)
            record["kind"] = task["kind"]
            documents[f"{task['task_no']}.docx"] = export_record(
                record, EXPERIMENTS[task["experiment"]].get("template"), []
            )
        documents["report.docx"] = report_document(
            c, groups, samples, tasks, lims_db.report_records(commission_no),
            lims_db.report(commission_no), users, {}
        )
        for name, buffer in documents.items():
            path = td / name
            path.write_bytes(buffer.getvalue())
            assert path.stat().st_size > 5000, name

    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
