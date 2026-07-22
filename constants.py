# -*- coding: utf-8 -*-
from __future__ import annotations

COMPANY_CN = "大连标普检测有限公司"
COMPANY_EN = "DALIAN BIAOPU TESTING CO., LTD."
SYSTEM_CN = "大连标普实验室样品全过程追溯系统"
SYSTEM_EN = "BPLab Sample Lifecycle Tracking System"
APP_VERSION = "BPLab Trace V5.2 实验名称与方法版"
TIMEZONE_NAME = "Asia/Shanghai"

STORAGE_AREAS = ["A区域", "B区域"]
SAMPLE_CONDITIONS = ["完好", "不完好"]
RETURN_CONDITIONS = ["完好", "部分消耗", "已破坏", "全部消耗"]

DETECTION_LOCATIONS = [
    "化学室",
    "无损检测室",
    "性能检测室",
    "显微检测室",
    "制样室",
    "外观检测室",
    "样品室",
]

ATTACHMENT_TYPES = [
    "电脑截图", "实验过程照片", "仪器曲线", "X射线图像",
    "原始数据文件", "校准证书", "其他",
]

# 与当前受控《检验委托单》保持一致，仅使用已批准的方法选项。
METHOD_OPTIONS = [
    "YY/T 1936", "YY 0300", "YY 0621.1", "YY 0621.2", "YY/T 1702",
    "GB 17168", "GB/T 4340.1", "GB/T 3851", "GB/T 18876.1",
    "YY/T 1937", "YY 0270.1", "T/GDMDMA 0003", "YY 0710",
]

# 用户界面只显示“实验名称｜检测方法”。
# key仅用于数据库内部关联，不在界面、任务编号、原始记录或报告中显示。
EXPERIMENTS = {
    "表面粗糙度试验": {
        "key": "I001", "category": "增材制造检测",
        "std": "YY/T 1702-2020；GB/T 10610-2009",
        "method": "YY/T 1702", "kind": "rough",
        "template": None, "sop": "SOP_ROUGHNESS.docx",
    },
    "金属-陶瓷结合裂纹萌生试验": {
        "key": "I002", "category": "力学性能检测",
        "std": "YY 0621.1-2016 / ISO 9693-1",
        "method": "YY 0621.1", "kind": "mc_crack",
        "template": "RECORD_MC_CRACK_INITIATION.docx",
        "sop": "SOP_MC_CRACK_INITIATION.docx",
    },
    "金属内部质量X射线灰度分析": {
        "key": "I003", "category": "内部质量检测",
        "std": "GB 17168及实验室受控SOP",
        "method": "GB 17168", "kind": "xray",
        "template": "RECORD_XRAY_INTERNAL_QUALITY.docx",
        "sop": "SOP_XRAY_INTERNAL_QUALITY.docx",
    },
    "翘曲变形试验": {
        "key": "I004", "category": "增材制造检测",
        "std": "YY/T 1702-2020 第7.3.2条",
        "method": "YY/T 1702", "kind": "warp",
        "template": "RECORD_WARPAGE.docx", "sop": "SOP_WARPAGE.docx",
    },
    "热膨胀系数试验": {
        "key": "I005", "category": "物理性能检测",
        "std": "YY 0621.1及实验室受控SOP",
        "method": "YY 0621.1", "kind": "cte",
        "template": "RECORD_CTE.docx", "sop": None,
    },
    "陶瓷牙耐急冷急热试验": {
        "key": "I006", "category": "陶瓷材料检测",
        "std": "YY 0300-2009 第7.10条",
        "method": "YY 0300", "kind": "shock",
        "template": "RECORD_THERMAL_SHOCK.docx",
        "sop": "SOP_THERMAL_SHOCK.docx",
    },
    "弯曲性能试验": {
        "key": "I007", "category": "力学性能检测",
        "std": "YY/T 1702-2020",
        "method": "YY/T 1702", "kind": "bend",
        "template": "RECORD_BENDING.docx", "sop": "SOP_BENDING.docx",
    },
    "维氏硬度试验": {
        "key": "I008", "category": "力学性能检测",
        "std": "GB/T 4340.1-2009",
        "method": "GB/T 4340.1", "kind": "hv",
        "template": "RECORD_VICKERS_HARDNESS.docx", "sop": None,
    },
    "增材制造金属试样厚度测量": {
        "key": "I009", "category": "增材制造检测",
        "std": "YY/T 1702-2020",
        "method": "YY/T 1702", "kind": "thickness",
        "template": "RECORD_THICKNESS.docx", "sop": "SOP_THICKNESS.docx",
    },
    "牙科材料色稳定性试验": {
        "key": "I010", "category": "物理性能检测",
        "std": "YY 0710及产品技术要求",
        "method": "YY 0710", "kind": "color",
        "template": "RECORD_COLOR_STABILITY.docx",
        "sop": "SOP_COLOR_STABILITY.docx",
    },
}

def experiment_display(experiment_name: str) -> str:
    cfg = EXPERIMENTS.get(experiment_name, {})
    method = cfg.get("method", "")
    return f"{experiment_name}｜{method}" if method else experiment_name

ROLES = ["管理员", "样品管理员", "实验人员", "复核实验员", "批准人"]

ROLE_MENUS = {
    "管理员": [
        "首页看板", "单位信息库", "检测项目与方法库", "样品资料库",
        "新建委托与入库", "委托与样品管理", "任务包分配",
        "我的任务包", "实验记录", "原始记录复核", "样品归还",
        "回库确认", "附件与内部追溯", "单据中心", "报告中心",
        "修改追踪", "SOP与模板版本", "实验设备预设", "电子签名",
        "用户与权限", "审计追踪",
    ],
    "样品管理员": [
        "首页看板", "单位信息库", "样品资料库", "新建委托与入库",
        "委托与样品管理", "任务包分配", "回库确认",
        "附件与内部追溯", "单据中心",
    ],
    "实验人员": [
        "首页看板", "我的任务包", "实验记录", "样品归还",
        "附件与内部追溯", "单据中心", "报告中心", "修改追踪",
    ],
    "复核实验员": [
        "首页看板", "原始记录复核", "附件与内部追溯",
        "单据中心", "报告中心", "修改追踪",
    ],
    "批准人": ["首页看板", "报告中心", "单据中心"],
}
