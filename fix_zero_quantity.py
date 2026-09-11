from pathlib import Path

# Trigger finale: corregge il falso match "00 KG" prima di "KG 1".
UPDATER = Path("updater.py")
TESTS = Path("test_parser.py")

src = UPDATER.read_text(encoding="utf-8")
old = '''    if m:\n        value = _float_it(m.group(1))\n        unit = m.group(2).lower()\n        if unit == "g":\n            unit = "gr"\n        elif unit == "l":\n            unit = "lt"\n        return value, unit\n\n    # Piccolo names often use reversed order: "ORIGANO GR 15", "OLIO LT 1".\n'''
new = '''    if m:\n        value = _float_it(m.group(1))\n        unit = m.group(2).lower()\n        if unit == "g":\n            unit = "gr"\n        elif unit == "l":\n            unit = "lt"\n        # Evita falsi positivi nei nomi come "FARINA TIPO 00 KG 1":\n        # "00 KG" non è una confezione, quindi lasciamo proseguire la ricerca\n        # fino alla forma inversa corretta "KG 1".\n        if value > 0:\n            return value, unit\n\n    # Piccolo names often use reversed order: "ORIGANO GR 15", "OLIO LT 1".\n'''

if 'Evita falsi positivi nei nomi come "FARINA TIPO 00 KG 1"' not in src:
    if old not in src:
        raise SystemExit("Blocco quantity standard non trovato")
    src = src.replace(old, new, 1)
    UPDATER.write_text(src, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
reg = '''\n# Regressione: "TIPO 00 KG 1" deve ignorare lo 00 e leggere KG 1.\nassert quantity("PICCOLO FARINA TIPO 00 KG 1") == (1.0, "kg")\n'''
if 'PICCOLO FARINA TIPO 00 KG 1' not in tests:
    tests += reg
    TESTS.write_text(tests, encoding="utf-8")

compile(UPDATER.read_text(encoding="utf-8"), "updater.py", "exec")
compile(TESTS.read_text(encoding="utf-8"), "test_parser.py", "exec")
print("Fix quantity zero applicato; sintassi valida")
