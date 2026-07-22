# -*- coding: utf-8 -*-
from pathlib import Path
import tempfile
import lims_db
with tempfile.TemporaryDirectory() as td:
    lims_db.DB_PATH=Path(td)/"test.db"
    lims_db.init_db()
    orgs=lims_db.list_organizations()
    assert any(x["org_name"]=="测试委托客户（预设）" and x["is_client"] for x in orgs)
    assert any(x["org_name"]=="测试生产单位（预设）" and x["is_manufacturer"] for x in orgs)
    sample=next(x for x in lims_db.list_catalog() if x["sample_code"]=="S-DEFAULT")
    assert sample["sample_name"]=="测试金属试样（预设）"
    assert sample["model"]=="25 mm×2 mm×2 mm"
    assert sample["material_name"]=="钴铬合金"
    assert len(sample["experiment_labels"])==3
print("PRESET TEST PASSED")
