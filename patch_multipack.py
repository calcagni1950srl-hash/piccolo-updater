from pathlib import Path

UPDATER = Path('updater.py')
TESTS = Path('test_parser.py')

src = UPDATER.read_text(encoding='utf-8')
marker = '''    # Standard order: "15 gr", "1 kg".\n'''
patch = '''    # Reversed multipack used by Piccolo catalogue names:\n    # "GR 100 X 5" -> 500 gr, "GR 125 X 2" -> 250 gr.\n    mm = re.search(\n        r"\\b(kg|gr|g|ml|cl|lt|l|pz)\\s*(\\d+(?:[.,]\\d+)?)\\s*[xX]\\s*(\\d+)\\b",\n        text,\n        re.I,\n    )\n    if mm:\n        unit = mm.group(1).lower()\n        value = _float_it(mm.group(2)) * float(mm.group(3))\n        if unit == "g":\n            unit = "gr"\n        elif unit == "l":\n            unit = "lt"\n        return value, unit\n\n'''

if 'Reversed multipack used by Piccolo catalogue names' not in src:
    if marker not in src:
        raise SystemExit('Marker quantity() non trovato: patch interrotta')
    src = src.replace(marker, patch + marker, 1)
    UPDATER.write_text(src, encoding='utf-8')

# Aggiunge test di regressione solo se non già presenti.
t = TESTS.read_text(encoding='utf-8')
reg = '''\n# Regressione multipack Piccolo: ordine UNITA QUANTITA X PEZZI\nassert quantity("MARRANDINO MOZZARELLA BUFALA GR 100 X 5") == (500.0, "gr")\nassert quantity("LA PERLA MOZZARELLA DI BUFALA GR 125 X 2") == (250.0, "gr")\n'''
if 'MARRANDINO MOZZARELLA BUFALA GR 100 X 5' not in t:
    t += reg
    TESTS.write_text(t, encoding='utf-8')

# Controllo sintattico senza importare dipendenze esterne.
compile(UPDATER.read_text(encoding='utf-8'), 'updater.py', 'exec')
compile(TESTS.read_text(encoding='utf-8'), 'test_parser.py', 'exec')
print('Patch multipack V8 applicata; sintassi valida')
