# -*- coding: utf-8 -*-
from __future__ import annotations

COMPANY_CN = "大连标普检测有限公司"
COMPANY_EN = "DALIAN BIAOPU TESTING CO., LTD."
SYSTEM_CN = "大连标普实验室样品全过程追溯系统"
SYSTEM_EN = "BPLab Sample Lifecycle Tracking System"
APP_VERSION = "BPLab Trace V5.0.1 完整落地版"
TIMEZONE_NAME = "Asia/Shanghai"

STORAGE_AREAS = ["A区域", "B区域"]
SAMPLE_CONDITIONS = ["完好", "不完好"]
RETURN_CONDITIONS = ["完好", "部分消耗", "已破坏", "全部消耗"]
DETECTION_LOCATIONS = ["力学实验室", "物理性能实验室", "显微室", "视觉检测室", "制样室", "其他"]
ATTACHMENT_TYPES = ["电脑截图", "实验过程照片", "仪器曲线", "X射线图像", "原始数据文件", "校准证书", "其他"]

# 与当前受控《检验委托单》保持一致。页面不再录入保密要求，生成委托单时固定为“无要求”。
METHOD_OPTIONS = [
    "YY/T 1936", "YY 0300", "YY 0621.1", "YY 0621.2", "YY/T 1702",
    "GB 17168", "GB/T 4340.1", "GB/T 3851", "GB/T 18876.1",
    "YY/T 1937", "YY 0270.1", "T/GDMDMA 0003", "YY 0710", "其他方法",
]

ROLES = ["管理员", "样品管理员", "实验人员", "复核实验员", "批准人"]

EXPERIMENTS = {
    "表面粗糙度试验": {
        "category": "增材制造检测", "std": "YY/T 1702-2020；GB/T 10610-2009",
        "method": "YY/T 1702", "kind": "rough", "template": None, "sop": "SOP_ROUGHNESS.docx",
    },
    "金属-陶瓷结合三点弯曲试验": {
        "category": "力学性能检测", "std": "YY 0621.1-2016",
        "method": "YY 0621.1", "kind": "mc", "template": "RECORD_MC_THREE_POINT.docx", "sop": "SOP_MC_THREE_POINT.docx",
    },
    "金属-陶瓷结合裂纹萌生试验": {
        "category": "力学性能检测", "std": "YY 0621.1-2016 / ISO 9693-1",
        "method": "YY 0621.1", "kind": "mc_crack", "template": "RECORD_MC_CRACK_INITIATION.docx", "sop": "SOP_MC_CRACK_INITIATION.docx",
    },
    "金属内部质量X射线灰度分析": {
        "category": "内部质量检测", "std": "实验室SOP/委托技术要求",
        "method": "其他方法", "kind": "xray", "template": "RECORD_XRAY_INTERNAL_QUALITY.docx", "sop": "SOP_XRAY_INTERNAL_QUALITY.docx",
    },
    "翘曲变形试验": {
        "category": "增材制造检测", "std": "YY/T 1702-2020 第7.3.2条",
        "method": "YY/T 1702", "kind": "warp", "template": "RECORD_WARPAGE.docx", "sop": "SOP_WARPAGE.docx",
    },
    "热膨胀系数试验": {
        "category": "物理性能检测", "std": "热膨胀系数测试SOP/设备说明书",
        "method": "其他方法", "kind": "cte", "template": "RECORD_CTE.docx", "sop": None,
    },
    "陶瓷牙耐急冷急热试验": {
        "category": "陶瓷材料检测", "std": "YY 0300-2009 第7.10条",
        "method": "YY 0300", "kind": "shock", "template": "RECORD_THERMAL_SHOCK.docx", "sop": "SOP_THERMAL_SHOCK.docx",
    },
    "弯曲性能试验": {
        "category": "力学性能检测", "std": "YY/T 1702-2020",
        "method": "YY/T 1702", "kind": "bend", "template": "RECORD_BENDING.docx", "sop": "SOP_BENDING.docx",
    },
    "维氏硬度试验": {
        "category": "力学性能检测", "std": "GB/T 4340.1-2009",
        "method": "GB/T 4340.1", "kind": "hv", "template": "RECORD_VICKERS_HARDNESS.docx", "sop": None,
    },
    "增材制造金属试样厚度测量": {
        "category": "增材制造检测", "std": "YY/T 1702-2020",
        "method": "YY/T 1702", "kind": "thickness", "template": "RECORD_THICKNESS.docx", "sop": "SOP_THICKNESS.docx",
    },
    "牙科材料色稳定性试验": {
        "category": "物理性能检测", "std": "YY/T 0631-2008 / 产品技术要求",
        "method": "其他方法", "kind": "color", "template": "RECORD_COLOR_STABILITY.docx", "sop": "SOP_COLOR_STABILITY.docx",
    },
}

ROLE_MENUS = {
    "管理员": [
        "首页看板", "单位信息库", "样品资料库", "新建委托与入库", "委托与样品管理",
        "任务包分配", "我的任务包", "实验记录", "原始记录复核", "样品归还", "回库确认",
        "附件与内部追溯", "单据中心", "报告中心", "修改追踪", "SOP与模板版本",
        "实验设备预设", "电子签名", "用户与权限", "审计追踪",
    ],
    "样品管理员": [
        "首页看板", "单位信息库", "样品资料库", "新建委托与入库", "委托与样品管理",
        "任务包分配", "回库确认", "附件与内部追溯", "单据中心",
    ],
    "实验人员": [
        "首页看板", "我的任务包", "实验记录", "样品归还", "附件与内部追溯",
        "单据中心", "报告中心", "修改追踪",
    ],
    "复核实验员": [
        "首页看板", "原始记录复核", "附件与内部追溯", "单据中心", "报告中心", "修改追踪",
    ],
    "批准人": ["首页看板", "报告中心", "单据中心"],
}
