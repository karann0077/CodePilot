# CodePilot — AI Code Companion

> AI-powered developer assistant for learning repo internals, debugging, documentation, and patch generation.

## Deployment

### Backend (Render)

1. Create a new **Web Service** on [Render](https://render.com) pointing to the `backend/` directory.
2. Set the following environment variables in Render:

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/db` |
| `QDRANT_HOST` | Qdrant vector DB host | `localhost` |
| `QDRANT_PORT` | Qdrant vector DB port | `6333` |
| `LLM_MODE` | LLM selection mode (`hybrid` or `gemini_only`) | `gemini_only` |
| `GEMINI_API_KEY` | Gemini API key for Gemini-only mode | `AIza...` |
| `GEMINI_MODEL` | Gemini model to use | `gemini-1.5-flash` |
| `OPENROUTER_API_KEY` | OpenRouter API key for hybrid fallback | `sk-or-...` |
| `OPENROUTER_MODEL` | OpenRouter model for hybrid mode | `anthropic/claude-3.5-sonnet` |
| `OLLAMA_BASE_URL` | Ollama base URL for hybrid mode | `http://localhost:11434` |
| `MODEL_CACHE_DIR` | Directory for caching embedding models | `/tmp/codepilot_models` |
| `CORS_ORIGINS` | Allowed frontend origin(s), comma-separated | `https://your-app.vercel.app` |

> **Note:** If you set `CORS_ORIGINS=*`, all origins are allowed (useful for development). For production, set it to your Vercel frontend URL, e.g. `https://your-app.vercel.app`.


### Gemini-only mode (recommended for your use-case)

Set these env vars on backend:

- `LLM_MODE=gemini_only`
- `GEMINI_API_KEY=<your_gemini_key>`
- `GEMINI_MODEL=gemini-1.5-flash` (or another Gemini model)

In `gemini_only` mode, the backend bypasses Ollama and OpenRouter and calls Gemini directly.

### Frontend (Vercel)

1. Import the repository into [Vercel](https://vercel.com) and set the **Root Directory** to `frontend/`.
2. Set the following environment variable in Vercel:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://codepilot-cydq.onrender.com/api` |

> **Important:** The value must end with `/api` — no trailing slash.  
> Example: `https://codepilot-cydq.onrender.com/api` ✅  
> Wrong: `https://codepilot-cydq.onrender.com/` ❌  
> Wrong: `https://codepilot-cydq.onrender.com` ❌

If `VITE_API_URL` is **not** set, the frontend falls back to `/api` and relies on the Vercel proxy rewrite defined in `vercel.json` (which forwards `/api/*` to the Render backend automatically).

### Architecture

```
Frontend (Vercel)
  └─ VITE_API_URL=https://codepilot-cydq.onrender.com/api
     └─ axios baseURL → https://codepilot-cydq.onrender.com/api
        └─ api.post('/repos/connect') → https://codepilot-cydq.onrender.com/api/repos/connect ✅

Backend (Render)
  └─ app.include_router(repos.router, prefix="/api")
  └─ repos.router prefix="/repos"
  └─ Full path: /api/repos/connect ✅
```

## Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` automatically (see `vite.config.ts`).

