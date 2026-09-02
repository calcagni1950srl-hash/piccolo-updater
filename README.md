# Piccolo Price Updater – prova tecnica

Questo prototipo legge automaticamente alcune categorie pubbliche di Piccolo Supermercati e salva i dati in SQLite (`prezzi.db`).

Campi principali: supermercato, codice punto/catalogo, categoria, prodotto, quantità, unità, prezzo, prezzo unitario, peso variabile, scadenza promo, fonte e data verifica.

## Avvio locale

```bash
pip install -r requirements.txt
python updater.py
```

## Test del parser

```bash
python test_parser.py
```

## Aggiornamento automatico

Il workflow `.github/workflows/update-piccolo.yml` esegue l'updater ogni giorno e committa `prezzi.db` solo se l'estrazione termina correttamente.

### Protezioni già previste

- timeout HTTP;
- rifiuto di pagine anormalmente piccole;
- rifiuto di prezzi evidentemente errati;
- non cancella una categoria se il numero estratto crolla improvvisamente;
- storico dei cambi prezzo;
- registro aggiornamenti/errori.

> Nota: il test di rete va eseguito su GitHub Actions o su una macchina con accesso Internet. L'ambiente di esecuzione ChatGPT usato per creare il prototipo non consente richieste HTTP dirette esterne, quindi qui è stato validato il parser su una fixture locale coerente con la struttura pubblicamente osservata.
