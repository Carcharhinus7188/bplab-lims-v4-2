# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import lims_db
from experiment_engine import calculate_rows


ROOT = Path(__file__).parent


def main() -> None:
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'default=[],' in app_text
    assert "逐实验选择检测位置" in app_text
    assert "记录实验开始时间" in app_text
    assert "记录实验结束时间" in app_text
    assignment_block = app_text.split('elif page=="任务包分配":', 1)[1].split('elif page=="我的任务包":', 1)[0]
    assert "st.multiselect" not in assignment_block
    assert "experiment_codes=list(pending_map)" in assignment_block
    assert "本次任务包包含的检测项目与方法" not in assignment_block
    assert "本样品组待下发实验（自动继承，只读）" in assignment_block
    assert "收样员无需再次选择" in assignment_block
    assert "实时计算与判定" in (ROOT / "business_record_ui.py").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as temp_raw:
        temp = Path(temp_raw)
        lims_db.DB_PATH = temp / "workflow.db"
        lims_db.ATTACHMENT_DIR = temp / "attachments"
        lims_db.SIGNATURE_DIR = temp / "signatures"
        lims_db.init_db()
        ts = lims_db.now()
        with lims_db.connect() as connection:
            connection.execute(
                """INSERT INTO sample_groups(
                   id,group_no,commission_no,sample_name,model,material_name,quantity,
                   is_void,status,created_at,updated_at
                   ) VALUES(1,'BP20260724001','WT20260724001','测试试样','10×10','金属',1,0,
                   '等待实验员接收',?,?)""",
                (ts, ts),
            )
            connection.execute(
                """INSERT INTO samples(
                   sample_no,group_id,group_no,commission_no,sample_name,model,material_name,
                   condition,current_location,status,created_at,updated_at
                   ) VALUES('BP20260724001-01',1,'BP20260724001','WT20260724001',
                   '测试试样','10×10','金属','完好','A区域','等待实验员接收',?,?)""",
                (ts, ts),
            )
            connection.execute(
                """INSERT INTO task_packages(
                   package_no,commission_no,group_id,group_no,assignee,reviewer,material_name,
                   sample_nos,experiment_codes,experiments,status,assigned_by,assigned_at,
                   notified_at,created_at,updated_at
                   ) VALUES('BP20260724001-P01','WT20260724001',1,'BP20260724001',
                   'tester','reviewer','金属',?,?,?,'待接收','receiver',?,?,?,?)""",
                (
                    json.dumps(["BP20260724001-01"], ensure_ascii=False),
                    json.dumps(["R001", "R011"], ensure_ascii=False),
                    json.dumps(["表面粗糙度试验", "维氏硬度试验"], ensure_ascii=False),
                    ts, ts, ts, ts,
                ),
            )
            for task_no, code, experiment in (
                ("BP20260724001-P01-T01", "R001", "表面粗糙度试验"),
                ("BP20260724001-P01-T02", "R011", "维氏硬度试验"),
            ):
                connection.execute(
                    """INSERT INTO tasks(
                       task_no,package_no,commission_no,group_id,group_no,sample_nos,
                       experiment_code,experiment,method_code,standard,material_name,
                       assignee,reviewer,status,created_at,updated_at
                       ) VALUES(?,'BP20260724001-P01','WT20260724001',1,'BP20260724001',
                       ?,?,?,?,'测试标准','金属','tester','reviewer','待接收',?,?)""",
                    (
                        task_no,
                        json.dumps(["BP20260724001-01"], ensure_ascii=False),
                        code,
                        experiment,
                        "测试方法",
                        ts,
                        ts,
                    ),
                )

        location_map = {
            "BP20260724001-P01-T01": "性能检测室",
            "BP20260724001-P01-T02": "显微检测室",
        }
        lims_db.accept_package(
            "BP20260724001-P01",
            "tester",
            "样品已收到，确认完好",
            location_map,
            "逐实验地点测试",
        )
        tasks = lims_db.package_tasks("BP20260724001-P01")
        assert {item["task_no"]: item["detection_location"] for item in tasks} == location_map

        first = tasks[0]["task_no"]
        lims_db.mark_task_experiment_time(first, "tester", "开始")
        lims_db.mark_task_experiment_time(first, "tester", "结束")
        first_task = lims_db.task(first)
        assert first_task and first_task["experiment_started_at"] and first_task["experiment_ended_at"]

        live = calculate_rows(
            "rough",
            [{"sample_no": "BP20260724001-01", "ra1": 5.0, "ra2": 6.0, "ra3": 7.0, "limit": 15.0}],
        )[0]
        assert live["mean"] == 6.0
        assert live["conclusion"] == "符合"

        # Confirm an existing V5.7 database receives only additive columns.
        legacy_path = temp / "legacy.db"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute("CREATE TABLE tasks(task_no TEXT PRIMARY KEY)")
        lims_db.DB_PATH = legacy_path
        lims_db.init_db()
        with lims_db.connect() as connection:
            columns = {item[1] for item in connection.execute("PRAGMA table_info(tasks)")}
        assert {"detection_location", "experiment_started_at", "experiment_ended_at"} <= columns

    print("V5.7.3 WORKFLOW UPDATE PASSED: automatic task inheritance, locations, timeline and live results")


if __name__ == "__main__":
    main()
