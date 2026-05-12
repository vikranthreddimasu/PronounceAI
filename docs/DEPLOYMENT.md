# Deployment

This project should be deployed as two services:

- **Frontend:** Next.js on Vercel free tier.
- **Backend:** FastAPI/Python ML service as a long-running Daytona container or workspace.

Do not deploy the backend as Vercel serverless functions. It loads local audio/ML models, uses PyTorch, and benefits from a persistent process plus model/cache directories.

## 1. Backend on Daytona

Build from the backend directory:

```bash
cd backend
docker build -t pronounceai-backend .
```

Run locally as a smoke test:

```bash
docker run --rm -p 8000:8000 --env-file .env.production.example pronounceai-backend
```

Then check:

```bash
curl http://127.0.0.1:8000/health
```

For Daytona, create a service/workspace from `backend/Dockerfile`, expose port `8000`, and set the environment variables from `backend/.env.production.example`.

Use these conservative production defaults first:

```env
DEVICE=cpu
PREWARM_MODELS=0
SCORE_ASR_MODE=off
SCORE_INCLUDE_FORMANTS=0
SCORE_WAVLM_MODE=auto
FORCE_WAVLM_ENGINE=0
PRELOAD_ACCENT_CONVERTER=0
```

After Vercel gives you the frontend URL, update the backend:

```env
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

### Local model files

The Docker image includes only runtime checkpoint files when they exist locally:

- `backend/checkpoints/phoneme_scorer_best.pt`
- `backend/checkpoints/assessment_head_best.pt`
- `backend/checkpoints/accent_centroids.pt`

The base Hugging Face models are downloaded by the backend at startup and cached under `/app/.cache/huggingface`.

If you build from a clean Git checkout, these `.pt` files will not be present because they are intentionally gitignored. That is okay: the backend falls back to raw/deterministic scoring when optional checkpoints are absent. If you want the learned heads in production, copy those files into `backend/checkpoints/` before building the Daytona image, or upload/mount them into the same paths in the Daytona workspace.

## 2. Frontend on Vercel

Create a Vercel project from this repo with:

- Project name: `pronounceai`
- Root directory: `frontend`
- Build command: `npm run build`
- Install command: `npm install`

That should give the app a simple free Vercel domain:

```text
https://pronounceai.vercel.app
```

If `pronounceai` is already taken in Vercel, use the first available simple fallback:

```text
pronounce-ai
pronounceai-demo
pronounceai-final
```

Avoid the auto-generated deployment URL for final submission; use the stable project domain instead.

If deploying from the Vercel CLI, link with the project name explicitly:

```bash
cd frontend
vercel link --yes --project pronounceai
vercel deploy --prod --project pronounceai
```

Set this env var:

```env
NEXT_PUBLIC_API_URL=https://your-daytona-backend-url
```

Keep this unset for the real backend:

```env
NEXT_PUBLIC_USE_MOCK=
```

If the backend is down near submission time, set:

```env
NEXT_PUBLIC_USE_MOCK=1
```

The app will use its built-in demo scoring and browser speech fallback, which keeps the public demo usable.

## 3. Submission-day checklist

1. Open the Daytona backend `/health` URL and confirm it returns `{"status":"ok"}`.
2. Open the stable Vercel project URL, ideally `https://pronounceai.vercel.app`.
3. Record a short phrase in Practice.
4. Confirm the browser can call `POST /api/score`; if not, check `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL`.
5. Try Voice Lab only after Practice works. Voice cloning is the heaviest flow and may be unavailable on a small CPU instance.
6. If the backend becomes unstable, set `NEXT_PUBLIC_USE_MOCK=1` in Vercel and redeploy.
