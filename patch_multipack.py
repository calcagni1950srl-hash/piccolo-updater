from pathlib import Path

# Trigger audit finale V8.1 dopo pulizia categorie legacy.
UPDATER = Path('updater.py')
TESTS = Path('test_parser.py')

src = UPDATER.read_text(encoding='utf-8')

# Multipack Piccolo: GR 100 X 5 -> 500 gr.
marker = '''    # Standard order: "15 gr", "1 kg".\n'''
patch = '''    # Reversed multipack used by Piccolo catalogue names:\n    # "GR 100 X 5" -> 500 gr, "GR 125 X 2" -> 250 gr.\n    mm = re.search(\n        r"\\b(kg|gr|g|ml|cl|lt|l|pz)\\s*(\\d+(?:[.,]\\d+)?)\\s*[xX]\\s*(\\d+)\\b",\n        text,\n        re.I,\n    )\n    if mm:\n        unit = mm.group(1).lower()\n        value = _float_it(mm.group(2)) * float(mm.group(3))\n        if unit == "g":\n            unit = "gr"\n        elif unit == "l":\n            unit = "lt"\n        return value, unit\n\n'''
if 'Reversed multipack used by Piccolo catalogue names' not in src:
    if marker not in src:
        raise SystemExit('Marker quantity() non trovato: patch interrotta')
    src = src.replace(marker, patch + marker, 1)

legacy_code = '''\nLEGACY_CATEGORIES = {"verdura", "legumi", "pane", "pasta"}\n\ndef cleanup_legacy_categories(conn: sqlite3.Connection) -> int:\n    now = datetime.now(timezone.utc).isoformat(timespec="seconds")\n    placeholders = ",".join("?" for _ in LEGACY_CATEGORIES)\n    params = ["Piccolo", STORE_CODE, *sorted(LEGACY_CATEGORIES)]\n    rows = conn.execute(\n        f"""\n        SELECT category,name,price_eur,source_url\n        FROM products_current\n        WHERE supermarket=? AND store_code=?\n          AND category IN ({placeholders})\n        """,\n        params,\n    ).fetchall()\n    if not rows:\n        return 0\n    with conn:\n        for category, name, price, source_url in rows:\n            conn.execute(\n                """\n                INSERT INTO products_archive\n                (supermarket,store_code,category,name,removed_at,last_price_eur,source_url,reason)\n                VALUES (?,?,?,?,?,?,?,?)\n                """,\n                ("Piccolo", STORE_CODE, category, name, now, price, source_url,\n                 "CATEGORIA_LEGACY_SOSTITUITA"),\n            )\n        conn.execute(\n            f"""\n            DELETE FROM products_current\n            WHERE supermarket=? AND store_code=?\n              AND category IN ({placeholders})\n            """,\n            params,\n        )\n    return len(rows)\n\n'''
run_marker = '\ndef run():\n'
if 'def cleanup_legacy_categories(' not in src:
    if run_marker not in src:
        raise SystemExit('Marker run() non trovato: patch interrotta')
    src = src.replace(run_marker, legacy_code + run_marker, 1)

close_marker = '''    conn.close()\n    print(f"Totale prodotti certificati: {total}; categorie fallite: {failures}")\n'''
close_patch = '''    if failures == 0:\n        removed_legacy = cleanup_legacy_categories(conn)\n        print(f"Categorie legacy archiviate/rimosse: {removed_legacy}")\n\n    conn.close()\n    print(f"Totale prodotti certificati: {total}; categorie fallite: {failures}")\n'''
if 'removed_legacy = cleanup_legacy_categories(conn)' not in src:
    if close_marker not in src:
        raise SystemExit('Marker chiusura run non trovato: patch interrotta')
    src = src.replace(close_marker, close_patch, 1)

UPDATER.write_text(src, encoding='utf-8')

t = TESTS.read_text(encoding='utf-8')
reg = '''\n# Regressione multipack Piccolo: ordine UNITA QUANTITA X PEZZI\nassert quantity("MARRANDINO MOZZARELLA BUFALA GR 100 X 5") == (500.0, "gr")\nassert quantity("LA PERLA MOZZARELLA DI BUFALA GR 125 X 2") == (250.0, "gr")\n'''
if 'MARRANDINO MOZZARELLA BUFALA GR 100 X 5' not in t:
    t += reg
    TESTS.write_text(t, encoding='utf-8')

compile(UPDATER.read_text(encoding='utf-8'), 'updater.py', 'exec')
compile(TESTS.read_text(encoding='utf-8'), 'test_parser.py', 'exec')
print('Patch Piccolo V8.1 applicata: multipack + pulizia legacy; sintassi valida')
