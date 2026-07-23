from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import EXPERIMENTS
from .db import init_db, query, query_one
from .services import (
    confirm_return,
    create_commission,
    initial_record_data,
    review_task,
    save_task_data,
    submit_task,
    task_detail,
)


def _generic_value(field: dict[str, Any], index: int = 0) -> Any:
    if field.get("default") not in (None, ""):
        return field["default"]
    kind = field.get("kind")
    if kind == "select":
        return field.get("options", ["正常"])[0]
    if kind == "multiselect":
        return field.get("default") or field.get("options", [])[:1]
    if kind == "date":
        return "2026-07-23"
    if kind == "time":
        return f"{9 + index % 8:02d}:00"
    if kind == "textarea":
        return ""
    if kind == "json":
        return "{}"
    if kind in {"number", "integer"}:
        return 1 + index * 0.01
    return f"TEST-{index + 1:03d}"


def demo_record_data(task: dict[str, Any]) -> dict[str, Any]:
    code = task["experiment_code"]
    cfg = task["config"]
    data = initial_record_data(task)
    for idx, field in enumerate(cfg.get("run_fields", [])):
        data["run"][field["key"]] = _generic_value(field, idx)
    for idx, sample in enumerate(data["samples"]):
        for field_idx, field in enumerate(cfg.get("sample_fields", [])):
            sample[field["key"]] = _generic_value(field, idx + field_idx)
    if code == "roughness":
        data["run"].update({"standard_block_id": "RB-TEST", "standard_block_nominal": 10.0, "standard_block_m1": 9.9, "standard_block_m2": 10.0, "standard_block_m3": 10.1})
        for idx, sample in enumerate(data["samples"]):
            sample.update({"ra1": 6.0 + idx * 0.2, "ra2": 6.1 + idx * 0.2, "ra3": 6.2 + idx * 0.2, "surface_ok": "符合"})
    elif code == "crack_initiation":
        data["run"].update({"elastic_modulus": 200.0, "em_source": "TEST-MATERIAL-CERT", "fixture_id": "FIX-20", "span_actual": 20.0, "parallel_block_id": "PB-01", "software_file": "CURVE-CRACK"})
        for idx, sample in enumerate(data["samples"]):
            sample.update({"metal_t1": 0.50, "metal_t2": 0.51, "metal_t3": 0.50, "k_factor": 0.25, "failure_force": 120 + idx, "failure_mode": "典型裂纹萌生/剥离"})
    elif code == "xray":
        reference = {f"{i / 10:.1f}": [1000 - i * 80, 999 - i * 80, 1001 - i * 80] for i in range(1, 11)}
        data["run"].update({"density_strip_id": "DS-01", "density_nominal": 2.0, "density_m1": 2.00, "density_m2": 2.01, "density_m3": 1.99, "density_tolerance": 0.05, "reference_grays": json.dumps(reference, ensure_ascii=False)})
        for idx, sample in enumerate(data["samples"]):
            gray = 600 - idx * 5
            sample.update({
                "image_id": f"XRAY-{idx + 1:02d}",
                "roi1_m1": gray, "roi1_m2": gray + 1, "roi1_m3": gray - 1,
                "roi2_m1": gray + 2, "roi2_m2": gray + 1, "roi2_m3": gray,
                "roi3_m1": gray - 2, "roi3_m2": gray - 1, "roi3_m3": gray,
                "image_valid": "有效", "abnormal_shadow": "未见", "linear_indication": "未见",
                "local_missing": "未见", "bright_spot": "未见", "abnormal_detail": "",
            })
    elif code == "warpage":
        data["parameters"]["limit_abs"] = 0.5
        data["run"].update({"cutting_disc": "0.5 mm / LOT-01", "coolant_status": "正常", "data_path": "TRACE-WARPAGE"})
        for idx, sample in enumerate(data["samples"]):
            sample.update({"image_before": f"H1-{idx+1:02d}", "h1": 10.0 + idx * 0.01, "cut_start": "09:00", "cut_end": "09:05", "recut": "否", "image_after": f"H2-{idx+1:02d}", "h2": 9.8 + idx * 0.01})
    elif code == "thermal_expansion":
        data["run"].update({"software_version": "TEST-1.0", "pv_value": 55.0, "temperature_series": json.dumps({str(t): t * 0.35 for t in range(50, 551, 50)}, ensure_ascii=False), "data_path": "TRACE-CTE"})
        for idx, sample in enumerate(data["samples"]):
            sample.update({"l0": 25.0, "width_diameter": 3.0, "thickness": 2.0, "initial_pv": 55.0, "start_temp": 25.0, "end_temp": 550.0, "delta_l_um": 183.75 + idx, "curve_file": f"CTE-{idx+1:02d}", "valid": "有效"})
    elif code == "thermal_shock":
        data["run"].update({"oven_stable_temp": 100.0, "first_heat_actual": 20.0, "ice_readings": json.dumps({"试验前": 1.0, "第1批前": 1.1, "15min": 1.0}, ensure_ascii=False), "transfer_actual": 2.5, "ice_actual": 5.0, "second_heat_actual": 15.0, "cool_surface_temp": 23.0})
        for sample in data["samples"]:
            sample.update({"initial_abnormal": "无", "crack": "无", "chipping": "无", "fracture": "无", "defect_detail": ""})
    elif code == "bending":
        data["run"].update({"sensor_id": "SENSOR-2KN", "sensor_check": 1000.0, "fixture_id": "FIX-BEND", "software_version": "FastTest TEST", "data_path": "TRACE-BEND"})
        for idx, sample in enumerate(data["samples"]):
            sample.update({"length": 25.0, "width": 2.0, "height": 2.0, "span_actual": 20.0, "speed_actual": 1.0, "fmax": 320 + idx, "offset_stress": 850 + idx * 10, "data_file": f"BEND-{idx+1:02d}", "valid": "有效"})
    elif code == "vickers":
        data["run"].update({"standard_block_id": "BPGL-B007", "standard_block_nominal": 466.0, "block_m1": 465.0, "block_m2": 467.0, "block_m3": 466.0, "surface_confirm_method": ["目视/显微镜确认"], "surface_ra": 0.8, "data_path": "TRACE-HV"})
        for idx, sample in enumerate(data["samples"]):
            base = 460 + idx
            sample.update({
                "face1_hv1": base, "face1_hv2": base + 1, "face1_hv3": base - 1,
                "face2_hv1": base + 2, "face2_hv2": base + 1, "face2_hv3": base,
                "face1_surface": "合格", "face2_surface": "合格", "report_id": f"HV-{idx+1:02d}",
            })
    elif code == "thickness":
        data["run"].update({"gauge_block_id": "GB-001", "gauge_nominal": 1.0, "gauge_measured": 1.001, "software_version": "TEST-1.0", "fixing_method": "按SOP固定"})
        for idx, sample in enumerate(data["samples"]):
            for section in ("fixed", "middle", "free"):
                for point in (1, 2, 3):
                    sample[f"{section}_{point}"] = 1.0 + idx * 0.002 + point * 0.001
    elif code == "color_stability":
        data["run"].update({"observer1": "观察者甲", "observer2": "观察者乙", "observer3": "观察者丙", "xenon_id": "XE-01", "xenon_hours": 200.0, "filter_id": "FILTER-01", "filter_hours": 200.0, "surface_lux1": 150000.0, "surface_lux2": 149800.0, "surface_lux3": 150200.0, "bath_actual": 37.0, "exposure_actual": 24.0, "observation_date": "2026-07-24"})
        for idx, sample in enumerate(data["samples"]):
            sample.update({"shape": "圆片", "size": "直径50 mm", "shield_method": "试样夹", "position": f"P{idx+1}", "observer1_result": "未见明显差异", "observer2_result": "未见明显差异", "observer3_result": "未见明显差异", "comparison_note": "照射区与未照射区未见明显差异"})
    return data


def seed_full_demo(path: Path | None = None) -> int:
    init_db(path)
    existing = query_one(
        "SELECT id FROM commissions WHERE notes='V5.7全实验测试样例'",
        path=path,
    )
    if existing:
        return int(existing["id"])
    tester = query_one("SELECT id FROM users WHERE username='tester'", path=path)["id"]
    reviewer = query_one("SELECT id FROM users WHERE username='reviewer'", path=path)["id"]
    approver = query_one("SELECT id FROM users WHERE username='approver'", path=path)["id"]
    admin = query_one("SELECT id FROM users WHERE username='admin'", path=path)["id"]
    groups = []
    for code, cfg in EXPERIMENTS.items():
        quantity = min(cfg["sample_slots"], 6)
        groups.append(
            {
                "sample_name": f"测试样品-{cfg['name']}",
                "specification": "V5.7 TEST",
                "material": "钴铬合金" if code not in {"thermal_shock", "color_stability"} else "牙科材料",
                "batch_no": f"LOT-{code[:4].upper()}",
                "quantity": quantity,
                "receive_condition": "完好",
                "experiments": [code],
            }
        )
    commission_id = create_commission(
        client_name="V5.7测试委托单位",
        production_unit="V5.7测试生产单位",
        production_address="测试地址",
        received_date="2026-07-23",
        due_date="2026-08-23",
        groups=groups,
        main_tester_id=tester,
        reviewer_id=reviewer,
        approver_id=approver,
        created_by=admin,
        notes="V5.7全实验测试样例",
        path=path,
    )
    tasks = query("SELECT id FROM tasks WHERE commission_id=? ORDER BY id", (commission_id,), path)
    for row in tasks:
        task = task_detail(row["id"], path)
        data = demo_record_data(task)
        save_task_data(task["id"], data, tester, path)
        missing = submit_task(task["id"], tester, path)
        if missing:
            raise AssertionError(f"{task['experiment_code']}测试数据不完整：{missing}")
        review_task(task["id"], reviewer, True, "测试复核通过", path)
        confirm_return(task["id"], admin, "留样保存", "测试回库", path)
    return int(commission_id)

