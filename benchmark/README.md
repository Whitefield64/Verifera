# Simulatore conversazioni

Il file `benchmark.jsonl` contiene 40 scenari con domande standalone e conversazioni multi-turno. Le risposte attese e le fonti obbligatorie sono una rubrica per la review del coding agent: non vengono inviate al backend e non influenzano le risposte.

`run.py` non assegna punteggi e non chiama un secondo LLM. Riproduce le conversazioni tramite lo stesso endpoint JSON usato dalla webapp e salva transcript ispezionabili in `benchmark/results/`.

## Comandi

```bash
python3 benchmark/run.py --validate-only
python3 benchmark/run.py --backend-url http://localhost:8000/api/chat
python3 benchmark/run.py --backend-url http://localhost:8000/api/chat --item q38
```

Se si seleziona un follow-up, il runner include automaticamente i turni precedenti dello stesso thread.

## Contratto condiviso con la webapp

Richiesta `POST`:

```json
{
  "message": "Domanda dell'utente",
  "history": [
    {"role": "user", "content": "Turno precedente"},
    {"role": "assistant", "content": "Risposta precedente"}
  ]
}
```

Risposta minima:

```json
{
  "answer": "Risposta mostrata nella chat",
  "citations": ["chem-prod-0006"],
  "path": "rag"
}
```

Il runner conserva l'intero oggetto di risposta senza rimuovere o trasformare campi. La webapp dovrà usare lo stesso endpoint e lo stesso payload: questa condivisione del contratto garantisce risposte identiche senza Playwright.

Ogni turno nel risultato contiene `request`, `response`, dati di trasporto e la rubrica `expected`. I risultati sono locali e gitignored. Il coding agent confronta `response` con `expected` e, quando necessario, apre i documenti indicati in `must_cite`.
