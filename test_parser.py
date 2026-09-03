from updater import quantity, parse_product_block

def check(got, expected, label):
    assert got == expected, f"{label}: ottenuto {got}, atteso {expected}"

# Regressioni V6.
check(quantity("PICCOLO ORIGANO GR 15"), (15.0, "gr"), "origano reverse")
check(quantity("PICCOLO PEPE NERO MACINATO GR 35"), (35.0, "gr"), "pepe reverse")
check(quantity("PICCOLO OLIO DI GIRASOLE LT 1"), (1.0, "lt"), "olio reverse")
check(quantity("Prodotto 2 x 50 g"), (100.0, "gr"), "multipack classico")

# Sealed pack, reversed syntax: name remains authoritative.
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

# Sold-by-weight product: 500 g is correct, despite "KG 1" in catalogue title.
p = parse_product_block(
    "PANE GRATTUGIATO KG 1",
    """PANE GRATTUGIATO KG 1
500 gr
2,55 € al kg
Venduto a Peso
1,27 €
Aggiungi""",
    "pane",
    "https://example.test/pane-grattugiato",
)
assert p is not None
check((p.quantity_value, p.quantity_unit), (500.0, "gr"), "pane grattugiato live weight")
assert p.variable_weight == 1
assert abs(p.unit_price_eur - 2.55) < 0.001

# Ambiguous catalogue multipack: current live-card weight wins.
p = parse_product_block(
    "DUEGI IL PANUOZZO X2 GR 400",
    """DUEGI IL PANUOZZO X2 GR 400
350 gr
7,00 € al kg
2,45 €
Aggiungi""",
    "pasta_pane_farinacei",
    "https://example.test/panuozzo",
)
assert p is not None
check((p.quantity_value, p.quantity_unit), (350.0, "gr"), "panuozzo live weight")
assert p.variable_weight == 0
assert abs(p.unit_price_eur - 7.00) < 0.001

print("OK - test_parser V7 superati")
