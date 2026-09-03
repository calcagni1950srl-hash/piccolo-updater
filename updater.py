import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

BASE = "https://www.piccolospesaonline.it"
STORE_CODE = "8004C"
DB_PATH = Path(__file__).with_name("prezzi.db")

CATEGORIES = {
    # Macro-categorie V5: servono al motore ricette.
    # Manteniamo anche alcune categorie specialistiche già affidabili.
    "verdura_legumi_cereali": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/verdura-legumi-e-cereali_7?d=1&s=g&sort=price",
    "pasta_pane_farinacei": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/pasta-pane-e-farinacei_12?d=1&s=g&sort=price",
    "condimenti": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/condimenti_351?d=1&s=g&sort=price",
    "sughi": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/sughi_350?d=1&s=g&sort=price",
    "dolci_dispensa": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/dolci_17?d=1&s=g&sort=price",
    "dispensa_scatolame": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/dispensa-e-scatolame_352?d=1&s=g&sort=price",

    # Categorie già validate nelle versioni precedenti.
    "carne": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/carne_5?d=1&s=g&sort=price",
    "latte": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/latte_159?d=1&s=g&sort=price",
    "formaggi": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/formaggi_8?d=1&s=g&sort=price",
    "uova": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/uova_161?d=1&s=g&sort=price",
    "frutta": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/frutta_277?d=1&s=g&sort=price",
    "salumi": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/salumi_9?d=1&s=g&sort=price",
    "olio": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/olio_349?d=1&s=g&sort=price",
    "pesce_surgelato": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/pesce-surgelato_253?d=1&s=g&sort=price",
    "pesce_scatola": f"{BASE}/spesa-consegna-domicilio/{STORE_CODE}/tonno-e-pesce-in-scatola_209?d=1&s=g&sort=price",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SmartCampaniaPriceBot/0.4; +personal-research)",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
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
    list_price_eur: float | None
    discount_pct: float | None
    variable_weight: int
    promo_until: str | None
    source_url: str
    checked_at: str


def _float_it(value: str) -> float:
    return float(value.replace(",", "."))


def quantity(text: str):
    """
    Read an explicit product quantity such as:
      500 gr, 200 g, 0,5 kg, 1 lt, 6 pz, 2 x 50 g
    and catalogue-style reversed forms such as:
      GR 15, KG 1, LT 1.

    When used on a fixed-pack product NAME this is more reliable than
    Piccolo's card metadata. For variable-weight products the parser instead
    trusts the card metadata/default weight.
    """
    # Multipack: "2 x 50 g" -> 100 gr.
    mm = re.search(
        r"(?<![\d.,])(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|cl|lt|l|pz)\b",
        text,
        re.I,
    )
    if mm:
        n = float(mm.group(1))
        value = _float_it(mm.group(2)) * n
        unit = mm.group(3).lower()
        if unit == "g":
            unit = "gr"
        elif unit == "l":
            unit = "lt"
        return value, unit

    # Standard order: "15 gr", "1 kg".
    m = re.search(
        r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|cl|lt|l|pz)\b",
        text,
        re.I,
    )
    if m:
        value = _float_it(m.group(1))
        unit = m.group(2).lower()
        if unit == "g":
            unit = "gr"
        elif unit == "l":
            unit = "lt"
        return value, unit

    # Piccolo names often use reversed order: "ORIGANO GR 15", "OLIO LT 1".
    m = re.search(
        r"\b(kg|gr|g|ml|cl|lt|l|pz)\s*(\d+(?:[.,]\d+)?)\b",
        text,
        re.I,
    )
    if not m:
        return None, None
    unit = m.group(1).lower()
    value = _float_it(m.group(2))
    if unit == "g":
        unit = "gr"
    elif unit == "l":
        unit = "lt"
    return value, unit



def _ambiguous_reversed_multipack_name(text: str) -> bool:
    """
    Piccolo sometimes uses catalogue names such as:
        DUEGI IL PANUOZZO X2 GR 400

    This is not the same syntax as "2 x 50 g".  The X2 is a piece count,
    while "GR 400" is catalogue text and can disagree with the current
    selling-card weight.  In this case the live card is preferred when it
    provides a coherent quantity/price/unit-price trio.
    """
    return bool(
        re.search(
            r"\bX\s*\d+\s+(?:KG|GR|G|ML|CL|LT|L)\s*\d+(?:[.,]\d+)?\b",
            text,
            re.I,
        )
    )

def _calculated_unit_price(price: float, qv: float | None, qu: str | None):
    """Return mathematically derived €/kg, €/L or €/piece for fixed packs."""
    if not qv or not qu or qv <= 0:
        return None, None

    qu = qu.lower()
    if qu == "gr":
        kg = qv / 1000.0
        return (round(price / kg, 2), "kg") if kg > 0 else (None, None)
    if qu == "kg":
        return round(price / qv, 2), "kg"
    if qu == "ml":
        litres = qv / 1000.0
        return (round(price / litres, 2), "litro") if litres > 0 else (None, None)
    if qu == "cl":
        litres = qv / 100.0
        return (round(price / litres, 2), "litro") if litres > 0 else (None, None)
    if qu == "lt":
        return round(price / qv, 2), "litro"
    if qu == "pz":
        return round(price / qv, 2), "pezzo"
    return None, None


def _unit_prices_compatible(source_value, source_unit, calc_value, calc_unit) -> bool:
    if source_value is None or calc_value is None:
        return False

    su = (source_unit or "").lower()
    cu = (calc_unit or "").lower()

    kg_units = {"kg"}
    litre_units = {"litro", "l", "lt"}
    piece_units = {"pezzo", "pz"}

    same_family = (
        (su in kg_units and cu in kg_units)
        or (su in litre_units and cu in litre_units)
        or (su in piece_units and cu in piece_units)
    )
    if not same_family:
        return False

    # Allow normal rounding differences, but reject impossible catalogue metadata.
    tolerance = max(0.05, calc_value * 0.08)
    return abs(source_value - calc_value) <= tolerance


def unit_price(text: str):
    # Piccolo examples:
    # 8,13 € al kg
    # 0,01 € al pezzo
    # 1,29 € al litro
    m = re.search(
        r"(\d+(?:[.,]\d{1,2})?)\s*€\s*al\s*(kg|litro|l|lt|pezzo|pz)\b",
        text,
        re.I,
    )
    if not m:
        return None, None
    return _float_it(m.group(1)), m.group(2).lower()


def _non_unit_prices(text: str) -> list[float]:
    """
    Return only real selling/list prices, excluding unit prices such as
    '8,13 € al kg'. On a promoted card Piccolo normally shows:
        8,30 € al kg
        2,99 €
        2,49€
        -17%
    so this returns [2.99, 2.49].
    """
    values: list[float] = []
    pattern = re.compile(
        r"(\d+(?:[.,]\d{1,2})?)\s*€(?!\s*al\s*(?:kg|litro|l|lt|pezzo|pz)\b)",
        re.I,
    )
    for m in pattern.finditer(text):
        values.append(_float_it(m.group(1)))
    return values


def promo_until(text: str):
    # Current Piccolo pages show e.g. "IN OFFERTA fino al 13/09".
    m = re.search(
        r"IN\s+OFFERTA\s*fino\s+al\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
        text,
        re.I,
    )
    return m.group(1) if m else None


def parse_product_block(name: str, text: str, category: str, source_url: str) -> Product | None:
    # Work only on the single product card. Remove title once so numbers in
    # product names (e.g. "0,204 kg") don't confuse quantity/price matching.
    body = text.replace(name, " ", 1)

    up, uu = unit_price(body)
    prices = _non_unit_prices(body)

    if not prices:
        return None

    # The CURRENT selling price is the last non-unit euro amount before
    # "Aggiungi". If a promotion is active, the previous/list price is the
    # preceding non-unit price.
    price = prices[-1]
    list_price = prices[-2] if len(prices) >= 2 and prices[-2] > price else None

    # Safety checks.
    if price <= 0 or price > 500:
        return None
    if up is not None and (up <= 0 or up > 1000):
        up, uu = None, None
    if list_price is not None and list_price > 1000:
        list_price = None

    is_variable = 1 if re.search(r"Venduto\s+a\s+Peso|SP\.?\s*(?:AL\s+)?KG", text, re.I) else 0

    # Fixed packs: prefer the quantity written in the product name, including
    # Piccolo's reversed style "GR 15" / "KG 1".
    # Variable-weight products: trust the card/default-weight metadata instead,
    # otherwise a title such as "... KG 1" could incorrectly force 1 kg.
    if is_variable:
        # For products sold by weight, the card's selected/default weight is
        # the quantity actually priced. Example: "PANE GRATTUGIATO KG 1"
        # is currently sold with a 500 g default at 2,55 €/kg.
        qv, qu = quantity(body)
        if qv is None:
            qv, qu = quantity(name)
    else:
        # Normal sealed packs: the pack size in the name remains preferred.
        # Exception: ambiguous catalogue names such as "X2 GR 400".  Here the
        # live selling card may contain a different current weight; use it
        # first so the quantity stays coherent with price and €/kg.
        if _ambiguous_reversed_multipack_name(name):
            qv, qu = quantity(body)
            if qv is None:
                qv, qu = quantity(name)
        else:
            qv, qu = quantity(name)
            if qv is None:
                qv, qu = quantity(body)

    # For FIXED packs, cross-check Piccolo's published unit price against the
    # package price and quantity. If the metadata is clearly impossible,
    # derive €/kg or €/L mathematically from the real pack price and size.
    if not is_variable:
        calc_up, calc_uu = _calculated_unit_price(price, qv, qu)
        if calc_up is not None and not _unit_prices_compatible(up, uu, calc_up, calc_uu):
            up, uu = calc_up, calc_uu

    discount = None
    if list_price and list_price > price:
        discount = round((1 - price / list_price) * 100, 1)

    return Product(
        supermarket="Piccolo",
        store_code=STORE_CODE,
        category=category,
        name=" ".join(name.split()),
        quantity_value=qv,
        quantity_unit=qu,
        price_eur=price,
        unit_price_eur=up,
        unit_price_unit=uu,
        list_price_eur=list_price,
        discount_pct=discount,
        variable_weight=is_variable,
        promo_until=promo_until(text),
        source_url=source_url,
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _find_single_product_card(h3):
    """
    Find the nearest ancestor that contains:
      - exactly this one H3 product title
      - at least one euro value
      - the 'Aggiungi' control

    The old parser stopped too early as soon as it saw '€ al kg', which meant
    it sometimes captured 8,13 €/kg as if it were the pack price and never
    reached the actual 1,30 € selling price.
    """
    node = h3
    fallback = None

    for _ in range(12):
        node = node.parent
        if node is None:
            break

        text = node.get_text("\n", strip=True)
        if "€" not in text:
            continue

        h3s = node.find_all("h3")
        if len(h3s) == 1 and h3s[0] is h3:
            fallback = node
            if re.search(r"\bAggiungi\b", text, re.I):
                return node

        # Once we have climbed into a container with multiple product H3s,
        # do not keep climbing: that would mix several product cards.
        if len(h3s) > 1:
            break

    return fallback


def parse_html(html: str, category: str, source_url: str) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []

    for h3 in soup.find_all("h3"):
        name = h3.get_text(" ", strip=True)
        if not name:
            continue

        card = _find_single_product_card(h3)
        if card is None:
            continue

        card_text = card.get_text("\n", strip=True)

        # Only parse complete cards. This prevents accepting a fragment that
        # contains €/kg but not the actual selling price.
        if not re.search(r"\bAggiungi\b", card_text, re.I):
            continue

        p = parse_product_block(name, card_text, category, source_url)
        if p:
            products.append(p)

    # Dedupe by category/name while preserving first appearance.
    seen = set()
    unique = []
    for p in products:
        key = (p.category, p.name.casefold())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if len(r.text) < 5000:
        raise RuntimeError(
            f"Pagina troppo piccola ({len(r.text)} byte): possibile blocco o errore"
        )
    return r.text


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str):
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(conn: sqlite3.Connection):
    conn.executescript(
        """
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
            list_price_eur REAL,
            discount_pct REAL,
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
        """
    )

    # Automatic migration for the prezzi.db already created by v1.
    _ensure_column(conn, "products_current", "list_price_eur", "REAL")
    _ensure_column(conn, "products_current", "discount_pct", "REAL")
    conn.commit()


def _product_is_sane(p: Product) -> bool:
    if p.price_eur <= 0 or p.price_eur > 500:
        return False

    # If both quantity and €/kg or €/L are available, compare expected pack
    # price to actual selling price. Use a broad tolerance because variable
    # weight products can use an indicative default weight.
    if (
        p.quantity_value is not None
        and p.quantity_unit is not None
        and p.unit_price_eur is not None
        and p.unit_price_unit in {"kg", "litro", "l", "lt"}
    ):
        q = p.quantity_value
        if p.quantity_unit in {"gr", "g"}:
            q /= 1000
        elif p.quantity_unit == "ml":
            q /= 1000
        elif p.quantity_unit == "cl":
            q /= 100

        compatible = (
            p.quantity_unit in {"kg", "gr", "g"} and p.unit_price_unit == "kg"
        ) or (
            p.quantity_unit in {"l", "lt", "ml", "cl"}
            and p.unit_price_unit in {"litro", "l", "lt"}
        )

        if compatible and q > 0:
            expected = q * p.unit_price_eur
            ratio = p.price_eur / expected if expected else 1
            if ratio < 0.45 or ratio > 2.20:
                return False

    return True


def save_category(conn: sqlite3.Connection, category: str, products: Iterable[Product]):
    products = [p for p in products if _product_is_sane(p)]

    old_count = conn.execute(
        """
        SELECT COUNT(*) FROM products_current
        WHERE supermarket=? AND store_code=? AND category=?
        """,
        ("Piccolo", STORE_CODE, category),
    ).fetchone()[0]

    # Guardrail: do not replace/update a category if extraction suddenly
    # collapses. This protects the previous good dataset.
    if old_count >= 10 and len(products) < max(3, int(old_count * 0.30)):
        raise RuntimeError(
            f"estrazione anomala: {len(products)} prodotti validi contro {old_count} precedenti"
        )
    if len(products) < 1:
        raise RuntimeError("nessun prodotto valido estratto")

    with conn:
        for p in products:
            previous = conn.execute(
                """
                SELECT price_eur FROM products_current
                WHERE supermarket=? AND store_code=? AND category=? AND name=?
                """,
                (p.supermarket, p.store_code, p.category, p.name),
            ).fetchone()

            if previous is None or abs(previous[0] - p.price_eur) > 1e-9:
                conn.execute(
                    """
                    INSERT INTO price_history
                    (supermarket,store_code,category,name,price_eur,checked_at,source_url)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        p.supermarket,
                        p.store_code,
                        p.category,
                        p.name,
                        p.price_eur,
                        p.checked_at,
                        p.source_url,
                    ),
                )

            conn.execute(
                """
                INSERT INTO products_current
                (
                    supermarket,store_code,category,name,
                    quantity_value,quantity_unit,
                    price_eur,unit_price_eur,unit_price_unit,
                    list_price_eur,discount_pct,
                    variable_weight,promo_until,source_url,checked_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(supermarket,store_code,category,name) DO UPDATE SET
                    quantity_value=excluded.quantity_value,
                    quantity_unit=excluded.quantity_unit,
                    price_eur=excluded.price_eur,
                    unit_price_eur=excluded.unit_price_eur,
                    unit_price_unit=excluded.unit_price_unit,
                    list_price_eur=excluded.list_price_eur,
                    discount_pct=excluded.discount_pct,
                    variable_weight=excluded.variable_weight,
                    promo_until=excluded.promo_until,
                    source_url=excluded.source_url,
                    checked_at=excluded.checked_at
                """,
                (
                    p.supermarket,
                    p.store_code,
                    p.category,
                    p.name,
                    p.quantity_value,
                    p.quantity_unit,
                    p.price_eur,
                    p.unit_price_eur,
                    p.unit_price_unit,
                    p.list_price_eur,
                    p.discount_pct,
                    p.variable_weight,
                    p.promo_until,
                    p.source_url,
                    p.checked_at,
                ),
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

            valid_count = len([p for p in products if _product_is_sane(p)])
            total += valid_count

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
                    None,
                ),
            )
            conn.commit()
            print(f"[OK] {category}: {valid_count} prodotti validi")

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
            print(f"[ERRORE] {category}: {exc}", file=sys.stderr)

    conn.close()
    print(f"Totale prodotti validi estratti: {total}; categorie fallite: {failures}")

    if failures:
        sys.exit(2)


if __name__ == "__main__":
    run()
