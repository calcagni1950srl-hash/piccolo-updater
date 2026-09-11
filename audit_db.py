import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "prezzi.db"
OUT_PATH = ROOT / "audit_piccolo.json"

TARGETS = {
    "mozzarella": ["mozzarella"],
    "pane": ["pane"],
    "zucchine": ["zucchin"],
    "cipolla": ["cipoll"],
    "olio_frittura": ["olio", "girasole", "arachide", "fritt"],
    "pere_frutta": ["pera", "pere"],
    "uova": ["uova"],
    "salsiccia": ["salsicc"],
}

def rows_as_dicts(cur):
    cols = [x[0] for x in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def main():
    if not DB_PATH.exists():
        raise SystemExit("prezzi.db non trovato")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(products_current)")}
    has_audit = "audit_status" in cols
    has_prev_low = "previous_lowest_price_eur" in cols
    has_last_seen = "last_seen_at" in cols

    select_cols = [
        "category", "name", "quantity_value", "quantity_unit",
        "price_eur", "unit_price_eur", "unit_price_unit",
        "variable_weight", "promo_until", "source_url", "checked_at",
    ]
    if has_audit:
        select_cols += ["audit_status", "audit_reason"]
    if has_prev_low:
        select_cols += ["previous_lowest_price_eur"]
    if has_last_seen:
        select_cols += ["last_seen_at"]

    rows = rows_as_dicts(conn.execute(f"SELECT {', '.join(select_cols)} FROM products_current"))

    status_counter = Counter((r.get("audit_status") or "LEGACY") for r in rows)
    reason_counter = Counter(r.get("audit_reason") for r in rows if r.get("audit_reason"))
    category_counter = Counter(r["category"] for r in rows)

    review_rows = [r for r in rows if (r.get("audit_status") or "").upper() == "REVIEW"]
    rejected_rows = [r for r in rows if (r.get("audit_status") or "").upper() == "REJECTED"]

    missing_qty = [r for r in rows if not r["variable_weight"] and (r["quantity_value"] is None or r["quantity_unit"] is None)]
    variable_without_unit_price = [r for r in rows if r["variable_weight"] and (r["unit_price_eur"] is None or not r["unit_price_unit"])]
    bad_price = [r for r in rows if r["price_eur"] is None or r["price_eur"] <= 0 or r["price_eur"] > 500]

    target_samples = {}
    for label, needles in TARGETS.items():
        matched = []
        for r in rows:
            low = r["name"].casefold()
            if any(n.casefold() in low for n in needles):
                matched.append(r)
        matched.sort(key=lambda x: (x["name"].casefold(), x["price_eur"]))
        target_samples[label] = matched[:50]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db": str(DB_PATH.name),
        "total_current_rows": len(rows),
        "by_category": dict(sorted(category_counter.items())),
        "audit_status_counts": dict(sorted(status_counter.items())),
        "audit_reason_counts": dict(sorted(reason_counter.items())),
        "review_rows": review_rows[:100],
        "rejected_rows": rejected_rows[:100],
        "anomalies": {
            "fixed_pack_missing_quantity_count": len(missing_qty),
            "variable_weight_missing_unit_price_count": len(variable_without_unit_price),
            "invalid_price_count": len(bad_price),
            "fixed_pack_missing_quantity_samples": missing_qty[:100],
            "variable_weight_missing_unit_price_samples": variable_without_unit_price[:100],
            "invalid_price_samples": bad_price[:100],
        },
        "priority_samples": target_samples,
    }

    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Audit scritto in {OUT_PATH.name}")
    print(f"Righe correnti: {len(rows)}")
    print(f"Stati: {dict(status_counter)}")
    print(f"REVIEW: {len(review_rows)}")
    for r in review_rows[:20]:
        print(f"[REVIEW] {r['category']} | {r['name']} | motivo={r.get('audit_reason')}")
    print(f"Confezioni fisse senza quantità: {len(missing_qty)}")
    print(f"Peso variabile senza prezzo unitario: {len(variable_without_unit_price)}")
    print(f"Prezzi non validi: {len(bad_price)}")

    conn.close()

if __name__ == "__main__":
    main()
