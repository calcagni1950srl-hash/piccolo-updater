from updater import parse_html

FIXTURE = '''
<html><body>
<div class="product-card">
  <div>IN OFFERTA fino al 13/09</div>
  <div>Amadori</div>
  <h3>Amadori Bistecca di pollo 500 g</h3>
  <div>500 gr</div><div>8,99 € al kg</div><div>Prezzo più basso precedente 5,50 €</div>
  <div>4,50€</div><button>Aggiungi</button>
</div>
<div class="product-card">
  <h3>ALI DI POLLO SP AL KG</h3><div>500 gr</div><div>2,99 € al kg</div>
  <div>Venduto a Peso</div><div>1,50€</div><button>Aggiungi</button>
</div>
</body></html>
'''

items = parse_html(FIXTURE, 'carne', 'fixture://carne')
assert len(items) == 2, items
assert items[0].name == 'Amadori Bistecca di pollo 500 g'
assert items[0].price_eur == 4.50
assert items[0].unit_price_eur == 8.99
assert items[0].promo_until == '13/09'
assert items[1].variable_weight == 1
assert items[1].price_eur == 1.50
print('TEST OK:', [(x.name, x.price_eur, x.unit_price_eur, x.variable_weight) for x in items])
