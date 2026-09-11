
import sqlite3
from updater import (
    quantity, parse_product_block, init_db, save_category, Product, STORE_CODE
)

def check(got, expected, label):
    assert got == expected, f"{label}: ottenuto {got!r}, atteso {expected!r}"

check(quantity("PICCOLO ORIGANO GR 15"), (15.0, "gr"), "origano reverse")
check(quantity("PICCOLO PEPE NERO MACINATO GR 35"), (35.0, "gr"), "pepe reverse")
check(quantity("PICCOLO OLIO DI GIRASOLE LT 1"), (1.0, "lt"), "olio reverse")
check(quantity("Prodotto 2 x 50 g"), (100.0, "gr"), "multipack classico")

p = parse_product_block(
    "PICCOLO ORIGANO GR 15",
    """PICCOLO ORIGANO GR 15
20 gr
55,00 € al kg
1,10 €
Aggiungi""",
    "condimenti",
    "https://example.test/origano",
)
assert p is not None
check((p.quantity_value, p.quantity_unit), (15.0, "gr"), "fixed name precedence")
check(p.audit_status, "VALID", "fixed certified")

p = parse_product_block(
    "PANE BIANCO AL KG",
    """PANE BIANCO AL KG
500 gr
2,70 € al kg
Venduto a Peso
1,35 €
Aggiungi""",
    "pasta_pane_farinacei",
    "https://example.test/pane",
)
assert p is not None
check(p.variable_weight, 1, "pane variable")
check(p.audit_status, "VALID", "pane certified")
check((p.quantity_value, p.quantity_unit), (500.0, "gr"), "pane default weight")

p = parse_product_block(
    "PRODOTTO SENZA FORMATO",
    """PRODOTTO SENZA FORMATO
2,49 €
Aggiungi""",
    "x",
    "https://example.test/noqty",
)
assert p is not None
check(p.audit_status, "REVIEW", "fixed no quantity review")
check(p.audit_reason, "CONFEZIONE_SENZA_QUANTITA", "fixed no quantity reason")

p = parse_product_block(
    "BENEDUCE MOZZARELLA GR 250",
    """BENEDUCE MOZZARELLA GR 250
250 gr
Prezzo più basso precedente 2,25 €
8,00 € al kg
2,00 €
IN OFFERTA fino al 13/09
Aggiungi""",
    "formaggi",
    "https://example.test/mozzarella",
)
assert p is not None
check(p.previous_lowest_price_eur, 2.25, "previous lowest separated")
check(p.list_price_eur, None, "not fake list price")
check(p.discount_pct, None, "no fake discount")
check(p.price_eur, 2.0, "selling price")

# Snapshot semantics: stale row must be archived after a successful extraction.
c = sqlite3.connect(":memory:")
init_db(c)
now = "2026-09-10T17:00:00+00:00"

def prod(name, price=1.0):
    return Product(
        supermarket="Piccolo", store_code=STORE_CODE, category="test",
        name=name, quantity_value=500.0, quantity_unit="gr",
        price_eur=price, unit_price_eur=price*2, unit_price_unit="kg",
        list_price_eur=None, previous_lowest_price_eur=None,
        discount_pct=None, variable_weight=0,
        audit_status="VALID", audit_reason=None,
        promo_until=None, source_url="https://example.test", checked_at=now
    )

save_category(c, "test", [prod("A"), prod("B")])
check(c.execute("select count(*) from products_current").fetchone()[0], 2, "initial snapshot")
save_category(c, "test", [prod("B"), prod("C")])
names = [r[0] for r in c.execute("select name from products_current order by name")]
check(names, ["B", "C"], "stale removed")
arch = c.execute("select name, reason from products_archive").fetchall()
check(arch, [("A", "NON_PIU_PRESENTE_NELLO_SNAPSHOT_CATEGORIA")], "stale archived")
check(c.execute("select count(*) from products_certified").fetchone()[0], 2, "certified view")

print("OK - test_parser V8 superati")

# Regressione multipack Piccolo: ordine UNITA QUANTITA X PEZZI
assert quantity("MARRANDINO MOZZARELLA BUFALA GR 100 X 5") == (500.0, "gr")
assert quantity("LA PERLA MOZZARELLA DI BUFALA GR 125 X 2") == (250.0, "gr")

# Regressione: "TIPO 00 KG 1" deve ignorare lo 00 e leggere KG 1.
assert quantity("PICCOLO FARINA TIPO 00 KG 1") == (1.0, "kg")
