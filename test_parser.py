from updater import parse_html

FIXTURE = """
<html><body>

<div class="product-card">
  <h3>AVIMECC HAMBURGER POLLO</h3>
  <div>160 gr</div>
  <div>8,13 € al kg</div>
  <div>1,30€</div>
  <button>Aggiungi</button>
</div>

<div class="product-card">
  <h3>ALI DI POLLO SP AL KG</h3>
  <div>500 gr</div>
  <div>2,99 € al kg</div>
  <div>Venduto a Peso</div>
  <div>1,50€</div>
  <button>Aggiungi</button>
</div>

<div class="product-card">
  <div>IN OFFERTA fino al 13/09</div>
  <h3>Amadori le Birbe Classiche 0,300 kg</h3>
  <div>300 gr</div>
  <div>8,30 € al kg</div>
  <div>2,99 €</div>
  <div>2,49€</div>
  <div>-17%</div>
  <button>Aggiungi</button>
</div>

<div class="product-card">
  <h3>Amadori Polpettine Ricetta Classica 0,240 kg</h3>
  <div>240 pz</div>
  <div>0,01 € al pezzo</div>
  <div>2,79€</div>
  <button>Aggiungi</button>
</div>

</body></html>
"""

items = parse_html(FIXTURE, "carne", "fixture://carne")
assert len(items) == 4, items

a = items[0]
assert a.name == "AVIMECC HAMBURGER POLLO"
assert a.quantity_value == 160
assert a.quantity_unit == "gr"
assert a.unit_price_eur == 8.13
assert a.unit_price_unit == "kg"
assert a.price_eur == 1.30
assert a.list_price_eur is None

b = items[1]
assert b.price_eur == 1.50
assert b.unit_price_eur == 2.99
assert b.variable_weight == 1

c = items[2]
assert c.price_eur == 2.49
assert c.list_price_eur == 2.99
assert c.discount_pct == 16.7
assert c.promo_until == "13/09"

d = items[3]
assert d.price_eur == 2.79
assert d.unit_price_eur == 0.01
assert d.unit_price_unit == "pezzo"

print("TEST OK")
for x in items:
    print(
        x.name,
        "| prezzo:", x.price_eur,
        "| unitario:", x.unit_price_eur, x.unit_price_unit,
        "| listino:", x.list_price_eur,
        "| sconto:", x.discount_pct,
        "| promo:", x.promo_until,
        "| peso variabile:", x.variable_weight,
    )


def test_bad_catalogue_metadata_is_corrected():
    html = """
    <div class="card">
      <h3>Senfter Servelade 200 g</h3>
      <div>200 kg</div>
      <div>0,01 € al kg</div>
      <div>1,99 €</div>
      <div>1,49€</div>
      <div>-25%</div>
      <div>IN OFFERTA fino al 13/09</div>
      <button>Aggiungi</button>
    </div>
    """
    products = parse_html(html, "salumi", "test")
    assert len(products) == 1
    p = products[0]
    assert p.quantity_value == 200
    assert p.quantity_unit == "gr"
    assert p.price_eur == 1.49
    assert p.unit_price_eur == 7.45
    assert p.unit_price_unit == "kg"
    assert p.list_price_eur == 1.99
    assert p.promo_until == "13/09"


def test_multipack_quantity():
    html = """
    <div class="card">
      <h3>Senfter Cubetti di Speck 2 x 50 g</h3>
      <div>100 gr</div>
      <div>29,00 € al kg</div>
      <div>2,90€</div>
      <button>Aggiungi</button>
    </div>
    """
    products = parse_html(html, "salumi", "test")
    assert len(products) == 1
    p = products[0]
    assert p.quantity_value == 100
    assert p.quantity_unit == "gr"
    assert p.unit_price_eur == 29.0
