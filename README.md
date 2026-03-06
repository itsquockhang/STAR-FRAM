## STARFRAM (React + Flask)

Simple web app for extracting NER with GLiNER. Supported models:
- `knowledgator/gliner-bi-base-v2.0` ([model card](https://huggingface.co/knowledgator/gliner-bi-base-v2.0))
- `urchade/gliner_multi-v2.1`

### Run backend (Flask)

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
python app.py
```

Backend: `http://127.0.0.1:8000`

### Run frontend (React Vite + MUI)

```bash
cd frontend
npm install
npm run dev
```

Frontend: open `http://127.0.0.1:5173`

The frontend proxies `/api/*` → `http://127.0.0.1:8000` in `frontend/vite.config.ts`.

