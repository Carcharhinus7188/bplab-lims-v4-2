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
        return defaults.get((kind, key), 0.0)
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
                vals = [_num(row.get("dm1")), _num(row.get("dm2")), _num(row.get("dm3"))]
                row["dm_mean"] = round(sum(vals) / 3, 4)
                row["tau"] = round(_num(row.get("k")) * _num(row.get("ffail")), 2)
                row["conclusion"] = "符合" if row["tau"] > 25 else "不符合"
            elif kind == "rough":
                vals = [_num(row.get("ra1")), _num(row.get("ra2")), _num(row.get("ra3"))]
                row["mean"] = round(sum(vals) / 3, 3)
                row["conclusion"] = "符合" if row["mean"] <= _num(row.get("limit"), 15) else "不符合"
            elif kind == "xray":
                vals = [_num(row.get("roi1")), _num(row.get("roi2")), _num(row.get("roi3"))]
                row["roi_mean"] = round(sum(vals) / 3, 2)
            elif kind == "warp":
                row["delta"] = round(_num(row.get("h1")) - _num(row.get("h2")), 4)
                row["conclusion"] = "合格" if abs(row["delta"]) <= _num(row.get("limit"), .5) else "不合格"
            elif kind == "cte":
                row["delta_t"] = round(_num(row.get("t2")) - _num(row.get("t1")), 3)
                l0, dt = _num(row.get("l0")), _num(row.get("delta_t"))
                row["alpha"] = round((_num(row.get("delta_l")) / 1000.0) / (l0 * dt) * 1_000_000, 3) if l0 and dt else 0.0
            elif kind == "shock":
                row["conclusion"] = "符合" if all(str(row.get(k, "无")) == "无" for k in ("crack", "chipping", "fracture")) else "不符合"
            elif kind == "bend":
                row["conclusion"] = "符合" if _num(row.get("stress_02")) >= 800 else "不符合"
            elif kind == "hv":
                vals = [_num(row.get("indent1")), _num(row.get("indent2")), _num(row.get("indent3"))]
                row["mean"] = round(sum(vals) / 3, 1)
            elif kind == "thickness":
                vals = [_num(row.get(k)) for k in ("fixed1", "fixed2", "middle1", "middle2", "free1", "free2")]
                row["mean"] = round(sum(vals) / len(vals), 4)
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
        overall = "见原始记录"
    summary_parts = []
    for row in rows[:12]:
        sid = row.get("sample_no", "")
        calculated = []
        for key in ("mean", "tau", "roi_mean", "delta", "alpha", "stress_02", "overall"):
            if row.get(key) not in (None, "", 0, 0.0):
                calculated.append(f"{key}={row[key]}")
        if calculated:
            summary_parts.append(f"{sid}：" + "，".join(calculated))
    return "；".join(summary_parts) or "详见原始记录", overall
