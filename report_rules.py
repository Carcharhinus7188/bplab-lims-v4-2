# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from experiment_engine import calculate_rows, result_summary


STANDARD_REQUIREMENTS = {
    "rough": "每个试样3条测量线Ra平均值均≤15 μm。",
    "mc_crack": "金属—陶瓷结合强度τb＞25 MPa。",
    "xray": "按受控方法完成灰度分析；图像有效，像质计显示清晰，无影响判定的异常影像。",
    "warp": "翘曲变化量应满足委托/产品技术要求（默认|ΔH|≤0.5 mm）。",
    "cte": "在规定温度区间内报告线膨胀系数，按委托/产品技术要求判定。",
    "shock": "全部样品经耐急冷急热试验后应无裂纹、崩瓷或破裂。",
    "bend": "0.2%规定非比例弯曲应力≥800 MPa，或按委托/技术要求。",
    "hv": "报告HV10实测结果，按委托/产品技术要求进行符合性判定。",
    "thickness": "各试样平均厚度相对设计厚度偏差应在±0.05 mm内。",
    "color": "规定条件照射24 h后，试样照射区与未照射区不得出现明显色泽差异。",
    "generic": "按委托/产品技术要求。",
}


def report_item(kind: str, rows: list[dict[str, Any]]) -> dict[str, str]:
    calculated = calculate_rows(kind, rows)
    summary, conclusion = result_summary(kind, calculated)
    if summary in ("", "详见原始记录", "见原始记录"):
        summary = "尚未形成有效检验结果"
    return {
        "requirement": STANDARD_REQUIREMENTS.get(kind, STANDARD_REQUIREMENTS["generic"]),
        "result": summary,
        "conclusion": conclusion,
    }


def overall_conclusion(items: list[dict[str, str]]) -> str:
    conclusions = [item.get("conclusion", "") for item in items]
    if any(value in ("不符合", "不合格") for value in conclusions):
        return "所检项目中存在不符合项，详见检验结果附表。"
    if conclusions and all(value in ("符合", "合格") for value in conclusions):
        return "所检项目均符合相应标准要求。"
    return "所检项目结果见检验结果附表，未作符合性判定的项目仅提供实测结果。"
