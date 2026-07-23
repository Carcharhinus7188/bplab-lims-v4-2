from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import BinaryIO

from .config import ATTACHMENT_DIR
from .db import execute, now_iso, query_one


ATTACHMENT_TYPES = [
    "实验过程照片",
    "软件截图",
    "仪器输出数据",
    "曲线文件",
    "图像文件",
    "原始数据文件",
    "异常证明文件",
    "其他",
]


def save_attachment(
    *,
    commission_id: int,
    task_id: int | None,
    sample_group_id: int | None,
    sample_id: str,
    attachment_type: str,
    original_filename: str,
    content: bytes,
    uploaded_by: int,
    description: str,
    source_relation: str = "原始文件",
    generated_at: str | None = None,
    path: Path | None = None,
) -> int:
    digest = hashlib.sha256(content).hexdigest()
    existing = query_one(
        "SELECT id FROM attachments WHERE commission_id=? AND sha256=?",
        (commission_id, digest),
        path,
    )
    if existing:
        return int(existing["id"])
    row = query_one(
        "SELECT commission_no FROM commissions WHERE id=?",
        (commission_id,),
        path,
    )
    if not row:
        raise ValueError("委托不存在")
    count = query_one(
        "SELECT COUNT(*) AS n FROM attachments WHERE commission_id=?",
        (commission_id,),
        path,
    )["n"]
    attachment_no = f"ATT-{row['commission_no']}-{int(count) + 1:03d}"
    suffix = Path(original_filename).suffix.lower()
    safe_name = f"{attachment_no}{suffix}"
    folder = ATTACHMENT_DIR / row["commission_no"]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe_name
    target.write_bytes(content)
    relative_path = str(target.relative_to(ATTACHMENT_DIR.parent))
    return execute(
        """INSERT INTO attachments(
            attachment_no,commission_id,task_id,sample_group_id,sample_id,attachment_type,
            original_filename,relative_path,generated_at,uploaded_by,description,
            source_relation,sha256
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            attachment_no,
            commission_id,
            task_id,
            sample_group_id,
            sample_id,
            attachment_type,
            original_filename,
            relative_path,
            generated_at or now_iso(),
            uploaded_by,
            description,
            source_relation,
            digest,
        ),
        path,
    )

