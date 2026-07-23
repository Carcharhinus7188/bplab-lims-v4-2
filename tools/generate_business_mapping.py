from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from business_record_engine import (
    AUTO_ROW_KEYS,
    HIDDEN_PARAMETER_KEYS,
    OPTIONAL_PARAMETER_KEYS,
    OPTIONAL_ROW_KEYS,
)
from constants import EXPERIMENTS
from experiment_schemas import SCHEMAS


def parameter_source(field: dict) -> tuple[str, str]:
    key = field["key"]
    if field.get("readonly") or key in HIDDEN_PARAMETER_KEYS:
        return "前序流程、配置快照或附件索引自动带入", "只读摘要或后台隐藏"
    if field.get("actual"):
        return "实验员填写本次实际值", "简洁填空/选项；过程明细可折叠"
    if field.get("default") not in (None, ""):
        return "现行实验配置默认值；发生偏离时修改", "默认只读；选择偏离后展开"
    return "实验员填写或确认", "简洁填空/选项"


def build_rows() -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for experiment, config in EXPERIMENTS.items():
        definition = SCHEMAS[config["kind"]]
        for section in definition["sections"]:
            for field in section["fields"]:
                source, logic = parameter_source(field)
                output.append(
                    {
                        "实验名称": experiment,
                        "检测方法": config["method"],
                        "页面分区": section["title"],
                        "字段类别": "参数",
                        "字段键": field["key"],
                        "界面名称": field["label"],
                        "控件类型": field.get("type", "text"),
                        "数据来源": source,
                        "默认值": json.dumps(field.get("default", ""), ensure_ascii=False)
                        if isinstance(field.get("default"), list)
                        else str(field.get("default", "") or ""),
                        "是否必填": "系统自动" if field.get("readonly") or field["key"] in HIDDEN_PARAMETER_KEYS
                        else ("否" if field["key"] in OPTIONAL_PARAMETER_KEYS else "是"),
                        "显示逻辑": logic,
                    }
                )
        for key, label, field_type in definition["columns"]:
            automatic = field_type == "calc" or key in AUTO_ROW_KEYS
            output.append(
                {
                    "实验名称": experiment,
                    "检测方法": config["method"],
                    "页面分区": "原始测量数据",
                    "字段类别": "样品数据",
                    "字段键": key,
                    "界面名称": label,
                    "控件类型": field_type,
                    "数据来源": "系统自动计算/附件索引自动关联" if automatic else "实验员按样品填写或选择",
                    "默认值": "",
                    "是否必填": "系统自动" if automatic else ("否" if key in OPTIONAL_ROW_KEYS or key == "note" else "是"),
                    "显示逻辑": "只读结果/后台关联" if automatic else "样品卡片",
                }
            )
    return output


def main() -> None:
    rows = build_rows()
    columns = list(rows[0])
    with (ROOT / "business_field_mapping_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["实验名称"] for row in rows)
    coverage = {
        "version": "V5.7",
        "experiment_count": len(EXPERIMENTS),
        "business_field_count": len(rows),
        "per_experiment": dict(counts),
        "principles": [
            "前序流程数据只读继承",
            "现行配置提供合理默认值",
            "实验员只填写本次实际值",
            "计算结果只读",
            "附件索引不进入人工重复填写",
            "原始记录与报告仅回填既有母版位置",
        ],
    }
    (ROOT / "business_field_coverage_summary.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Generated {len(rows)} business fields for {len(EXPERIMENTS)} experiments")


if __name__ == "__main__":
    main()
