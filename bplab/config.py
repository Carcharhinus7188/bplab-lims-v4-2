from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
ATTACHMENT_DIR = ROOT / "attachments"
RECORD_TEMPLATE_DIR = ROOT / "templates" / "records"
REPORT_TEMPLATE_DIR = ROOT / "templates" / "report"

COMPANY_CN = "大连标普检测有限公司"
COMPANY_EN = "DALIAN BIAOPU TESTING CO., LTD."
SYSTEM_NAME = "BPLab Trace"
VERSION = "V5.7"

LOCATIONS = ["化学室", "无损检测室", "性能检测室", "显微检测室", "制样室", "外观检测室", "样品室"]

ROLE_LABELS = {
    "admin": "管理员",
    "sample_manager": "样品管理员",
    "tester": "实验员",
    "reviewer": "复核员",
    "approver": "批准人",
}


def field(
    key: str,
    label: str,
    kind: str = "number",
    *,
    unit: str = "",
    default: Any = None,
    required: bool = True,
    options: list[str] | None = None,
    help_text: str = "",
    source: str = "operator",
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    advanced: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": kind,
        "unit": unit,
        "default": default,
        "required": required,
        "options": options or [],
        "help": help_text,
        "source": source,
        "min": minimum,
        "max": maximum,
        "step": step,
        "advanced": advanced,
    }


COMMON_ENV = [
    field("temperature_before", "检测前温度", unit="℃", default=20.0, minimum=-20, maximum=60, step=0.1),
    field("temperature_after", "检测后温度", unit="℃", default=20.0, minimum=-20, maximum=60, step=0.1),
    field("humidity_before", "检测前相对湿度", unit="%RH", default=50.0, minimum=0, maximum=100, step=0.1),
    field("humidity_after", "检测后相对湿度", unit="%RH", default=50.0, minimum=0, maximum=100, step=0.1),
]

COMMON_PRECHECKS = [
    {"key": "sample_received", "label": "样品已收到且数量一致", "default": True},
    {"key": "sample_id_match", "label": "样品编号与任务一致", "default": True},
    {"key": "sample_condition_ok", "label": "样品状态满足检测要求", "default": True},
    {"key": "equipment_ok", "label": "设备、器具使用前状态正常", "default": True},
    {"key": "environment_ok", "label": "环境条件满足要求", "default": True},
    {"key": "method_followed", "label": "按现行受控方法和参数执行", "default": True},
]


EXPERIMENTS: dict[str, dict[str, Any]] = {
    "roughness": {
        "name": "表面粗糙度试验",
        "method": "YY/T 1702—2020",
        "basis": "每个试样3次测量的Ra平均值≤15 μm；6个试样均符合时批次符合。",
        "location": "性能检测室",
        "sop_file": "SOP_roughness.docx",
        "record_template": "R001_roughness.pages",
        "template_status": "blocked_pages",
        "template_note": "受控记录母版为Pages格式，Streamlit Cloud无法无损回填。需补充同版DOCX后启用正式导出。",
        "sample_slots": 6,
        "calculation": "roughness",
        "report_rule": "逐样输出Ra平均值、结果范围、最大值、标准要求和单项结论。",
        "environment": deepcopy(COMMON_ENV),
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "bench_clean", "label": "工作台清洁且无明显振动、强气流", "default": True},
            {"key": "stylus_ok", "label": "测针清洁、无损伤", "default": True},
        ],
        "parameters": [
            field("calculation_standard", "计算标准", "text", default="ISO-97", source="config"),
            field("filter", "滤波器", "text", default="Gaussian", source="config"),
            field("sampling_length", "取样长度 λc", unit="mm", default=0.8, source="config"),
            field("evaluation_length", "评定长度", unit="mm", default=4.0, source="config"),
            field("travel_speed", "测针移动速度", unit="mm/s", default=0.5, source="config"),
            field("measurement_lines", "有效测量线数量", "integer", default=3, source="config"),
            field("limit", "Ra平均值限值", unit="μm", default=15.0, source="config"),
        ],
        "run_fields": [
            field("level_x", "工作台X轴水平度", unit="mm/m", default=0.0, maximum=0.02),
            field("level_y", "工作台Y轴水平度", unit="mm/m", default=0.0, maximum=0.02),
            field("standard_block_id", "粗糙度标准块编号", "text"),
            field("standard_block_nominal", "标准块标称Ra", unit="μm", default=10.0),
            field("standard_block_m1", "核查值1", unit="μm"),
            field("standard_block_m2", "核查值2", unit="μm"),
            field("standard_block_m3", "核查值3", unit="μm"),
            field("measurement_direction", "测量方向", "select", default="按SOP规定方向", options=["按SOP规定方向", "平行纹理", "垂直纹理", "其他"]),
        ],
        "sample_fields": [
            field("ra1", "测量线1 Ra", unit="μm"),
            field("ra2", "测量线2 Ra", unit="μm"),
            field("ra3", "测量线3 Ra", unit="μm"),
            field("surface_ok", "原打印面/方向确认", "select", default="符合", options=["符合", "不符合"]),
            field("line_position", "测量线位说明", "text", default="3条平行、不重叠的代表性测量线", required=False),
        ],
    },
    "crack_initiation": {
        "name": "金属—陶瓷结合裂纹萌生试验",
        "method": "YY 0621.1—2016",
        "basis": "τb=K×Ffail；通常τb>25 MPa。6个有效试样中≥4个符合则合格，≤2个不合格，3个需复试。",
        "location": "性能检测室",
        "sop_file": "SOP_crack_initiation.docx",
        "record_template": "",
        "template_status": "missing",
        "template_note": "资料包未包含裂纹萌生项目对应受控原始记录DOCX，正式原始记录导出被受控阻断。",
        "sample_slots": 6,
        "calculation": "crack_initiation",
        "report_rule": "逐样输出Ffail、K、τb、破坏模式、有效试样数与批次结论。",
        "environment": deepcopy(COMMON_ENV),
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "fixture_parallel", "label": "三点弯曲夹具跨距和平行性确认合格", "default": True},
            {"key": "ceramic_opposite_load", "label": "陶瓷面位于加载面的反面", "default": True},
        ],
        "parameters": [
            field("span", "下支撑跨距", unit="mm", default=20.0, source="config"),
            field("loading_rate", "加载速率", unit="mm/min", default=1.5, source="config"),
            field("edge_radius", "压头/支撑刃口半径", unit="mm", default=1.0, source="config"),
            field("limit", "τb判定限值", unit="MPa", default=25.0, source="config"),
        ],
        "run_fields": [
            field("elastic_modulus", "金属材料杨氏模量 EM", unit="GPa"),
            field("em_source", "EM来源文件", "text"),
            field("fixture_id", "夹具编号", "text"),
            field("span_actual", "跨距实测值", unit="mm", default=20.0),
            field("parallel_block_id", "平行块编号", "text"),
            field("software_file", "原始曲线/数据文件编号", "text"),
        ],
        "sample_fields": [
            field("length", "试样长度", unit="mm", default=25.0),
            field("width", "试样宽度", unit="mm", default=3.0),
            field("metal_t1", "金属基体厚度1", unit="mm"),
            field("metal_t2", "金属基体厚度2", unit="mm"),
            field("metal_t3", "金属基体厚度3", unit="mm"),
            field("ceramic_total_thickness", "陶瓷总厚度", unit="mm", default=1.1),
            field("k_factor", "K系数", default=None, help_text="按YY 0621.1图2或经验证软件取得"),
            field("failure_force", "裂纹萌生/剥离力 Ffail", unit="N"),
            field("failure_mode", "破坏模式", "select", default="典型裂纹萌生/剥离", options=["典型裂纹萌生/剥离", "非典型破坏", "滑移", "数据采集失败"]),
        ],
    },
    "xray": {
        "name": "金属内部质量X射线数字成像灰度分析",
        "method": "实验室SOP / 委托技术要求",
        "basis": "通过0.1～1.0 mm孔形像质计灰度比对估算厚度，并评价内部异常影像；超出范围时不得强行给出准确厚度。",
        "location": "无损检测室",
        "sop_file": "SOP_xray.docx",
        "record_template": "R005_xray.docx",
        "template_status": "controlled",
        "sample_slots": 10,
        "calculation": "xray",
        "report_rule": "逐样输出图像有效性、厚度估算区间、异常类型与内部质量判定。",
        "environment": [
            field("temperature_before", "检测温度", unit="℃", default=23.0, minimum=18, maximum=28, step=0.1),
            field("humidity_before", "相对湿度", unit="%RH", default=50.0, minimum=30, maximum=75, step=0.1),
        ],
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "radiation_safety", "label": "辐射警示、联锁、急停和防护设施正常", "default": True},
            {"key": "detector_clean", "label": "采集板与像质计清洁、标识清晰", "default": True},
        ],
        "parameters": [
            field("voltage", "管电压", unit="kV", default=75.0, source="config"),
            field("current", "管电流", unit="mA", default=56.0, source="config"),
            field("exposure_ms", "曝光时间", unit="ms", default=110.0, source="config"),
            field("mas", "管电流时间积", unit="mAs", default=6.3, source="config"),
            field("focus_mode", "焦点模式", "text", default="L", source="config"),
            field("body_mode", "体型模式", "text", default="瘦", source="config"),
        ],
        "run_fields": [
            field("density_strip_id", "标准密度片编号", "text"),
            field("density_nominal", "标准密度片标称值", default=2.0),
            field("density_m1", "密度核查值1"),
            field("density_m2", "密度核查值2"),
            field("density_m3", "密度核查值3"),
            field("density_tolerance", "密度核查允许偏差", default=0.05),
            field("reference_grays", "像质计0.1～1.0 mm灰度值", "json", help_text="按0.1 mm步进录入每个厚度点的3次灰度值"),
        ],
        "sample_fields": [
            field("image_id", "图像文件编号", "text"),
            field("roi1_m1", "ROI-1灰度值1"),
            field("roi1_m2", "ROI-1灰度值2"),
            field("roi1_m3", "ROI-1灰度值3"),
            field("roi2_m1", "ROI-2灰度值1"),
            field("roi2_m2", "ROI-2灰度值2"),
            field("roi2_m3", "ROI-2灰度值3"),
            field("roi3_m1", "ROI-3灰度值1"),
            field("roi3_m2", "ROI-3灰度值2"),
            field("roi3_m3", "ROI-3灰度值3"),
            field("image_valid", "图像有效性", "select", default="有效", options=["有效", "无效"]),
            field("abnormal_shadow", "异常暗影", "select", default="未见", options=["未见", "可见"]),
            field("linear_indication", "线状/裂纹状影像", "select", default="未见", options=["未见", "可见"]),
            field("local_missing", "局部缺失/断续/明显变薄", "select", default="未见", options=["未见", "可见"]),
            field("bright_spot", "异常亮斑/高密度点", "select", default="未见", options=["未见", "可见"]),
            field("abnormal_detail", "异常位置、尺寸和数量", "textarea", required=False),
        ],
    },
    "warpage": {
        "name": "翘曲变形试验",
        "method": "YY/T 1702—2020 7.3.2",
        "basis": "ΔH=H1-H2；按委托、产品标准或注册技术要求的限值判定；未提供限值时仅报告实测值。",
        "location": "显微检测室",
        "sop_file": "",
        "record_template": "R006_warpage.docx",
        "template_status": "controlled",
        "sample_slots": 10,
        "calculation": "warpage",
        "report_rule": "逐样输出H1、H2、ΔH和单样判定，汇总结果范围与最终结论。",
        "environment": deepcopy(COMMON_ENV),
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "image_clear", "label": "图像清晰、边缘锐利且无重影", "default": True},
            {"key": "point_to_line", "label": "使用Point to Line点到线功能", "default": True},
            {"key": "cut_quality", "label": "切口无崩边、裂纹等影响测量缺陷", "default": True},
        ],
        "parameters": [
            field("cut_position", "切割位置", "text", default="悬臂梁中部", source="config"),
            field("cut_travel", "切割行程", default=50.0, source="config"),
            field("feed_rate", "进给速度", default=0.1, source="config"),
            field("limit_abs", "绝对翘曲量限值", unit="mm", default=None, required=False, source="config"),
        ],
        "run_fields": [
            field("cutting_disc", "切割片规格/批号", "text"),
            field("coolant_status", "冷却液状态", "select", default="正常", options=["正常", "异常"]),
            field("data_path", "图像/测量数据归档编号", "text"),
        ],
        "sample_fields": [
            field("image_before", "切割前图像编号", "text"),
            field("h1", "切割前H1", unit="mm"),
            field("cut_start", "切割开始时间", "time"),
            field("cut_end", "切割结束时间", "time"),
            field("recut", "是否重新制样", "select", default="否", options=["否", "是"]),
            field("image_after", "切割后图像编号", "text"),
            field("h2", "切割后H2", unit="mm"),
        ],
    },
    "thermal_expansion": {
        "name": "热膨胀系数试验",
        "method": "热膨胀系数测试实验操作规程 / 委托技术要求",
        "basis": "α=ΔL/(L0×ΔT)，按委托限值判定；无明确限值时仅提供实测值。",
        "location": "性能检测室",
        "sop_file": "",
        "record_template": "R007_thermal_expansion.docx",
        "template_status": "controlled",
        "sample_slots": 6,
        "calculation": "thermal_expansion",
        "report_rule": "逐样输出温度区间、L0、ΔL、α，汇总平均系数和最大膨胀量。",
        "environment": deepcopy(COMMON_ENV),
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "high_temp_safety", "label": "高温警示、隔热和断电措施有效", "default": True},
            {"key": "pv_stable", "label": "启动前PV值稳定在50～60", "default": True},
        ],
        "parameters": [
            field("terminal_temperature", "终止温度", unit="℃", default=550.0, source="config"),
            field("limit_min", "α下限", unit="×10⁻⁶/K", required=False, source="config"),
            field("limit_max", "α上限", unit="×10⁻⁶/K", required=False, source="config"),
        ],
        "run_fields": [
            field("software_version", "测试系统软件版本", "text"),
            field("pv_value", "启动前PV值", default=55.0, minimum=50, maximum=60),
            field("temperature_series", "代表性温度—位移数据", "json", help_text="记录起始、50、100…550℃对应位移；完整曲线进入附件追溯"),
            field("data_path", "原始数据/曲线归档编号", "text"),
        ],
        "sample_fields": [
            field("l0", "试样长度L0", unit="mm"),
            field("width_diameter", "宽度/直径", unit="mm"),
            field("thickness", "厚度", unit="mm"),
            field("initial_pv", "初始PV值", default=55.0),
            field("start_temp", "起始温度", unit="℃", default=25.0),
            field("end_temp", "终止温度", unit="℃", default=550.0),
            field("delta_l_um", "总位移ΔL", unit="μm"),
            field("curve_file", "曲线文件编号", "text"),
            field("valid", "数据有效性", "select", default="有效", options=["有效", "无效"]),
        ],
    },
    "thermal_shock": {
        "name": "陶瓷牙耐急冷急热性能试验",
        "method": "YY 0300—2009 7.10",
        "basis": "全部样品经规定急冷急热处理后无裂纹、崩瓷、破裂或结构破坏时判定合格。",
        "location": "性能检测室",
        "sop_file": "SOP_thermal_shock.docx",
        "record_template": "R009_thermal_shock.docx",
        "template_status": "controlled",
        "sample_slots": 28,
        "calculation": "thermal_shock",
        "report_rule": "输出样品总数、有效样品数、各缺陷数量、异常样品编号和最终结论。",
        "environment": [
            field("temperature_before", "试验前环境温度", unit="℃", default=23.0, minimum=21, maximum=25, step=0.1),
            field("temperature_after", "检查前环境温度", unit="℃", default=23.0, minimum=21, maximum=25, step=0.1),
            field("humidity_before", "试验前相对湿度", unit="%RH", default=50.0, maximum=70, step=0.1),
            field("humidity_after", "检查前相对湿度", unit="%RH", default=50.0, maximum=70, step=0.1),
            field("illumination", "检查照度", unit="lx", default=1000.0, minimum=1000),
        ],
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "initial_surface_ok", "label": "初始外观无影响判定的裂纹或崩瓷", "default": True},
            {"key": "magnifier_ok", "label": "10×放大镜清洁、状态正常", "default": True},
        ],
        "parameters": [
            field("oven_temp", "烘箱温度", unit="℃", default=100.0, source="config"),
            field("first_heat_min", "首次加热", unit="min", default=20.0, source="config"),
            field("transfer_sec", "最大转移时间", unit="s", default=3.0, source="config"),
            field("ice_temp", "冰水目标温度", unit="℃", default=1.0, source="config"),
            field("ice_min", "冰水浸泡", unit="min", default=5.0, source="config"),
            field("second_heat_min", "再次加热", unit="min", default=15.0, source="config"),
        ],
        "run_fields": [
            field("oven_stable_temp", "烘箱稳定读数", unit="℃", default=100.0),
            field("first_heat_actual", "首次加热实测时长", unit="min", default=20.0),
            field("ice_readings", "冰水温度监测", "json", help_text="试验前、每批样品前及每15min录入温度"),
            field("transfer_actual", "实际转移时间", unit="s", default=3.0, maximum=3.0),
            field("ice_actual", "冰水浸泡实测时长", unit="min", default=5.0),
            field("second_heat_actual", "再次加热实测时长", unit="min", default=15.0),
            field("cool_surface_temp", "冷却后表面温度", unit="℃", default=23.0, minimum=21, maximum=25),
        ],
        "sample_fields": [
            field("initial_abnormal", "初始外观异常", "select", default="无", options=["无", "有"]),
            field("crack", "裂纹", "select", default="无", options=["无", "有"]),
            field("chipping", "崩瓷", "select", default="无", options=["无", "有"]),
            field("fracture", "破裂/裂开", "select", default="无", options=["无", "有"]),
            field("defect_detail", "缺陷位置/尺寸/照片编号", "textarea", required=False),
        ],
    },
    "bending": {
        "name": "弯曲性能试验",
        "method": "YY/T 1702—2020",
        "basis": "0.2%规定非比例弯曲应力应不低于800 MPa，或按委托/注册技术要求。",
        "location": "性能检测室",
        "sop_file": "SOP_bending.docx",
        "record_template": "R010_bending.docx",
        "template_status": "controlled",
        "sample_slots": 6,
        "calculation": "bending",
        "report_rule": "逐样输出尺寸、Fmax、0.2%规定非比例弯曲应力和结论，汇总范围与批次结论。",
        "environment": deepcopy(COMMON_ENV),
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "fixture_ok", "label": "三点弯曲夹具安装牢固、对中和平行", "default": True},
            {"key": "extensometer_ok", "label": "挠度计/位移测量状态正常", "default": True},
        ],
        "parameters": [
            field("span", "支点距离", unit="mm", default=20.0, source="config"),
            field("loading_rate", "加载速度", unit="mm/min", default=1.0, source="config"),
            field("offset_strain", "规定非比例应变", unit="%", default=0.2, source="config"),
            field("support_radius", "支撑/压头半径", unit="mm", default=2.0, source="config"),
            field("stress_limit", "0.2%规定非比例弯曲应力限值", unit="MPa", default=800.0, source="config"),
        ],
        "run_fields": [
            field("sensor_id", "2kN力传感器编号", "text"),
            field("sensor_check", "力传感器使用前核查值", unit="N"),
            field("fixture_id", "弯曲夹具编号", "text"),
            field("software_version", "FastTest软件版本", "text"),
            field("data_path", "原始曲线/数据归档编号", "text"),
        ],
        "sample_fields": [
            field("length", "试样长度", unit="mm", default=25.0),
            field("width", "试样宽度", unit="mm", default=2.0),
            field("height", "试样厚度/高度", unit="mm", default=2.0),
            field("span_actual", "支点距离实测值", unit="mm", default=20.0),
            field("speed_actual", "加载速度实测值", unit="mm/min", default=1.0),
            field("fmax", "最大力Fmax", unit="N"),
            field("offset_stress", "0.2%规定非比例弯曲应力", unit="MPa"),
            field("data_file", "曲线/数据文件编号", "text"),
            field("valid", "试样有效性", "select", default="有效", options=["有效", "无效"]),
        ],
    },
    "vickers": {
        "name": "维氏硬度试验",
        "method": "GB/T 4340.1",
        "basis": "按委托、产品标准或注册技术要求的HV10限值判定；未给出限值时仅提供实测结果。",
        "location": "显微检测室",
        "sop_file": "SOP_vickers.pages",
        "record_template": "R011_vickers.docx",
        "template_status": "controlled",
        "sample_slots": 6,
        "calculation": "vickers",
        "report_rule": "逐样输出两个检测面的HV10平均值、总体结果和判定依据。",
        "environment": deepcopy(COMMON_ENV),
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "indenter_ok", "label": "压头、物镜和载台状态正常", "default": True},
            {"key": "surface_ok", "label": "两个检测面平整、清洁且满足压痕识别要求", "default": True},
            {"key": "perpendicular_ok", "label": "Z轴方向和相邻面垂直关系已确认", "default": True},
        ],
        "parameters": [
            field("scale", "硬度标尺", "text", default="HV10", source="config"),
            field("force", "试验力", unit="N", default=98.07, source="config"),
            field("hold_time", "保荷时间", unit="s", default=15.0, source="config"),
            field("faces", "检测面数量", "integer", default=2, source="config"),
            field("indents_per_face", "每面压痕数", "integer", default=3, source="config"),
            field("limit_min", "HV10下限", required=False, source="config"),
            field("limit_max", "HV10上限", required=False, source="config"),
        ],
        "run_fields": [
            field("standard_block_id", "标准维氏硬度块编号", "text"),
            field("standard_block_nominal", "标准块标称值", unit="HV10", default=466.0),
            field("block_m1", "标准块核查值1", unit="HV10"),
            field("block_m2", "标准块核查值2", unit="HV10"),
            field("block_m3", "标准块核查值3", unit="HV10"),
            field("surface_confirm_method", "测试面确认方式", "multiselect", default=["目视/显微镜确认"], options=["目视/显微镜确认", "粗糙度仪实测", "制样工艺确认", "其他"]),
            field("surface_ra", "测试面Ra（如实测）", unit="μm", required=False),
            field("data_path", "硬度报告/压痕图像归档编号", "text"),
        ],
        "sample_fields": [
            field("face1_hv1", "面1压痕1 HV10"),
            field("face1_hv2", "面1压痕2 HV10"),
            field("face1_hv3", "面1压痕3 HV10"),
            field("face2_hv1", "面2压痕1 HV10"),
            field("face2_hv2", "面2压痕2 HV10"),
            field("face2_hv3", "面2压痕3 HV10"),
            field("face1_surface", "面1表面状态", "select", default="合格", options=["合格", "不合格"]),
            field("face2_surface", "面2表面状态", "select", default="合格", options=["合格", "不合格"]),
            field("report_id", "设备报告编号", "text"),
        ],
    },
    "thickness": {
        "name": "增材制造金属试样厚度测量",
        "method": "YY/T 1702—2020",
        "basis": "总平均厚度与设计厚度偏差应不大于±0.05 mm，或按委托/图纸要求。",
        "location": "显微检测室",
        "sop_file": "SOP_thickness.docx",
        "record_template": "",
        "template_status": "missing",
        "template_note": "资料包仅含SOP，未含对应受控原始记录Word母版，正式原始记录导出被受控阻断。",
        "sample_slots": 5,
        "calculation": "thickness",
        "report_rule": "逐样输出固定端、中点、自由端平均厚度、总平均、偏差和判定。",
        "environment": [
            field("temperature_before", "恒温环境温度", unit="℃", default=20.0, minimum=18, maximum=22, step=0.1),
            field("equilibration_minutes", "恒温平衡时间", unit="min", default=60.0, minimum=60),
            field("humidity_before", "相对湿度", unit="%RH", default=50.0, minimum=0, maximum=100),
        ],
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "warmup_ok", "label": "二次元影像测量仪已预热20 min", "default": True},
            {"key": "surface_untreated", "label": "测量位置未打磨、抛光或挤压", "default": True},
            {"key": "fixed_ok", "label": "试样固定稳定、成像边缘清晰", "default": True},
        ],
        "parameters": [
            field("design_thickness", "设计厚度", unit="mm", default=1.0, source="config"),
            field("objective", "物镜倍率", "text", default="33×", source="config"),
            field("tolerance", "允许偏差", unit="mm", default=0.05, source="config"),
        ],
        "run_fields": [
            field("gauge_block_id", "标准量块编号", "text"),
            field("gauge_nominal", "量块标称值", unit="mm", default=1.0),
            field("gauge_measured", "量块实测值", unit="mm"),
            field("software_version", "测量软件版本", "text"),
            field("fixing_method", "试样固定方式", "text", default="按SOP固定"),
        ],
        "sample_fields": [
            field("fixed_1", "固定端测点1", unit="mm"),
            field("fixed_2", "固定端测点2", unit="mm"),
            field("fixed_3", "固定端测点3", unit="mm"),
            field("middle_1", "中点测点1", unit="mm"),
            field("middle_2", "中点测点2", unit="mm"),
            field("middle_3", "中点测点3", unit="mm"),
            field("free_1", "自由端测点1", unit="mm"),
            field("free_2", "自由端测点2", unit="mm"),
            field("free_3", "自由端测点3", unit="mm"),
        ],
    },
    "color_stability": {
        "name": "牙科材料色稳定性试验",
        "method": "YY/T 0631—2008",
        "basis": "3名颜色视觉正常观察者独立比较，以多数结果判定；未见明显色泽差异时符合。",
        "location": "外观检测室",
        "sop_file": "SOP_color_stability.docx",
        "record_template": "R012_color_stability.docx",
        "template_status": "controlled",
        "sample_slots": 12,
        "calculation": "color_stability",
        "report_rule": "逐样输出三名观察者结果、多数判定和单样结论，汇总最终色稳定性结论。",
        "environment": [
            field("temperature_before", "实验室温度", unit="℃", default=23.0, step=0.1),
            field("humidity_before", "相对湿度", unit="%RH", default=50.0, step=0.1),
            field("observation_lux", "D65观察照度", unit="lx", default=1500.0, minimum=1000, maximum=2000),
        ],
        "prechecks": deepcopy(COMMON_PRECHECKS)
        + [
            {"key": "observer_vision", "label": "3名观察者颜色视觉资格均已确认", "default": True},
            {"key": "background_ok", "label": "N5中性灰/规定背景板清洁且符合要求", "default": True},
            {"key": "shield_ok", "label": "试样遮盖牢固且未污染试样", "default": True},
        ],
        "parameters": [
            field("bath_temp", "水浴目标温度", unit="℃", default=37.0, source="config"),
            field("surface_lux", "试样表面目标照度", unit="lx", default=150000.0, source="config"),
            field("water_distance", "试样与水面距离", unit="mm", default=10.0, source="config"),
            field("exposure_hours", "照射时间", unit="h", default=24.0, source="config"),
            field("observation_distance", "观察距离", unit="mm", default=250.0, source="config"),
            field("single_view_seconds", "单次观察时间", unit="s", default=2.0, source="config"),
        ],
        "run_fields": [
            field("observer1", "观察者1姓名", "text"),
            field("observer2", "观察者2姓名", "text"),
            field("observer3", "观察者3姓名", "text"),
            field("xenon_id", "氙灯编号/批号", "text"),
            field("xenon_hours", "氙灯累计使用时间", unit="h", default=0.0, maximum=1500),
            field("filter_id", "滤光片编号/批号", "text"),
            field("filter_hours", "滤光片累计使用时间", unit="h", default=0.0, maximum=1500),
            field("surface_lux1", "受光位置照度1", unit="lx", default=150000.0),
            field("surface_lux2", "受光位置照度2", unit="lx", default=150000.0),
            field("surface_lux3", "受光位置照度3", unit="lx", default=150000.0),
            field("bath_actual", "水浴实测温度", unit="℃", default=37.0),
            field("exposure_actual", "累计照射时间", unit="h", default=24.0),
            field("observation_date", "观察日期", "date"),
        ],
        "sample_fields": [
            field("shape", "试样形状", "select", default="圆片", options=["圆片", "牙形", "其他"]),
            field("size", "试样尺寸", "text"),
            field("shield_method", "遮盖方式", "select", default="试样夹", options=["试样夹", "锡箔", "铝箔"]),
            field("position", "摆放位置", "text"),
            field("observer1_result", "观察者1总体结果", "select", default="未见明显差异", options=["未见明显差异", "轻微差异", "明显差异", "无法判定"]),
            field("observer2_result", "观察者2总体结果", "select", default="未见明显差异", options=["未见明显差异", "轻微差异", "明显差异", "无法判定"]),
            field("observer3_result", "观察者3总体结果", "select", default="未见明显差异", options=["未见明显差异", "轻微差异", "明显差异", "无法判定"]),
            field("comparison_note", "照射区/未照射区及对照试样比较说明", "textarea", required=False),
        ],
    },
}


def get_experiment(code: str) -> dict[str, Any]:
    return deepcopy(EXPERIMENTS[code])


def active_experiment_options() -> dict[str, str]:
    return {cfg["name"]: code for code, cfg in EXPERIMENTS.items()}

