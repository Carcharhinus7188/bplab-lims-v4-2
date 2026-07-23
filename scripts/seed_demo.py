import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bplab.demo import seed_full_demo
from bplab.db import query_one


if __name__ == "__main__":
    commission_id = seed_full_demo()
    row = query_one("SELECT commission_no FROM commissions WHERE id=?", (commission_id,))
    print(f"已建立全实验测试委托：{row['commission_no']}")
