"""Repair only overlaps observed in Desktop on 20 October; no regeneration."""
import json
from pathlib import Path

P = Path(__file__).resolve().parent
CHANGES = {
    "P2.5": {"height": 136},
    "P2.6": {"height": 136},
    "P2.7": {"y": 636, "height": 80},
    "P5.6": {"height": 144},
    "P5.6.detail": {"height": 144},
    "P5.7.detail": {"height": 54},
}

def repair():
    for item in json.loads((P / "native_visual_map.json").read_text(encoding="utf8")):
        if item["layout"] not in CHANGES:
            continue
        path = (P / "NZ_Electricity_Market.Report/definition/pages" /
                item["page"] / "visuals" / item["visual"] / "visual.json")
        value = json.loads(path.read_text(encoding="utf8"))
        if all(value["position"].get(k) == v for k, v in CHANGES[item["layout"]].items()):
            continue
        value["position"].update(CHANGES[item["layout"]])
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")

if __name__ == "__main__":
    repair()
