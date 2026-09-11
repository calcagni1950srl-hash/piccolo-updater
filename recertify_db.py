import sqlite3
from pathlib import Path

from updater import certify_product

DB_PATH = Path(__file__).with_name("prezzi.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT supermarket, store_code, category, name,
               price_eur, quantity_value, quantity_unit,
               unit_price_eur, unit_price_unit, variable_weight,
               audit_status, audit_reason
        FROM products_current
        """
    ).fetchall()

    changed = 0
    with conn:
        for row in rows:
            (
                supermarket, store_code, category, name,
                price_eur, qv, qu,
                unit_price_eur, unit_price_unit, variable_weight,
                old_status, old_reason,
            ) = row

            new_status, new_reason = certify_product(
                name=name,
                price=price_eur,
                qv=qv,
                qu=qu,
                unit_price_value=unit_price_eur,
                unit_price_unit=unit_price_unit,
                variable_weight=variable_weight,
            )

            if new_status != old_status or new_reason != old_reason:
                conn.execute(
                    """
                    UPDATE products_current
                    SET audit_status=?, audit_reason=?
                    WHERE supermarket=? AND store_code=? AND category=? AND name=?
                    """,
                    (
                        new_status, new_reason,
                        supermarket, store_code, category, name,
                    ),
                )
                changed += 1
                print(
                    f"[RICERTIFICA] {category} | {name} | "
                    f"{old_status}/{old_reason} -> {new_status}/{new_reason}"
                )

    print(f"Righe ricertificate/modificate: {changed}")
    conn.close()


if __name__ == "__main__":
    main()
