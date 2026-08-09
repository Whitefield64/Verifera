# Frontend — mockup split-view (fase 2)

Webapp Next.js: chat a sinistra, viewer documenti a destra. Click su una citazione →
il viewer apre l'originale, scrolla ed evidenzia il passaggio (overlay sui bbox per i
PDF, ancore testuali + CSS Custom Highlight API per HTML/DOCX).

## Avvio

Backend prima (`docker compose up -d` dalla root), poi:

```bash
npm install
npm run dev        # http://localhost:3000
```

L'URL dell'API si configura con `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`,
vedi `.env.example`). Il worker di pdf.js viene copiato in `public/` da `predev`/`prebuild`.

## Test e lint

```bash
npm test           # vitest: matcher delle ancore testuali (lib/anchors.ts)
npm run lint
npm run build      # include il type-check; pronto per deploy Vercel
```

## Struttura

- `app/page.tsx` — stato split-view: messaggi, tab documenti, target di evidenziazione
- `components/Chat.tsx` — chat con streaming SSE e chip citazioni (flag `verified`)
- `components/PdfViewer.tsx` — react-pdf, overlay multi-rect scalati dai punti PDF
- `components/HtmlViewer.tsx` — originale in `<iframe sandbox srcdoc>` (rende fedele via `<base href>`; mammoth per DOCX); highlight scriptato nel frame same-origin
- `lib/anchors.ts` — matching testuale normalizzato (specchia `backend/app/citations.py`)
- `lib/api.ts` — tipi del contratto di citazione + client SSE
