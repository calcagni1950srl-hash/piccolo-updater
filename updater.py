import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.piccolospesaonline.it'
STORE_CODE = '8004C'
DB_PATH = Path(__file__).with_name('prezzi.db')

CATEGORIES = {
    'carne': f'{BASE}/spesa-consegna-domicilio/{STORE_CODE}/carne_5?d=1&s=g&sort=price',
    'pasta': f'{BASE}/spesa-consegna-domicilio/{STORE_CODE}/pasta_195?d=1&s=g&sort=price',
    'legumi': f'{BASE}/spesa-consegna-domicilio/{STORE_CODE}/legumi-secchi_4073?d=1&s=g&sort=price',
    'latte': f'{BASE}/spesa-consegna-domicilio/{STORE_CODE}/latte_159?d=1&s=g&sort=price',
    'verdura': f'{BASE}/spesa-consegna-domicilio/{STORE_CODE}/verdura-fresca-e-ortaggi_139?d=1&s=g&sort=price',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; SmartCampaniaPriceBot/0.1; +personal-research)',
    'Accept-Language': 'it-IT,it;q=0.9,en;q=0.7',
}

@dataclass
class Product:
    supermarket: str
    store_code: str
    category: str
    name: str
    quantity_value: float | None
    quantity_unit: str | None
    price_eur: float
    unit_price_eur: float | None
    unit_price_unit: str | None
    variable_weight: int
    promo_until: str | None
    source_url: str
    checked_at: str


def euro(s: str) -> float | None:
    if not s:
        return None
    m = re.search(r'(\d+(?:[.,]\d{1,2})?)\s*€', s)
    return float(m.group(1).replace(',', '.')) if m else None


def quantity(s: str):
    m = re.search(r'(?<!\d)(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|cl|lt|l|pz)\b', s, re.I)
    if not m:
        return None, None
    return float(m.group(1).replace(',', '.')), m.group(2).lower()


def unit_price(s: str):
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*€\s*al\s*(kg|litro|l|pezzo)', s, re.I)
    if not m:
        return None, None
    return float(m.group(1).replace(',', '.')), m.group(2).lower()


def promo_until(s: str):
    m = re.search(r'IN OFFERTA\s+fino al\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)', s, re.I)
    return m.group(1) if m else None


def parse_product_block(name: str, text: str, category: str, source_url: str) -> Product | None:
    # Remove the title itself before price matching to avoid numbers embedded in names.
    body = text.replace(name, ' ', 1)
    prices = [float(x.replace(',', '.')) for x in re.findall(r'(\d+(?:[.,]\d{1,2})?)\s*€', body)]
    if not prices:
        return None

    # On promoted cards the final selling price is normally the last explicit euro amount.
    price = prices[-1]
    qv, qu = quantity(body)
    up, uu = unit_price(body)

    # Basic sanity filters: reject obviously broken cards.
    if price <= 0 or price > 500:
        return None
    if up is not None and (up <= 0 or up > 1000):
        up = None
        uu = None

    return Product(
        supermarket='Piccolo',
        store_code=STORE_CODE,
        category=category,
        name=' '.join(name.split()),
        quantity_value=qv,
        quantity_unit=qu,
        price_eur=price,
        unit_price_eur=up,
        unit_price_unit=uu,
        variable_weight=1 if re.search(r'Venduto\s+a\s+Peso|SP\.?\s*(?:AL\s+)?KG', text, re.I) else 0,
        promo_until=promo_until(text),
        source_url=source_url,
        checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    )


def parse_html(html: str, category: str, source_url: str) -> list[Product]:
    soup = BeautifulSoup(html, 'html.parser')
    products: list[Product] = []

    # Piccolo currently renders product names as H3 headings on category pages.
    for h3 in soup.find_all('h3'):
        name = h3.get_text(' ', strip=True)
        if not name:
            continue

        # Walk up a few levels until we find the card containing a euro price.
        node = h3
        card_text = ''
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            candidate = node.get_text(' ', strip=True)
            if '€' in candidate and len(candidate) < 3000:
                card_text = candidate
                # A product card should include add-to-cart or a unit-price marker.
                if 'Aggiungi' in candidate or '€ al ' in candidate:
                    break

        if not card_text:
            continue
        p = parse_product_block(name, card_text, category, source_url)
        if p:
            products.append(p)

    # Dedupe by category/name/price while preserving order.
    seen = set()
    unique = []
    for p in products:
        key = (p.category, p.name.casefold(), p.price_eur)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if len(r.text) < 5000:
        raise RuntimeError(f'Pagina troppo piccola ({len(r.text)} byte): possibile blocco o errore')
    return r.text


def init_db(conn: sqlite3.Connection):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS products_current (
        supermarket TEXT NOT NULL,
        store_code TEXT NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        quantity_value REAL,
        quantity_unit TEXT,
        price_eur REAL NOT NULL,
        unit_price_eur REAL,
        unit_price_unit TEXT,
        variable_weight INTEGER NOT NULL DEFAULT 0,
        promo_until TEXT,
        source_url TEXT NOT NULL,
        checked_at TEXT NOT NULL,
        PRIMARY KEY (supermarket, store_code, category, name)
    );
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supermarket TEXT NOT NULL,
        store_code TEXT NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        price_eur REAL NOT NULL,
        checked_at TEXT NOT NULL,
        source_url TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS update_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checked_at TEXT NOT NULL,
        category TEXT NOT NULL,
        status TEXT NOT NULL,
        products_found INTEGER NOT NULL,
        message TEXT
    );
    ''')


def save_category(conn: sqlite3.Connection, category: str, products: Iterable[Product]):
    products = list(products)
    # Guardrail: do not replace a category if extraction suddenly collapses.
    old_count = conn.execute(
        'SELECT COUNT(*) FROM products_current WHERE supermarket=? AND store_code=? AND category=?',
        ('Piccolo', STORE_CODE, category),
    ).fetchone()[0]
    if old_count >= 10 and len(products) < max(3, int(old_count * 0.30)):
        raise RuntimeError(f'estrazione anomala: {len(products)} prodotti contro {old_count} precedenti')
    if len(products) < 1:
        raise RuntimeError('nessun prodotto estratto')

    with conn:
        for p in products:
            previous = conn.execute(
                '''SELECT price_eur FROM products_current
                   WHERE supermarket=? AND store_code=? AND category=? AND name=?''',
                (p.supermarket, p.store_code, p.category, p.name),
            ).fetchone()
            if previous is None or abs(previous[0] - p.price_eur) > 1e-9:
                conn.execute(
                    '''INSERT INTO price_history
                       (supermarket,store_code,category,name,price_eur,checked_at,source_url)
                       VALUES (?,?,?,?,?,?,?)''',
                    (p.supermarket,p.store_code,p.category,p.name,p.price_eur,p.checked_at,p.source_url),
                )
            conn.execute(
                '''INSERT INTO products_current
                   (supermarket,store_code,category,name,quantity_value,quantity_unit,price_eur,
                    unit_price_eur,unit_price_unit,variable_weight,promo_until,source_url,checked_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(supermarket,store_code,category,name) DO UPDATE SET
                     quantity_value=excluded.quantity_value,
                     quantity_unit=excluded.quantity_unit,
                     price_eur=excluded.price_eur,
                     unit_price_eur=excluded.unit_price_eur,
                     unit_price_unit=excluded.unit_price_unit,
                     variable_weight=excluded.variable_weight,
                     promo_until=excluded.promo_until,
                     source_url=excluded.source_url,
                     checked_at=excluded.checked_at''',
                (p.supermarket,p.store_code,p.category,p.name,p.quantity_value,p.quantity_unit,p.price_eur,
                 p.unit_price_eur,p.unit_price_unit,p.variable_weight,p.promo_until,p.source_url,p.checked_at),
            )


def run():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    failures = 0
    total = 0
    for category, url in CATEGORIES.items():
        try:
            html = fetch(url)
            products = parse_html(html, category, url)
            save_category(conn, category, products)
            total += len(products)
            conn.execute('INSERT INTO update_log(checked_at,category,status,products_found,message) VALUES(?,?,?,?,?)',
                         (datetime.now(timezone.utc).isoformat(timespec='seconds'), category, 'OK', len(products), None))
            conn.commit()
            print(f'[OK] {category}: {len(products)} prodotti')
        except Exception as exc:
            failures += 1
            conn.execute('INSERT INTO update_log(checked_at,category,status,products_found,message) VALUES(?,?,?,?,?)',
                         (datetime.now(timezone.utc).isoformat(timespec='seconds'), category, 'ERROR', 0, str(exc)))
            conn.commit()
            print(f'[ERRORE] {category}: {exc}', file=sys.stderr)
    conn.close()
    print(f'Totale prodotti estratti: {total}; categorie fallite: {failures}')
    if failures:
        sys.exit(2)

if __name__ == '__main__':
    run()
