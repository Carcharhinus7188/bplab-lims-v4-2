# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime
from typing import Any
import pandas as pd
from experiment_schemas import SCHEMAS


def schema(kind: str) -> dict[str, Any]:
    return SCHEMAS.get(kind) or SCHEMAS["generic"]


def initial_parameters(kind: str, preset: dict[str, Any] | None = None, detection_location: str = "") -> dict[str, Any]:
    values: dict[str, Any] = {}
    for section in schema(kind)["sections"]:
        for field in section["fields"]:
            key = field["key"]
            default = field.get("default", "")
            if key == "detection_location":
                default = detection_location
            values[key] = default
    if preset:
        for key, value in preset.items():
            if value not in (None, ""):
                values[key] = value
    return values


def initial_rows(kind: str, sample_ids: list[str]) -> list[dict[str, Any]]:
    ids = sample_ids or [""]
    columns = schema(kind)["columns"]
    rows: list[dict[str, Any]] = []
    if schema(kind).get("row_expansion") == "faces":
        for sid in ids:
            for face in ["面1", "面2"]:
                row = {key: _default_for_column(kind, key, ctype) for key, _, ctype in columns}
                row["sample_no"] = sid
                row["face"] = face
                rows.append(row)
    else:
        for sid in ids:
            row = {key: _default_for_column(kind, key, ctype) for key, _, ctype in columns}
            row["sample_no"] = sid
            rows.append(row)
    return calculate_rows(kind, rows)


def _default_for_column(kind: str, key: str, ctype: str) -> Any:
    if ctype == "number" or ctype == "calc":
        defaults = {
            ("rough", "limit"): 15.0,
            ("warp", "limit"): 0.5,
            ("bend", "length"): 25.0,
            ("bend", "width"): 2.0,
            ("bend", "height"): 2.0,
            ("bend", "span"): 20.0,
            ("bend", "speed"): 1.0,
            ("cte", "t1"): 25.0,
            ("cte", "t2"): 550.0,
        }
        return defaults.get((kind, key))
    if ctype.startswith("select:"):
        options = ctype.split(":", 1)[1].split("|")
        return options[0] if options else ""
    return ""


def columns_for_editor(kind: str) -> list[dict[str, str]]:
    return [{"key": key, "label": label, "type": ctype} for key, label, ctype in schema(kind)["columns"]]


def dataframe(kind: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    cols = [x[0] for x in schema(kind)["columns"]]
    return pd.DataFrame(rows)[cols]


def calculate_rows(kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        try:
            if kind == "mc_crack":
                vals = [_number_or_none(row.get("dm1")), _number_or_none(row.get("dm2")), _number_or_none(row.get("dm3"))]
                row["dm_mean"] = round(sum(vals) / 3, 4) if all(v is not None for v in vals) else None
                k_value, fail_value = _number_or_none(row.get("k")), _number_or_none(row.get("ffail"))
                row["tau"] = round(k_value * fail_value, 2) if k_value is not None and fail_value is not None else None
                row["conclusion"] = ("符合" if row["tau"] > 25 else "不符合") if row["tau"] is not None else ""
            elif kind == "rough":
                vals = [_number_or_none(row.get("ra1")), _number_or_none(row.get("ra2")), _number_or_none(row.get("ra3"))]
                row["mean"] = round(sum(vals) / 3, 3) if all(v is not None for v in vals) else None
                row["conclusion"] = ("符合" if row["mean"] <= _num(row.get("limit"), 15) else "不符合") if row["mean"] is not None else ""
            elif kind == "xray":
                roi_means = []
                for roi in range(1, 4):
                    values = [_number_or_none(row.get(f"roi{roi}_reading{reading}")) for reading in range(1, 4)]
                    # Keep compatibility with records saved before V5.7.
                    legacy = _number_or_none(row.get(f"roi{roi}"))
                    roi_mean = round(sum(values) / 3, 2) if all(value is not None for value in values) else legacy
                    row[f"roi{roi}"] = roi_mean
                    roi_means.append(roi_mean)
                row["roi_mean"] = round(sum(roi_means) / 3, 2) if all(value is not None for value in roi_means) else None
            elif kind == "warp":
                h1, h2 = _number_or_none(row.get("h1")), _number_or_none(row.get("h2"))
                row["delta"] = round(h1 - h2, 4) if h1 is not None and h2 is not None else None
                row["conclusion"] = ("合格" if abs(row["delta"]) <= _num(row.get("limit"), .5) else "不合格") if row["delta"] is not None else ""
            elif kind == "cte":
                t1, t2 = _number_or_none(row.get("t1")), _number_or_none(row.get("t2"))
                row["delta_t"] = round(t2 - t1, 3) if t1 is not None and t2 is not None else None
                l0, dt, delta_l = _number_or_none(row.get("l0")), _number_or_none(row.get("delta_t")), _number_or_none(row.get("delta_l"))
                row["alpha"] = round((delta_l / 1000.0) / (l0 * dt) * 1_000_000, 3) if l0 and dt and delta_l is not None else None
            elif kind == "shock":
                row["conclusion"] = "符合" if all(str(row.get(k, "无")) == "无" for k in ("crack", "chipping", "fracture")) else "不符合"
            elif kind == "bend":
                row["conclusion"] = "符合" if _num(row.get("stress_02")) >= 800 else "不符合"
            elif kind == "hv":
                vals = [_number_or_none(row.get("indent1")), _number_or_none(row.get("indent2")), _number_or_none(row.get("indent3"))]
                row["mean"] = round(sum(vals) / 3, 1) if all(v is not None for v in vals) else None
            elif kind == "thickness":
                groups = {}
                for section in ("fixed", "middle", "free"):
                    keys = [f"r{repeat}_{section}_p{point}" for repeat in range(1, 4) for point in range(1, 4)]
                    vals = [_number_or_none(row.get(key)) for key in keys]
                    groups[section] = vals
                    row[f"{section}_mean"] = round(sum(vals) / len(vals), 4) if all(v is not None for v in vals) else None
                all_values = [value for values in groups.values() for value in values]
                row["mean"] = round(sum(all_values) / len(all_values), 4) if all(v is not None for v in all_values) else None
                design = _number_or_none(row.get("design_thickness"))
                if design is None:
                    design = _number_or_none(row.get("_design_thickness"))
                row["deviation"] = round(row["mean"] - design, 4) if row["mean"] is not None and design is not None else None
                row["conclusion"] = ("符合" if abs(row["deviation"]) <= 0.05 else "不符合") if row["deviation"] is not None else ""
            elif kind == "color":
                observations = [row.get("observer1"), row.get("observer2"), row.get("observer3")]
                severe = sum(x == "明显差异" for x in observations)
                unable = sum(x == "无法判定" for x in observations)
                row["overall"] = "无法判定" if unable >= 2 else ("明显差异" if severe >= 2 else "未见明显差异/轻微差异")
                row["conclusion"] = "不符合" if severe >= 2 else ("需复核" if unable >= 2 else "符合")
        except Exception:
            pass
        result.append(row)
    return result


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def result_summary(kind: str, rows: list[dict[str, Any]]) -> tuple[str, str]:
    rows = calculate_rows(kind, rows)
    conclusions = [str(x.get("conclusion", "")) for x in rows if x.get("conclusion")]
    if conclusions and all(x in ("符合", "合格") for x in conclusions):
        overall = "符合"
    elif any(x in ("不符合", "不合格") for x in conclusions):
        overall = "不符合"
    elif conclusions:
        overall = "；".join(dict.fromkeys(conclusions))
    else:
        overall = "仅描述结果"
    summary_parts = []
    labels = {
        "rough": ("平均Ra", "μm", "mean"),
        "mc_crack": ("结合强度", "MPa", "tau"),
        "xray": ("ROI平均灰度", "", "roi_mean"),
        "warp": ("翘曲变化量ΔH", "mm", "delta"),
        "cte": ("线膨胀系数α", "×10⁻⁶/K", "alpha"),
        "bend": ("0.2%规定非比例弯曲应力", "MPa", "stress_02"),
        "hv": ("平均维氏硬度", "HV10", "mean"),
        "thickness": ("平均厚度", "mm", "mean"),
        "color": ("目视比较结果", "", "overall"),
        "shock": ("耐急冷急热结果", "", "conclusion"),
    }
    title, unit, value_key = labels.get(kind, ("检验结果", "", "calculated_value"))
    for row in rows:
        sid = row.get("sample_no", "")
        if kind == "hv" and row.get("face"):
            sid = f"{sid}-{row.get('face')}"
        value = row.get(value_key)
        if value not in (None, ""):
            summary_parts.append(f"{sid}：{title}{_display_number(value)}{unit}")
    if not summary_parts:
        return "尚未形成有效检验结果", overall
    return "；".join(summary_parts), overall


def _display_number(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)
