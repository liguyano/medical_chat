"""默认人工题配置测试。"""

import json
from pathlib import Path


def test_adl_observed_mobility_items_are_manual() -> None:
    catalog_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "structured"
        / "assessment-scales"
        / "adl.json"
    )
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    items = {item["id"]: item for item in payload["scoring"]["items"]}

    for question_code in ("bed_chair_transfer", "walking_45m", "stairs"):
        assert items[question_code]["validation_rule"]["manual_required"] is True
