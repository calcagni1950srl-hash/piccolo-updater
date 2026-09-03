from updater import quantity, parse_product_block

def check(got, expected, label):
    assert got == expected, f"{label}: ottenuto {got}, atteso {expected}"

# Quantity syntax regressions.
check(quantity("PICCOLO ORIGANO GR 15"), (15.0, "gr"), "origano reverse")
check(quantity("PICCOLO PEPE NERO MACINATO GR 35"), (35.0, "gr"), "pepe reverse")
check(quantity("PICCOLO OLIO DI GIRASOLE LT 1"), (1.0, "lt"), "olio reverse")
check(quantity("BENEDUCE MOZZARELLA GR 250"), (250.0, "gr"), "mozzarella reverse")
check(quantity("Prodotto 2 x 50 g"), (100.0, "gr"), "multipack")

# Fixed pack: name quantity must beat bad card metadata.
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
assert abs(p.unit_price_eur - 73.33) < 0.01, p.unit_price_eur

# Variable weight: card default weight must beat a title ending in KG 1.
p = parse_product_block(
    "ARISTA DI MAIALE KG 1",
    """ARISTA DI MAIALE KG 1
Venduto a Peso
500 gr
8,99 € al kg
4,50 €
Aggiungi""",
    "carne",
    "https://example.test/arista",
)
assert p is not None
check((p.quantity_value, p.quantity_unit), (500.0, "gr"), "variable card precedence")
assert p.variable_weight == 1

print("OK - test_parser V6 superati")
