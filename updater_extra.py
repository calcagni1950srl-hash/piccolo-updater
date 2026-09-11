import sqlite3
import sys
from datetime import datetime, timezone

from updater import (
    BASE,
    STORE_CODE,
    DB_PATH,
    fetch,
    parse_html,
    save_category,
    _product_is_sane,
    init_db,
)

# Categorie aggiuntive necessarie al motore ricette Smart Campania.
# Vino era assente dal catalogo locale; Gastronomia copre alcuni prodotti
# confezionati reali (es. acciughe) non presenti nelle macro-categorie base.
EXTRA_CATEGORIES = {
    "vino": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/vino-amari-e-distillati_342?d=1&s=g&sort=price",
    "gastronomia": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/gastronomia_13?d=1&s=g&sort=price",
}


def run():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    failures = 0
    total = 0

    for category, url in EXTRA_CATEGORIES.items():
        try:
            html = fetch(url)
            products = parse_html(html, category, url)
            save_category(conn, category, products)

            sane_products = [p for p in products if _product_is_sane(p)]
            valid_count = len(sane_products)
            certified_count = len([p for p in sane_products if p.audit_status == "VALID"])
            review_count = len([p for p in sane_products if p.audit_status == "REVIEW"])
            total += certified_count

            conn.execute(
                """
                INSERT INTO update_log
                (checked_at,category,status,products_found,message)
                VALUES(?,?,?,?,?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    category,
                    "OK",
                    valid_count,
                    f"certificati={certified_count}; review={review_count}",
                ),
            )
            conn.commit()
            print(
                f"[OK EXTRA] {category}: estratti={valid_count}; "
                f"certificati={certified_count}; review={review_count}"
            )
        except Exception as exc:
            failures += 1
            conn.execute(
                """
                INSERT INTO update_log
                (checked_at,category,status,products_found,message)
                VALUES(?,?,?,?,?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    category,
                    "ERROR",
                    0,
                    str(exc),
                ),
            )
            conn.commit()
            print(f"[ERRORE EXTRA] {category}: {exc}", file=sys.stderr)

    conn.close()
    print(f"Totale prodotti extra certificati: {total}; categorie fallite: {failures}")

    if failures:
        sys.exit(2)


if __name__ == "__main__":
    run()
