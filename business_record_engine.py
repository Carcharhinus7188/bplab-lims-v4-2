# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

from experiment_engine import initial_parameters, initial_rows, calculate_rows, result_summary, schema
from template_record_engine import (
    template_manifest,
    prefill_template_fields,
    _compose_cell_text,
    _norm,
)

# Fields that are supplied by the workflow, equipment snapshot or attachment index.
HIDDEN_PARAMETER_KEYS = {
    "detection_location", "software", "data_path", "start_time", "end_time",
    "equipment_name", "equipment_model", "equipment_no",
    "calibration_certificate", "calibration_due", "equipment_status",
    "image_path", "image_before_path", "image_after_path", "curve_path",
}

# These fields always remain visible because they are actual conditions at the time of testing.
ALWAYS_EDIT_PARAMETER_KEYS = {
    "test_date", "temperature_before", "temperature_after",
    "humidity_before", "humidity_after",
}

# File/index fields are filled from the internal trace index rather than manually repeated.
AUTO_ROW_KEYS = {
    "file_no", "curve_no", "image_no", "photo_no", "image_path", "data_path",
}

# Optional fields do not prevent submission when left empty.
OPTIONAL_PARAMETER_KEYS = {
    "cutoff_filter", "measurement_direction", "zero_force", "atmosphere",
    "pv_range", "objective", "magnification", "calibration_scale",
    "observer_1", "observer_2", "observer_3", "lamp_no", "lamp_hours",
    "filter_no", "filter_hours", "background", "sample_preparation",
    "procedure_summary", "acceptance_criteria", "test_conditions",
    "spindle_speed", "metal_batch", "em_source_file", "parallel_block_no",
} | {
    f"monitor_{point}_note" for point in range(1, 6)
} | {
    f"color_monitor_{point}_note" for point in range(1, 7)
}
OPTIONAL_ROW_KEYS = {
    "position", "note", "crack_position", "thickness_relation",
    "estimated_thickness", "defect", "edge_condition", "control_no",
    "shape", "size", "cover_method", "cover_direction", "position",
    "measurement_item", "unit", "calculated_value",
    "retest_mean", "failure_mode", "retake", "cut_start", "cut_end",
}

PRECHECKS = {
    "rough": ["样品编号已核对", "Z轴方向标识清晰", "试样表面清洁", "探针状态正常", "测量平台水平稳定"],
    "mc_crack": ["样品编号已核对", "金属与陶瓷层外观正常", "夹具跨距已确认", "试样居中放置", "加载前力值已清零"],
    "xray": ["样品表面清洁干燥", "检测区域无无关人员", "辐射警示装置正常", "防护装置有效", "操作人员已授权"],
    "warp": ["打印及后处理已完成", "样品表面无污染", "样品无裂纹", "样品编号已核对", "切割前基准线清晰"],
    "cte": ["样品编号已核对", "试样安装牢固", "测温系统状态正常", "升温程序已核对", "基线稳定"],
    "shock": ["样品外观完好", "烘箱温度稳定", "冰水已准备", "计时器状态正常", "观察照度符合要求"],
    "bend": ["样品编号已核对", "试样表面无影响试验的缺陷", "夹具平行度已确认", "支点距离已确认", "挠度计接触状态正常", "加载前力值已清零"],
    "hv": ["样品编号已核对", "测试面平整清洁", "压头状态正常", "测量镜头清晰", "标准硬度块核查合格", "试样与压头轴线垂直"],
    "thickness": ["样品编号已核对", "试样表面已清洁", "试样已完成恒温平衡", "测量系统核查合格", "测量点位已确认"],
    "color": ["样品与对照编号已核对", "观察人员资格已确认", "D65灯箱状态正常", "照射条件已确认", "观察背景已准备"],
    "generic": ["样品编号已核对", "设备状态正常", "试验条件已确认"],
}

# Logical defaults for single-choice fields. They can be changed by the experimenter.
SELECT_DEFAULTS = {
    "standard_block_result": "合格",
    "probe_condition": "正常",
    "platform_level": "符合",
    "surface_state": "原打印表面",
    "parallel_check": "符合",
    "orientation": "金属面朝上、陶瓷面朝下",
    "radiation_safety": "允许曝光",
    "baseline_before": "符合",
    "coolant": "持续供给",
    "baseline_after": "符合",
    "sample_install": "牢固",
    "crack": "无", "chipping": "无", "fracture": "无",
    "fixture_parallel": "是",
    "deflectometer_contact": "轻微接触",
    "standard_block_result": "合格",
    "surface_condition": "平整清洁",
    "perpendicularity": "符合",
    "calibration_result": "合格",
    "source_type": "氙灯",
    "water_medium": "蒸馏水",
    "background": "N5中性灰",
    "cover_secure": "是",
    "image_valid": "有效",
    "iqi_display": "清晰",
    "sample_state": "完整",
    "indent_quality": "有效",
    "observer1": "未见明显差异",
    "observer2": "未见明显差异",
    "observer3": "未见明显差异",
    "environment_interference": "无明显干扰",
    "parameter_adjustment": "无调整",
    "coolant_status": "是",
    "remade": "否",
    "initial_appearance": "无异常",
    "sample_status": "完好",
    "retake": "否",
    "installation_direction": "正确",
    "sample_secure": "是",
    "run_status": "正常",
    "auto_stop": "是",
    "validity": "有效",
    "surface_confirm": "符合",
    "start_permission": "可以开始试验",
    "indent_measurement_method": "软件自动",
    "report_exported": "是",
    "observer_qualification": "均已确认合格",
    "lamp_box_ready": "已完成",
}

# Additional aliases for mapping concise business fields back into controlled templates.
PARAM_ALIASES = {
    "test_date": ["检测日期", "测量日期", "观察日期"],
    "temperature_before": ["检测前温度", "试验前", "环境温度"],
    "temperature_after": ["检测后温度", "试验中", "检查前"],
    "humidity_before": ["检测前湿度", "相对湿度", "试验前"],
    "humidity_after": ["检测后湿度", "试验中", "检查前"],
    "start_time": ["检测开始时间", "实验开始时间", "开始时间"],
    "end_time": ["检测结束时间", "实验结束时间", "结束时间"],
    "standard_block": ["标准粗糙度样板", "标准样板", "标准块编号"],
    "standard_block_nominal": ["标准样板标称值", "标称值"],
    "standard_block_measured": ["标准样板实测值", "实测值"],
    "repeat_check_1": ["核查重复性1", "连续测量1"],
    "repeat_check_2": ["核查重复性2", "连续测量2"],
    "repeat_check_3": ["核查重复性3", "连续测量3"],
    "standard_block_result": ["标准样板核查结果", "标准硬度块核查结果", "核查结果"],
    "sampling_length": ["取样长度"],
    "evaluation_length": ["评定长度"],
    "measuring_speed": ["测量速度"],
    "cutoff_filter": ["滤波", "计算标准"],
    "probe_condition": ["探针状态"],
    "platform_level": ["工作台水平", "平台水平"],
    "surface_state": ["试样表面状态", "样品表面状态"],
    "measurement_direction": ["测量方向"],
    "fixture_no": ["夹具编号"],
    "support_span": ["支承跨距", "支点距离", "实测跨距"],
    "loading_speed": ["加载速度"],
    "observation_method": ["观察方式", "裂纹萌生观察"],
    "parallel_check": ["夹具平行", "平行与居中"],
    "zero_force": ["清零后力值", "清零后力"],
    "orientation": ["试样放置方向", "样品摆放方向"],
    "radiation_safety": ["辐射安全确认", "允许曝光"],
    "xray_model": ["X射线机型号", "X射线机编号"],
    "panel_no": ["数据采集板编号"],
    "iqi_no": ["像质计编号", "孔型像质计编号"],
    "density_meter_no": ["密度计", "标准密度片"],
    "tube_voltage": ["管电压"],
    "tube_current": ["管电流"],
    "exposure_time": ["曝光时间", "照射时间"],
    "mas": ["管电流时间积", "mAs"],
    "focus_mode": ["焦点模式"],
    "image_device_no": ["影像测量仪编号", "二次元影像仪编号"],
    "cutting_device_no": ["切割设备编号"],
    "measurement_function": ["测量功能"],
    "baseline_before": ["切割前基准线确认"],
    "coolant": ["切割冷却液状态", "冷却液状态"],
    "cut_position": ["切割位置", "切割方向"],
    "baseline_after": ["切割后基准线确认"],
    "start_temperature": ["起始温度"],
    "end_temperature": ["终止温度"],
    "heating_rate": ["升温速率"],
    "atmosphere": ["试验气氛"],
    "pv_range": ["PV值", "稳定范围"],
    "sample_install": ["试样安装状态", "样品安装状态"],
    "oven_temperature": ["烘箱温度"],
    "first_heating_time": ["首次加热时间"],
    "transfer_time": ["转移时间"],
    "ice_water_temperature": ["冰水温度"],
    "immersion_time": ["冰水浸泡时间"],
    "second_heating_time": ["再次加热时间"],
    "cooling_temperature": ["观察前冷却温度", "冷却温度"],
    "illumination": ["观察照度", "照度"],
    "magnification": ["放大倍数", "测量放大倍率"],
    "timer_no": ["计时器编号"],
    "thermometer_no": ["温度计编号"],
    "printing_process": ["打印工艺", "打印设备"],
    "heat_treatment_record": ["热处理记录编号"],
    "printing_direction": ["打印方向", "成型方向"],
    "force_sensor": ["力传感器编号", "2000N力传感器"],
    "deflectometer": ["挠度计", "变形测量装置编号"],
    "speed": ["位移速度", "速度"],
    "specified_strain": ["规定应变"],
    "roller_radius": ["压头", "支点R"],
    "fixture_parallel": ["上压头", "下支撑平行"],
    "max_gap": ["最大间隙"],
    "deflectometer_contact": ["挠度计状态", "接触状态"],
    "method": ["试验力级别", "硬度标尺"],
    "test_force": ["试验力"],
    "dwell_time": ["保荷时间"],
    "standard_block_no": ["标准硬度块编号", "标称值"],
    "standard_block_result": ["标准硬度块核查结果"],
    "surface_roughness": ["测试面粗糙度", "Ra="],
    "surface_condition": ["测试面状态"],
    "perpendicularity": ["垂直性确认", "压头轴线垂直"],
    "objective": ["物镜", "放大倍数"],
    "calibration_scale": ["标尺", "校准片编号", "量块编号"],
    "calibration_result": ["校准核查结果", "量块核查结果"],
    "measurement_points": ["测量点位"],
    "repeat_count": ["重复测量次数"],
    "source_type": ["发光源"],
    "lamp_no": ["氙灯编号", "氙灯批号"],
    "lamp_hours": ["氙灯累计使用时间"],
    "filter_no": ["滤光片编号", "滤光片批号"],
    "filter_hours": ["滤光片累计使用时间"],
    "water_temperature": ["水浴温度"],
    "sample_illuminance": ["试样表面照度"],
    "water_distance": ["试样与水面距离"],
    "water_medium": ["水浴介质"],
    "d65_illuminance": ["D65灯箱观察照度", "灯箱观察照度"],
    "background": ["观察背景板", "观察背景"],
    "observation_distance": ["观察距离"],
    "single_observation_time": ["单次观察时间"],
    "observer_1": ["观察者1姓名", "观察者1"],
    "observer_2": ["观察者2姓名", "观察者2"],
    "observer_3": ["观察者3姓名", "观察者3"],
}

ROW_ALIASES = {
    "sample_no": ["样品编号", "试样编号", "实验室样品编号"],
    "face": ["测试面", "面"],
    "position": ["测量位置", "摆放位置"],
    "ra1": ["Ra1"], "ra2": ["Ra2"], "ra3": ["Ra3"], "mean": ["平均值", "平均"],
    "limit": ["判定限值", "判定要求", "限值"], "conclusion": ["单样结论", "结论", "判定"],
    "width": ["宽度"], "dm1": ["金属厚度1"], "dm2": ["金属厚度2"], "dm3": ["金属厚度3"],
    "dm_mean": ["金属厚度平均"], "em": ["金属弹性模量"], "k": ["K/mm", "K值"],
    "ffail": ["裂纹萌生力", "破坏力"], "tau": ["结合强度"], "crack_position": ["裂纹位置", "裂纹形态"],
    "sample_name_tooth": ["样品名称/牙位", "牙位"], "image_valid": ["图像有效性"],
    "iqi_display": ["像质计显示"], "roi1": ["ROI-1", "ROI1"], "roi2": ["ROI-2", "ROI2"],
    "roi3": ["ROI-3", "ROI3"], "roi_mean": ["ROI平均"],
    "thickness_relation": ["像质计厚度点", "接近/介于"], "estimated_thickness": ["厚度估算"],
    "defect": ["异常影像", "缺陷"],
    "h1": ["H1"], "h2": ["H2"], "delta": ["ΔH", "翘曲变化量"], "edge_condition": ["切口崩边", "裂纹状态"],
    "l0": ["初始长度L0", "L0"], "t1": ["起始温度"], "t2": ["终止温度"],
    "delta_l": ["长度变化ΔL", "ΔL"], "delta_t": ["温差ΔT", "ΔT"], "alpha": ["线膨胀系数"],
    "crack": ["裂纹"], "chipping": ["崩瓷"], "fracture": ["破裂", "裂开"],
    "length": ["长度"], "height": ["高度", "厚度"], "span": ["支点距", "跨距"],
    "speed": ["速度"], "fmax": ["Fmax", "最大力"], "stress_02": ["0.2%规定非比例弯曲应力", "规定非比例弯曲应力"],
    "sample_state": ["试样状态", "样品状态"],
    "indent1": ["压痕1", "实测值1"], "indent2": ["压痕2", "实测值2"], "indent3": ["压痕3", "实测值3"],
    "indent_quality": ["压痕有效性"],
    "fixed1": ["固定端1"], "fixed2": ["固定端2"], "middle1": ["中点1"], "middle2": ["中点2"],
    "free1": ["自由端1"], "free2": ["自由端2"],
    "control_no": ["对照试样编号"], "shape": ["试样形状"], "size": ["试样尺寸"],
    "cover_method": ["遮盖方式"], "cover_direction": ["遮盖区域", "遮盖方向"], "cover_secure": ["遮盖是否牢固"],
    "observer1": ["观察者1结果"], "observer2": ["观察者2结果"], "observer3": ["观察者3结果"],
    "overall": ["总体观察结果"], "measurement_item": ["测量项目"], "raw_value": ["原始测量值"],
    "unit": ["单位"], "calculated_value": ["计算结果"], "note": ["备注"],
}

POSITIVE_OPTIONS = [
    "委托检测", "完好", "正常", "符合", "合格", "是", "无", "清晰", "已确认", "已完成",
    "允许曝光", "清洁", "干燥", "无明显干扰", "已清洁", "平整", "无油污", "无氧化皮",
    "无影响压痕缺陷", "平稳", "测试面与压头轴线垂直", "有效", "牢固", "持续供给",
    "可用于本次试验", "未见明显差异", "产品标准", "通过", "不适用", "平行纹理", "否",
]


def form_definition(kind: str) -> dict[str, Any]:
    return schema(kind)


def initialize_business_record(
    kind: str,
    sample_ids: list[str],
    detection_location: str,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior = prior or {}
    params = initial_parameters(kind, prior.get("parameters") or {}, detection_location)
    legacy_temperature = params.get("temperature")
    legacy_humidity = params.get("humidity")
    if legacy_temperature not in (None, ""):
        params.setdefault("temperature_before", legacy_temperature)
        params.setdefault("temperature_after", legacy_temperature)
    if legacy_humidity not in (None, ""):
        params.setdefault("humidity_before", legacy_humidity)
        params.setdefault("humidity_after", legacy_humidity)
    for section in schema(kind)["sections"]:
        for field in section["fields"]:
            key = field["key"]
            if field.get("type") == "select" and params.get(key) in (None, ""):
                params[key] = SELECT_DEFAULTS.get(key) or (field.get("options") or [""])[0]
    rows = prior.get("rows") or initial_rows(kind, sample_ids)
    rows = calculate_rows(kind, rows)
    checks = PRECHECKS.get(kind, PRECHECKS["generic"])
    return {
        "task_confirmations": prior.get("task_confirmations") or {
            "sample_received": True,
            "number_match": True,
            "sample_condition": True,
        },
        "prechecks": prior.get("prechecks") or list(checks),
        "all_prechecks": list(checks),
        "precheck_note": prior.get("precheck_note", ""),
        "fixed_parameter_mode": prior.get("fixed_parameter_mode", "按默认参数执行"),
        "parameters": params,
        "rows": rows,
        "equipment_checks": prior.get("equipment_checks") or [],
        "overall_status": prior.get("overall_status", "正常完成"),
        "deviation": prior.get("deviation", ""),
        "retest": prior.get("retest", "否"),
        "report_summary": prior.get("report_summary", ""),
        "report_conclusion": prior.get("report_conclusion", ""),
    }


def fixed_and_manual_fields(kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixed: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    for section in schema(kind)["sections"]:
        for field in section["fields"]:
            if field["key"] in HIDDEN_PARAMETER_KEYS or field.get("readonly"):
                continue
            if field["key"] in ALWAYS_EDIT_PARAMETER_KEYS:
                manual.append(field)
            elif field.get("actual"):
                manual.append(field)
            elif field.get("default") not in (None, ""):
                fixed.append(field)
            else:
                manual.append(field)
    return fixed, manual


def visible_row_fields(kind: str) -> list[tuple[str, str, str]]:
    return [
        item for item in schema(kind)["columns"]
        if item[0] != "sample_no" and item[0] not in AUTO_ROW_KEYS
    ]


def calculate_business_record(kind: str, record: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(record)
    params = output.get("parameters") or {}
    if kind == "thickness":
        for row in output.get("rows") or []:
            row["_design_thickness"] = params.get("design_thickness")
    output["rows"] = calculate_rows(kind, output.get("rows") or [])
    summary, conclusion = result_summary(kind, output["rows"])
    output["report_summary"] = summary
    output["report_conclusion"] = conclusion
    return output


def validate_business_record(kind: str, record: dict[str, Any], required_equipment: list[dict[str, Any]] | None = None) -> list[str]:
    issues: list[str] = []
    confirmations = record.get("task_confirmations") or {}
    if not all(confirmations.get(k) for k in ("sample_received", "number_match", "sample_condition")):
        issues.append("任务与样品确认尚未全部完成")

    expected = set(record.get("all_prechecks") or PRECHECKS.get(kind, []))
    actual = set(record.get("prechecks") or [])
    if expected - actual and not str(record.get("precheck_note", "")).strip():
        issues.append("存在未通过的实验前检查项，但未填写说明")

    params = record.get("parameters") or {}
    if not str(params.get("start_time") or "").strip():
        issues.append("尚未通过时间轴记录实验开始时间")
    if not str(params.get("end_time") or "").strip():
        issues.append("尚未通过时间轴记录实验结束时间")
    for field in fixed_and_manual_fields(kind)[1]:
        key = field["key"]
        if key in OPTIONAL_PARAMETER_KEYS:
            continue
        value = params.get(key)
        if value in (None, ""):
            issues.append(f"未填写：{field['label']}")

    equipment_checks = record.get("equipment_checks") or []
    required_map = {x.get("management_no") or x.get("管理编号"): bool(x.get("required") or x.get("必需设备") == "是") for x in (required_equipment or [])}
    for item in equipment_checks:
        no = item.get("management_no") or item.get("管理编号")
        status = item.get("status") or item.get("使用前状态")
        note = item.get("note") or item.get("异常说明")
        if required_map.get(no) and status != "正常" and not str(note or "").strip():
            issues.append(f"必需设备 {no} 状态异常但未填写说明")

    rows = record.get("rows") or []
    for index, row in enumerate(rows, 1):
        sid = row.get("sample_no") or f"第{index}条"
        for key, label, typ in visible_row_fields(kind):
            if typ == "calc" or key in OPTIONAL_ROW_KEYS or key == "note":
                continue
            value = row.get(key)
            if value in (None, ""):
                issues.append(f"{sid} 未填写：{label}")

    if record.get("overall_status") == "存在异常" and not str(record.get("deviation", "")).strip():
        issues.append("选择了存在异常，但未填写异常、偏离及处理说明")
    if not str(record.get("report_summary", "")).strip():
        issues.append("检验报告用结果摘要尚未形成")
    return issues


def _checkbox_options(text: str) -> list[str]:
    return [re.sub(r"[_＿…]+.*$", "", x).strip(" ：:；;，,") for x in re.split(r"[□☐☑]", text)[1:] if x.strip()]


def _select_checkbox_value(original: str, preferred: Any) -> str:
    if "□" not in original and "☐" not in original:
        return original
    options = _checkbox_options(original)
    selected: list[str] = []
    if isinstance(preferred, (list, tuple, set)):
        preferred_values = [str(x) for x in preferred]
    else:
        preferred_values = [str(preferred or "")]
    for option in options:
        if any(v and (v in option or option in v) for v in preferred_values):
            selected.append(option)
    if not selected:
        for positive in POSITIVE_OPTIONS:
            match = next((x for x in options if positive in x), None)
            if match:
                selected.append(match)
                # Cells containing several independent positive confirmations should select all.
                if any(term in original for term in ("平整", "清洁", "无油污", "警示标识", "无明显粉尘", "已完成打印")):
                    selected.extend([x for x in options if any(p in x for p in POSITIVE_OPTIONS) and x not in selected])
                break
    if not selected and options:
        selected = [options[0]]
    result = original.replace("☑", "□")
    for option in selected:
        result = re.sub(r"□\s*" + re.escape(option), lambda m: "☑" + m.group(0)[1:], result, count=1)
    return result


def _field_match(combined: str, aliases: list[str]) -> bool:
    normalized = _norm(combined)
    return any(_norm(alias) and (_norm(alias) in normalized or normalized in _norm(alias)) for alias in aliases)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return (f"{value:.6f}").rstrip("0").rstrip(".")
    if isinstance(value, list):
        return "、".join(str(x) for x in value)
    return str(value if value is not None else "")


def _attachment_reference(attachments: list[dict[str, Any]], sample_no: str = "") -> str:
    ids = [x.get("attachment_id", "") for x in attachments if not sample_no or x.get("sample_no") in ("", sample_no)]
    ids = [x for x in ids if x]
    return "、".join(ids) if ids else "详见内部实验数据追溯Excel"


def _build_equipment_for_prefill(equipment: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_map = {x.get("management_no") or x.get("管理编号"): x for x in checks}
    result = []
    for item in equipment:
        value = dict(item)
        no = value.get("management_no") or value.get("管理编号")
        check = status_map.get(no, {})
        value["usage_status"] = check.get("status") or check.get("使用前状态") or "正常"
        value["usage_note"] = check.get("note") or check.get("异常说明") or ""
        result.append(value)
    return result


def _parameter_for_field(field: dict[str, Any], params: dict[str, Any]) -> tuple[str | None, Any]:
    combined = " ".join([field.get("label", ""), field.get("row_label", ""), field.get("col_header", ""), field.get("template_text", "")])
    for key, aliases in PARAM_ALIASES.items():
        if key in params and _field_match(combined, aliases):
            return key, params.get(key)
    return None, None


def _row_key_for_field(kind: str, field: dict[str, Any]) -> str | None:
    section = _norm(field.get("section", ""))
    combined = " ".join([field.get("label", ""), field.get("row_label", ""), field.get("col_header", ""), field.get("template_text", "")])
    if not any(token in section for token in ("数据", "结果", "测量", "观察", "原始", "记录")):
        return None
    allowed = {x[0] for x in schema(kind)["columns"]}
    for key, aliases in ROW_ALIASES.items():
        if key in allowed and _field_match(combined, aliases):
            return key
    return None


def business_to_template_fields(
    template_name: str,
    kind: str,
    context: dict[str, Any],
    equipment: list[dict[str, Any]],
    business_record: dict[str, Any],
    attachments: list[dict[str, Any]] | None = None,
    prior_template_fields: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Map the concise experiment form into the original controlled Word template.

    The source template is not changed. Only values in its existing cells are replaced.
    Fields that are already known from earlier workflow stages are filled automatically.
    Non-applicable layout fields receive a controlled default rather than being shown to the
    experimenter as a template-cell input.
    """
    attachments = attachments or []
    business_record = calculate_business_record(kind, business_record)
    params = business_record.get("parameters") or {}
    rows = business_record.get("rows") or []
    checks = business_record.get("equipment_checks") or []
    equipment_prefill = _build_equipment_for_prefill(equipment, checks)
    context = dict(context)
    context["method_code"] = context.get("method_code") or context.get("standard", "")
    values = prefill_template_fields(template_name, context, equipment_prefill, prior_template_fields or {})
    manifest = template_manifest(template_name)

    # Determine row occurrence indexes for each table/column/key combination.
    occurrence: dict[tuple[int, int, str], int] = {}
    for field in manifest:
        key = field["key"]
        original = str(field.get("template_text", "") or "")
        combined = " ".join([field.get("label", ""), field.get("row_label", ""), field.get("col_header", ""), original])
        normalized = _norm(combined)

        # Workflow-known checkbox choices are hidden from the experimenter and filled here.
        if ("□" in original or "☐" in original) and any(token in normalized for token in ("样品规格", "型号规格")):
            model = str(context.get("model", ""))
            selected = _select_checkbox_value(original, model)
            if "☑" not in selected and "其他" in original:
                selected = original.replace("□其他", "☑其他", 1)
            selected = re.sub(r"(_{2,}|＿{2,}|…{2,})", model or "不适用", selected)
            values[key] = selected
            continue
        if ("□" in original or "☐" in original) and any(token in normalized for token in ("材料工艺", "材料名称")):
            material = str(context.get("material", ""))
            selected = _select_checkbox_value(original, material)
            if "☑" not in selected and "其他" in original:
                selected = original.replace("□其他", "☑其他", 1)
            selected = re.sub(r"(_{2,}|＿{2,}|…{2,})", material or "不适用", selected)
            values[key] = selected
            continue
        if ("□" in original or "☐" in original) and any(token in normalized for token in ("检测方法", "检测依据", "判定依据")):
            preferred = context.get("method_code") or context.get("standard") or "产品标准"
            values[key] = _select_checkbox_value(original, preferred)
            continue

        # Combined environment cells.
        if "环境条件" in normalized and "℃" in original and ("rh" in normalized or "%RH" in original or "%rh" in original.lower()):
            values[key] = f"{_format_value(params.get('temperature', ''))} ℃ {_format_value(params.get('humidity', ''))} %RH"
            continue

        param_key, param_value = _parameter_for_field(field, params)
        if param_key is not None and param_value not in (None, ""):
            if "□" in original or "☐" in original:
                values[key] = _select_checkbox_value(original, param_value)
            else:
                values[key] = _compose_cell_text(original, _format_value(param_value))
            continue

        row_key = _row_key_for_field(kind, field)
        if row_key:
            occ_key = (field["table"], field["col"], row_key)
            index = occurrence.get(occ_key, 0)
            occurrence[occ_key] = index + 1
            if index < len(rows):
                row = rows[index]
                raw = row.get(row_key, "")
                if row_key in AUTO_ROW_KEYS:
                    raw = _attachment_reference(attachments, row.get("sample_no", ""))
                if "□" in original or "☐" in original:
                    values[key] = _select_checkbox_value(original, raw)
                else:
                    values[key] = _compose_cell_text(original, _format_value(raw))
            else:
                values[key] = original
            continue

        # Common workflow confirmations and automatic attachment references.
        if "异常" in normalized or "偏离" in normalized:
            raw = business_record.get("deviation") or "无"
            values[key] = _compose_cell_text(original, raw) if not ("□" in original or "☐" in original) else _select_checkbox_value(original, "无")
            continue
        if any(token in normalized for token in ("数据文件", "图像编号", "照片编号", "曲线文件", "附件归档", "数据归档", "保存路径", "文件路径")):
            values[key] = _compose_cell_text(original, _attachment_reference(attachments))
            continue
        if "复测" in normalized or "重制" in normalized:
            values[key] = _select_checkbox_value(original, business_record.get("retest", "否")) if ("□" in original or "☐" in original) else _compose_cell_text(original, business_record.get("retest", "否"))
            continue
        if "确认人" in normalized or "检测人员" in normalized or "记录人" in normalized or "操作人" in normalized:
            values[key] = _compose_cell_text(original, context.get("operator", ""))
            continue
        if "核验人员" in normalized or "复核人员" in normalized:
            values[key] = _compose_cell_text(original, context.get("reviewer", ""))
            continue

        # Logical defaults are only applied to real confirmation items.
        # Pure layout blanks and unused alternatives stay exactly as in the source template.
        if "□" in original or "☐" in original:
            auto_tokens = ("检验类别", "接收状态", "是否符合", "使用前状态", "确认结果", "判定", "结果", "状态", "允许曝光", "授权操作", "Z轴正方向标识")
            if any(token in combined for token in auto_tokens):
                values[key] = _select_checkbox_value(original, "")
            continue

    from controlled_template_mappings import apply_controlled_mapping

    values = apply_controlled_mapping(
        template_name,
        kind,
        values,
        context,
        business_record,
        _attachment_reference(attachments),
    )
    return {k: str(v if v is not None else "") for k, v in values.items()}


def business_completion_summary(kind: str, record: dict[str, Any], required_equipment: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issues = validate_business_record(kind, record, required_equipment)
    sections = {
        "任务与样品确认": all((record.get("task_confirmations") or {}).values()),
        "设备与实验前确认": not any("设备" in x or "实验前" in x for x in issues),
        "环境与实验参数": not any("未填写" in x and any(term in x for term in ("温度", "湿度", "时间", "参数")) for x in issues),
        "原始测量数据": not any("未填写" in x and "未填写：" in x for x in issues),
        "异常与结果摘要": not any(term in "；".join(issues) for term in ("异常", "结果摘要")),
    }
    return {"issues": issues, "sections": sections, "complete": not issues}
