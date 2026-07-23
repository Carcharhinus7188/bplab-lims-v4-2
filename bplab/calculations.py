from __future__ import annotations

import json
import math
from collections import Counter
from statistics import mean
from typing import Any


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _values(sample: dict[str, Any], keys: list[str]) -> list[float]:
    result = [_number(sample.get(key)) for key in keys]
    return [v for v in result if v is not None]


def _round(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _range(values: list[float], unit: str) -> str:
    if not values:
        return "无有效结果"
    if len(values) == 1:
        return f"{values[0]:.3f} {unit}"
    return f"{min(values):.3f}～{max(values):.3f} {unit}"


def _final_from_samples(results: list[dict[str, Any]]) -> str:
    valid = [r for r in results if r.get("judgment") not in {"无效", "需复测", ""}]
    if not valid:
        return "无法判定"
    return "不符合" if any(r.get("judgment") == "不符合" for r in valid) else "符合"


def calculate_roughness(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    limit = _number(data.get("parameters", {}).get("limit")) or 15.0
    rows = []
    averages = []
    for sample in data.get("samples", []):
        values = _values(sample, ["ra1", "ra2", "ra3"])
        avg = mean(values) if len(values) == 3 else None
        judgment = "符合" if avg is not None and avg <= limit else ("不符合" if avg is not None else "无法判定")
        rows.append({**sample, "average_ra": _round(avg), "judgment": judgment})
        if avg is not None:
            averages.append(avg)
    run = data.get("run", {})
    check_values = _values(run, ["standard_block_m1", "standard_block_m2", "standard_block_m3"])
    check_avg = mean(check_values) if check_values else None
    nominal = _number(run.get("standard_block_nominal"))
    deviation = ((check_avg - nominal) / nominal * 100) if check_avg is not None and nominal else None
    final = _final_from_samples(rows)
    report = "；".join(
        f"{row.get('sample_id', '样品')}：Ra平均值{row['average_ra']:.3f} μm"
        for row in rows
        if row.get("average_ra") is not None
    )
    if averages:
        report += f"。结果范围{_range(averages, 'μm')}，最大值{max(averages):.3f} μm。"
    return {
        "samples": rows,
        "summary": {
            "minimum": _round(min(averages) if averages else None),
            "maximum": _round(max(averages) if averages else None),
            "standard_check_average": _round(check_avg),
            "standard_check_relative_deviation_pct": _round(deviation),
        },
        "judgment": final,
        "standard_requirement": f"每个试样3次测量的Ra平均值≤{limit:g} μm。",
        "report_result": report or "未形成有效Ra结果。",
    }


def calculate_crack(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    limit = _number(data.get("parameters", {}).get("limit")) or 25.0
    rows = []
    passes = 0
    valid_count = 0
    values = []
    for sample in data.get("samples", []):
        thicknesses = _values(sample, ["metal_t1", "metal_t2", "metal_t3"])
        dm = mean(thicknesses) if len(thicknesses) == 3 else None
        k = _number(sample.get("k_factor"))
        force = _number(sample.get("failure_force"))
        tau = k * force if k is not None and force is not None else None
        is_valid = sample.get("failure_mode") == "典型裂纹萌生/剥离" and tau is not None
        judgment = "无效"
        if is_valid:
            valid_count += 1
            values.append(tau)
            judgment = "符合" if tau > limit else "不符合"
            passes += int(judgment == "符合")
        rows.append({**sample, "metal_thickness_average": _round(dm), "tau_b": _round(tau), "judgment": judgment})
    if valid_count < 6:
        final = "需补足6个有效试样"
    elif passes >= 4:
        final = "符合"
    elif passes <= 2:
        final = "不符合"
    else:
        final = "需复试"
    report = "；".join(
        f"{row.get('sample_id', '样品')}：Ffail={float(row['failure_force']):.3f} N，K={float(row['k_factor']):.5g}，τb={row['tau_b']:.3f} MPa（{row['judgment']}）"
        for row in rows
        if row.get("tau_b") is not None
    )
    return {
        "samples": rows,
        "summary": {"valid_count": valid_count, "pass_count": passes, "range": _range(values, "MPa")},
        "judgment": final,
        "standard_requirement": f"τb=K×Ffail，通常τb>{limit:g} MPa；6个有效试样按4/3/2规则判定。",
        "report_result": report or "未形成有效裂纹萌生强度结果。",
    }


def _parse_reference_grays(value: Any) -> list[tuple[float, float]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    result = []
    if isinstance(value, dict):
        for thickness, measures in value.items():
            try:
                t = float(thickness)
            except (TypeError, ValueError):
                continue
            vals = []
            if isinstance(measures, list):
                vals = [_number(v) for v in measures]
            else:
                vals = [_number(measures)]
            clean = [v for v in vals if v is not None]
            if clean:
                result.append((t, mean(clean)))
    return sorted(result)


def _estimate_thickness(gray: float, reference: list[tuple[float, float]]) -> tuple[str, bool]:
    if not reference:
        return "无像质计灰度数据", True
    by_gray = sorted((g, t) for t, g in reference)
    if gray < by_gray[0][0] or gray > by_gray[-1][0]:
        return "超出0.1～1.0 mm比对范围", True
    for (g1, t1), (g2, t2) in zip(by_gray, by_gray[1:]):
        if min(g1, g2) <= gray <= max(g1, g2):
            if abs(gray - g1) < 1e-9:
                return f"约{t1:.1f} mm", False
            if abs(gray - g2) < 1e-9:
                return f"约{t2:.1f} mm", False
            return f"{min(t1, t2):.1f}～{max(t1, t2):.1f} mm", False
    nearest = min(reference, key=lambda item: abs(item[1] - gray))
    return f"约{nearest[0]:.1f} mm", False


def calculate_xray(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    reference = _parse_reference_grays(data.get("run", {}).get("reference_grays"))
    rows = []
    for sample in data.get("samples", []):
        roi_averages = []
        for idx in (1, 2, 3):
            vals = _values(sample, [f"roi{idx}_m1", f"roi{idx}_m2", f"roi{idx}_m3"])
            roi_averages.append(mean(vals) if len(vals) == 3 else None)
        valid_gray = [v for v in roi_averages if v is not None]
        overall_gray = mean(valid_gray) if valid_gray else None
        estimate, out_of_range = _estimate_thickness(overall_gray, reference) if overall_gray is not None else ("无法估算", True)
        defects = [
            sample.get("abnormal_shadow"),
            sample.get("linear_indication"),
            sample.get("local_missing"),
            sample.get("bright_spot"),
        ]
        abnormal = any(value == "可见" for value in defects)
        image_valid = sample.get("image_valid") == "有效"
        judgment = "需复检" if not image_valid else ("不符合" if abnormal else ("超出方法范围" if out_of_range else "符合"))
        rows.append(
            {
                **sample,
                "roi1_average": _round(roi_averages[0]),
                "roi2_average": _round(roi_averages[1]),
                "roi3_average": _round(roi_averages[2]),
                "overall_gray": _round(overall_gray),
                "thickness_estimate": estimate,
                "out_of_range": out_of_range,
                "judgment": judgment,
            }
        )
    final = "不符合" if any(r["judgment"] == "不符合" for r in rows) else (
        "需复检" if any(r["judgment"] in {"需复检", "超出方法范围"} for r in rows) else "符合"
    )
    report = "；".join(
        f"{r.get('sample_id', '样品')}：图像{r.get('image_valid', '')}，厚度估算{r['thickness_estimate']}，内部质量{r['judgment']}"
        for r in rows
    )
    return {
        "samples": rows,
        "summary": {"reference_points": len(reference)},
        "judgment": final,
        "standard_requirement": config["basis"],
        "report_result": report or "未形成有效X射线灰度分析结果。",
    }


def calculate_warpage(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    limit = _number(data.get("parameters", {}).get("limit_abs"))
    rows, values = [], []
    for sample in data.get("samples", []):
        h1, h2 = _number(sample.get("h1")), _number(sample.get("h2"))
        delta = h1 - h2 if h1 is not None and h2 is not None else None
        if delta is None:
            judgment = "无法判定"
        elif limit is None:
            judgment = "仅记录"
        else:
            judgment = "符合" if abs(delta) <= limit else "不符合"
        rows.append({**sample, "delta_h": _round(delta), "judgment": judgment})
        if delta is not None:
            values.append(delta)
    final = "不符合" if any(r["judgment"] == "不符合" for r in rows) else (
        "仅记录" if limit is None else _final_from_samples(rows)
    )
    report = "；".join(
        f"{r.get('sample_id', '样品')}：H1={float(r['h1']):.3f} mm，H2={float(r['h2']):.3f} mm，ΔH={r['delta_h']:.3f} mm"
        for r in rows
        if r.get("delta_h") is not None
    )
    return {
        "samples": rows,
        "summary": {"minimum": _round(min(values) if values else None), "maximum": _round(max(values) if values else None)},
        "judgment": final,
        "standard_requirement": f"|ΔH|≤{limit:g} mm。" if limit is not None else "委托未提供限值，仅提供ΔH实测结果。",
        "report_result": report or "未形成有效翘曲变形结果。",
    }


def calculate_thermal_expansion(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    p = data.get("parameters", {})
    lower, upper = _number(p.get("limit_min")), _number(p.get("limit_max"))
    rows, alphas, displacements = [], [], []
    for sample in data.get("samples", []):
        l0 = _number(sample.get("l0"))
        start = _number(sample.get("start_temp"))
        end = _number(sample.get("end_temp"))
        delta_um = _number(sample.get("delta_l_um"))
        delta_t = end - start if start is not None and end is not None else None
        alpha = delta_um * 1000 / (l0 * delta_t) if l0 and delta_t and delta_um is not None else None
        if alpha is None:
            judgment = "无法判定"
        elif lower is None and upper is None:
            judgment = "仅记录"
        else:
            judgment = "符合" if (lower is None or alpha >= lower) and (upper is None or alpha <= upper) else "不符合"
        rows.append({**sample, "delta_t": _round(delta_t), "alpha": _round(alpha), "judgment": judgment})
        if alpha is not None:
            alphas.append(alpha)
        if delta_um is not None:
            displacements.append(delta_um)
    final = "不符合" if any(r["judgment"] == "不符合" for r in rows) else (
        "仅记录" if lower is None and upper is None else _final_from_samples(rows)
    )
    report = "；".join(
        f"{r.get('sample_id', '样品')}：{float(r['start_temp']):.1f}～{float(r['end_temp']):.1f} ℃，α={r['alpha']:.3f}×10⁻⁶/K"
        for r in rows
        if r.get("alpha") is not None
    )
    requirement = "仅提供实测热膨胀系数。"
    if lower is not None or upper is not None:
        requirement = f"α范围：{lower if lower is not None else '-∞'}～{upper if upper is not None else '+∞'}×10⁻⁶/K。"
    return {
        "samples": rows,
        "summary": {
            "average_alpha": _round(mean(alphas) if alphas else None),
            "maximum_displacement_um": _round(max(displacements) if displacements else None),
        },
        "judgment": final,
        "standard_requirement": requirement,
        "report_result": report or "未形成有效热膨胀系数结果。",
    }


def calculate_thermal_shock(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    rows = []
    crack = chipping = fracture = other = 0
    for sample in data.get("samples", []):
        has_crack = sample.get("crack") == "有"
        has_chipping = sample.get("chipping") == "有"
        has_fracture = sample.get("fracture") == "有"
        initial = sample.get("initial_abnormal") == "有"
        judgment = "不符合" if has_crack or has_chipping or has_fracture else "符合"
        rows.append({**sample, "judgment": judgment})
        crack += int(has_crack)
        chipping += int(has_chipping)
        fracture += int(has_fracture)
        other += int(initial)
    final = _final_from_samples(rows)
    abnormal_ids = [r.get("sample_id", "") for r in rows if r["judgment"] == "不符合"]
    report = (
        f"共检验{len(rows)}个样品，裂纹{crack}个、崩瓷{chipping}个、破裂/裂开{fracture}个。"
        + (f"异常样品：{'、'.join(abnormal_ids)}。" if abnormal_ids else "所有样品未见裂纹、崩瓷或破裂。")
    )
    return {
        "samples": rows,
        "summary": {"total": len(rows), "valid": len(rows), "crack": crack, "chipping": chipping, "fracture": fracture, "other": other},
        "judgment": final,
        "standard_requirement": config["basis"],
        "report_result": report,
    }


def calculate_bending(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    limit = _number(data.get("parameters", {}).get("stress_limit")) or 800.0
    rows, stresses = [], []
    for sample in data.get("samples", []):
        stress = _number(sample.get("offset_stress"))
        valid = sample.get("valid") == "有效"
        judgment = "无效" if not valid else ("符合" if stress is not None and stress >= limit else ("不符合" if stress is not None else "无法判定"))
        rows.append({**sample, "judgment": judgment})
        if stress is not None and valid:
            stresses.append(stress)
    final = _final_from_samples(rows)
    report = "；".join(
        f"{r.get('sample_id', '样品')}：Fmax={float(r['fmax']):.3f} N，0.2%规定非比例弯曲应力={float(r['offset_stress']):.3f} MPa"
        for r in rows
        if _number(r.get("fmax")) is not None and _number(r.get("offset_stress")) is not None
    )
    return {
        "samples": rows,
        "summary": {"minimum_stress": _round(min(stresses) if stresses else None), "maximum_stress": _round(max(stresses) if stresses else None)},
        "judgment": final,
        "standard_requirement": f"0.2%规定非比例弯曲应力≥{limit:g} MPa。",
        "report_result": report or "未形成有效弯曲性能结果。",
    }


def calculate_vickers(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    p = data.get("parameters", {})
    lower, upper = _number(p.get("limit_min")), _number(p.get("limit_max"))
    rows, overall_values = [], []
    for sample in data.get("samples", []):
        face1 = _values(sample, ["face1_hv1", "face1_hv2", "face1_hv3"])
        face2 = _values(sample, ["face2_hv1", "face2_hv2", "face2_hv3"])
        avg1 = mean(face1) if len(face1) == 3 else None
        avg2 = mean(face2) if len(face2) == 3 else None
        overall = mean([avg1, avg2]) if avg1 is not None and avg2 is not None else None
        if overall is None:
            judgment = "无法判定"
        elif lower is None and upper is None:
            judgment = "仅记录"
        else:
            judgment = "符合" if (lower is None or overall >= lower) and (upper is None or overall <= upper) else "不符合"
        rows.append({**sample, "face1_average": _round(avg1), "face2_average": _round(avg2), "overall_hv10": _round(overall), "judgment": judgment})
        if overall is not None:
            overall_values.append(overall)
    final = "不符合" if any(r["judgment"] == "不符合" for r in rows) else (
        "仅记录" if lower is None and upper is None else _final_from_samples(rows)
    )
    report = "；".join(
        f"{r.get('sample_id', '样品')}：面1 {r['face1_average']:.1f} HV10，面2 {r['face2_average']:.1f} HV10，总体 {r['overall_hv10']:.1f} HV10"
        for r in rows
        if r.get("overall_hv10") is not None
    )
    requirement = "未提供HV10限值，仅提供实测结果。" if lower is None and upper is None else f"HV10范围：{lower or '-∞'}～{upper or '+∞'}。"
    return {
        "samples": rows,
        "summary": {"minimum": _round(min(overall_values) if overall_values else None), "maximum": _round(max(overall_values) if overall_values else None)},
        "judgment": final,
        "standard_requirement": requirement,
        "report_result": report or "未形成有效维氏硬度结果。",
    }


def calculate_thickness(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    p = data.get("parameters", {})
    design = _number(p.get("design_thickness")) or 1.0
    tolerance = _number(p.get("tolerance")) or 0.05
    rows, averages = [], []
    for sample in data.get("samples", []):
        section_means = []
        result = {**sample}
        for section in ("fixed", "middle", "free"):
            vals = _values(sample, [f"{section}_1", f"{section}_2", f"{section}_3"])
            avg = mean(vals) if len(vals) == 3 else None
            result[f"{section}_average"] = _round(avg)
            if avg is not None:
                section_means.append(avg)
        all_values = _values(
            sample,
            [f"{section}_{idx}" for section in ("fixed", "middle", "free") for idx in (1, 2, 3)],
        )
        overall = mean(all_values) if len(all_values) == 9 else None
        deviation = overall - design if overall is not None else None
        judgment = "符合" if deviation is not None and abs(deviation) <= tolerance else ("不符合" if deviation is not None else "无法判定")
        result.update({"overall_average": _round(overall), "deviation": _round(deviation), "judgment": judgment})
        rows.append(result)
        if overall is not None:
            averages.append(overall)
    final = _final_from_samples(rows)
    gauge_nominal = _number(data.get("run", {}).get("gauge_nominal"))
    gauge_measured = _number(data.get("run", {}).get("gauge_measured"))
    gauge_error = gauge_measured - gauge_nominal if gauge_nominal is not None and gauge_measured is not None else None
    report = "；".join(
        f"{r.get('sample_id', '样品')}：总平均厚度{r['overall_average']:.3f} mm，偏差{r['deviation']:+.3f} mm（{r['judgment']}）"
        for r in rows
        if r.get("overall_average") is not None
    )
    return {
        "samples": rows,
        "summary": {
            "minimum": _round(min(averages) if averages else None),
            "maximum": _round(max(averages) if averages else None),
            "gauge_error": _round(gauge_error),
            "gauge_check": "符合" if gauge_error is not None and abs(gauge_error) <= 0.002 else "不符合",
        },
        "judgment": final,
        "standard_requirement": f"设计厚度{design:.3f} mm，厚度偏差≤±{tolerance:.3f} mm。",
        "report_result": report or "未形成有效厚度测量结果。",
    }


def calculate_color(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    rows = []
    severity = {"未见明显差异": 0, "轻微差异": 1, "明显差异": 2, "无法判定": 3}
    for sample in data.get("samples", []):
        observations = [sample.get(f"observer{i}_result") for i in (1, 2, 3)]
        valid = [v for v in observations if v]
        counts = Counter(valid)
        if not counts:
            majority = "无法判定"
        else:
            top = counts.most_common()
            max_count = top[0][1]
            tied = [value for value, count in top if count == max_count]
            majority = max(tied, key=lambda value: severity.get(value, 99))
        judgment = "符合" if majority == "未见明显差异" else ("无法判定" if majority == "无法判定" else "不符合")
        rows.append({**sample, "majority_result": majority, "judgment": judgment})
    final = "不符合" if any(r["judgment"] == "不符合" for r in rows) else (
        "无法判定" if any(r["judgment"] == "无法判定" for r in rows) else "符合"
    )
    report = "；".join(
        f"{r.get('sample_id', '样品')}：3名观察者多数判定为“{r['majority_result']}”（{r['judgment']}）"
        for r in rows
    )
    return {
        "samples": rows,
        "summary": {"total": len(rows), "pass_count": sum(r["judgment"] == "符合" for r in rows)},
        "judgment": final,
        "standard_requirement": config["basis"],
        "report_result": report or "未形成有效色稳定性观察结果。",
    }


CALCULATORS = {
    "roughness": calculate_roughness,
    "crack_initiation": calculate_crack,
    "xray": calculate_xray,
    "warpage": calculate_warpage,
    "thermal_expansion": calculate_thermal_expansion,
    "thermal_shock": calculate_thermal_shock,
    "bending": calculate_bending,
    "vickers": calculate_vickers,
    "thickness": calculate_thickness,
    "color_stability": calculate_color,
}


def calculate(code: str, data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    calculator = CALCULATORS.get(code)
    if not calculator:
        return {"samples": data.get("samples", []), "summary": {}, "judgment": "仅记录", "standard_requirement": config.get("basis", ""), "report_result": ""}
    return calculator(data, config)


def validate_record(data: dict[str, Any], config: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    prechecks = data.get("prechecks", {})
    for item in config.get("prechecks", []):
        if item.get("default") and prechecks.get(item["key"]) is not True:
            missing.append(f"实验前确认：{item['label']}")
    if not all(value is not None and value != "" for value in data.get("environment", {}).values()):
        missing.append("环境条件未完整填写")
    for item in config.get("run_fields", []):
        if item.get("required") and data.get("run", {}).get(item["key"]) in (None, "", []):
            missing.append(f"过程数据：{item['label']}")
    samples = data.get("samples", [])
    if not samples:
        missing.append("没有样品原始数据")
    for idx, sample in enumerate(samples, start=1):
        for item in config.get("sample_fields", []):
            if item.get("required") and sample.get(item["key"]) in (None, "", []):
                missing.append(f"样品{idx}：{item['label']}")
    if data.get("has_exception") and not str(data.get("exception_note", "")).strip():
        missing.append("已选择存在异常，但未填写异常说明")
    if data.get("parameter_deviation") and not str(data.get("deviation_note", "")).strip():
        missing.append("已选择参数偏离，但未填写偏离说明")
    return missing

