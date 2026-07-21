# -*- coding: utf-8 -*-
from __future__ import annotations

COMPANY_CN = "大连标普检测有限公司"
COMPANY_EN = "DALIAN BIAOPU TESTING CO., LTD."
SYSTEM_CN = "大连标普实验室样品全过程追溯系统"
SYSTEM_EN = "BPLab Sample Lifecycle Tracking System"
APP_VERSION = "BPLab Trace V4.5.1 入库默认预设版"
STORAGE_AREAS = ["A区域", "B区域"]
SAMPLE_CONDITIONS = ["完好", "不完好"]

ROLES = ["管理员", "收样员", "实验人员", "复核实验员", "样品管理员"]

EXPERIMENTS = {
    "表面粗糙度试验": {
        "category": "增材制造检测", "std": "YY/T 1702-2020；GB/T 10610-2009",
        "kind": "rough", "n": 6, "template": None,
        "sop": "SOP_ROUGHNESS.docx"
    },
    "金属-陶瓷结合三点弯曲试验": {
        "category": "力学性能检测", "std": "YY 0621.1-2016",
        "kind": "mc", "n": 6,
        "template": "RECORD_MC_CRACK_INITIATION.docx",
        "sop": "SOP_MC_THREE_POINT.docx"
    },
    "金属-陶瓷结合裂纹萌生试验": {
        "category": "力学性能检测", "std": "YY 0621.1-2016 / ISO 9693-1",
        "kind": "mc", "n": 6,
        "template": "RECORD_MC_THREE_POINT.docx",
        "sop": "SOP_MC_CRACK_INITIATION.docx"
    },
    "金属内部质量X射线灰度分析": {
        "category": "内部质量检测", "std": "实验室SOP/委托技术要求",
        "kind": "xray", "n": 6,
        "template": "RECORD_XRAY_INTERNAL_QUALITY.docx",
        "sop": "SOP_XRAY_INTERNAL_QUALITY.docx"
    },
    "翘曲变形试验": {
        "category": "增材制造检测", "std": "YY/T 1702-2020 第7.3.2条",
        "kind": "warp", "n": 10,
        "template": "RECORD_WARPAGE.docx",
        "sop": "SOP_WARPAGE.docx"
    },
    "热膨胀系数试验": {
        "category": "物理性能检测", "std": "热膨胀系数测试SOP/设备说明书",
        "kind": "cte", "n": 6,
        "template": "RECORD_CTE.docx",
        "sop": None
    },
    "陶瓷牙耐急冷急热试验": {
        "category": "陶瓷材料检测", "std": "YY 0300-2009 第7.10条",
        "kind": "shock", "n": 28,
        "template": "RECORD_THERMAL_SHOCK.docx",
        "sop": "SOP_THERMAL_SHOCK.docx"
    },
    "弯曲性能试验": {
        "category": "力学性能检测", "std": "YY/T 1702-2020",
        "kind": "bend", "n": 6,
        "template": "RECORD_BENDING.docx",
        "sop": "SOP_BENDING.docx"
    },
    "维氏硬度试验": {
        "category": "力学性能检测", "std": "GB/T 4340.1-2009",
        "kind": "hv", "n": 6,
        "template": "RECORD_VICKERS_HARDNESS.docx",
        "sop": None
    },
    "增材制造金属试样厚度测量": {
        "category": "增材制造检测", "std": "YY/T 1702-2020",
        "kind": "thickness", "n": 5,
        "template": "RECORD_THICKNESS.docx",
        "sop": "SOP_THICKNESS.docx"
    },
    "牙科材料色稳定性试验": {
        "category": "物理性能检测", "std": "YY/T 0631-2008 / 产品技术要求",
        "kind": "color", "n": 6,
        "template": "RECORD_COLOR_STABILITY.docx",
        "sop": "SOP_COLOR_STABILITY.docx"
    },
}

CHECK_ITEMS = {
    "rough": ["工作台水平度符合", "标准粗糙度样板核查合格", "取样长度0.8 mm", "评估长度4.0 mm", "速度0.5 mm/s", "原打印表面确认"],
    "mc": ["跨距20 mm确认", "压头/支点半径1.0 mm", "夹具平行性确认", "金属面朝上、陶瓷面朝下", "加载速度1.0～2.0 mm/min", "全部清零", "K系数经复核"],
    "xray": ["辐射安全确认", "采集板状态正常", "孔形像质计有效", "曝光参数确认", "样品方向确认", "原始图像保存"],
    "warp": ["二次元校准有效", "Point to Line功能可用", "切割前基准线确认", "冷却液持续供给", "切口无崩边裂纹", "切割后基准线确认"],
    "cte": ["终止温度550℃", "PV值稳定50～60", "试样安装牢固", "软件路径可追溯", "升温状态正常", "曲线和报告保存"],
    "shock": ["烘箱100±2℃", "首次加热20±1 min", "转移≤3 s", "冰水1±1℃", "浸泡5±1 min", "再次加热15±1 min", "冷却23±2℃", "光照≥1000 lx及10×放大镜"],
    "bend": ["2000 N传感器确认", "跨距20 mm", "速度1.0 mm/min", "规定应变0.2%", "挠度计轻微接触", "全部清零", "夹具平行居中"],
    "hv": ["标准硬度块核查合格", "HV10/98.07 N", "保荷15 s", "测试面平整清洁", "垂直性确认", "每面3个有效压痕"],
    "thickness": ["二次元校准有效", "放大倍率确认", "固定端/中点/自由端", "每点重复测量", "图像编号可追溯"],
    "color": ["仪器校准有效", "标准白板核查", "照明条件确认", "测量区域一致", "基线与试验后数据对应"],
}

ROLE_MENUS = {
    "管理员": ["首页看板", "样品入库", "基础资料", "样品全流程", "任务分配", "我的检测任务", "实验记录", "待复核", "样品回库", "原始记录表下载", "修改追踪", "已删除样品", "SOP与模板版本", "用户与权限"],
    "收样员": ["首页看板", "样品入库", "基础资料", "样品全流程", "任务分配", "原始记录表下载", "已删除样品"],
    "实验人员": ["首页看板", "样品全流程", "我的检测任务", "实验记录", "原始记录表下载", "修改追踪"],
    "复核实验员": ["首页看板", "样品全流程", "待复核", "原始记录表下载", "修改追踪"],
    "样品管理员": ["首页看板", "样品全流程", "样品回库", "原始记录表下载"],
}
