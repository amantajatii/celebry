# Celebry

Find your famous twin. Celebry is an entertainment-focused Hollywood look-alike finder, with a Next.js frontend and independently deployed FastAPI inference backend. Phases 1–5 are implemented for local use: the dedicated `/match` page now sends consenting uploads to real inference, renders five cosine-ranked results, and handles loading and errors. There is no fallback demo or random matching.

## Run locally

Use Node 22.18+ (for native TypeScript unit tests) and Python 3.12. Install and prepare the backend following [backend/README.md](backend/README.md), including the model licensing restrictions.

Terminal 1, from `backend/`, after preparing models and catalog:

```bash
export CELEBRY_DETECTION_MODEL="$PWD/models/buffalo_s/det_500m.onnx"
export CELEBRY_RECOGNITION_MODEL="$PWD/models/buffalo_s/w600k_mbf.onnx"
export CELEBRY_CATALOG="$PWD/data/celebrities.npz"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Terminal 2, from the repository root:

```bash
npm install
npm run dev
```

Open http://localhost:3000, then select “Find my twin” to open `/match`. Stop each server with Ctrl+C in its terminal. Without a ready backend, the UI displays an actionable error and never invents a match.

The frontend uses `NEXT_PUBLIC_API_BASE_URL`, default `http://127.0.0.1:8000`. Copy `.env.example` to `.env.local` if needed. This public URL is embedded at Next.js build time; set it before `npm run build`. Configure `CELEBRY_CORS_ORIGINS` on the backend for your frontend's exact origin. Defaults accept localhost:3000 and 127.0.0.1:3000. When testing from another device, use reachable LAN addresses for both services; loopback URLs refer to that device itself.

## Structure

- `app/`: App Router pages, metadata, global styles.
- `components/experience.tsx`: landing page and privacy information.
- `components/match-experience.tsx`: consent, upload, local preview, request lifecycle, real results, and text sharing.
- `lib/match-api.ts`: typed multipart API client and runtime response validation.
- `backend/app/`: FastAPI upload boundary, InsightFace/ArcFace inference, and cosine ranking.
- `backend/scripts/`: Commons reference preparation and precomputed catalog generation.
- `tests/` and `backend/tests/`: frontend contract/client tests and backend unit/integration tests.

## Matching and privacy

The browser previews JPEG, PNG, and WebP files up to 10 MiB using a temporary object URL. Only clicking analysis after checking consent sends the original file to the backend. A new photo resets consent. Uploads and query embeddings are not retained or enrolled. There are no accounts, analytics uploads, or embedding fields in frontend responses. Result thumbnails are served locally by the backend; only the editorial landing photos use Wikimedia through Next.js image optimization. Public photos may be cached. Selfies and query embeddings are never added to that image cache.

Results display the top five celebrities and **raw cosine similarity in [-1, 1]**, not a percentage or identity probability. Ranking is relative to a 35-celebrity Hollywood catalog; resemblance quality on new users has not been benchmarked. Photo credits and applicable licenses are included with results. Research weights are not cleared for commercial deployment.

Requests time out after 60 seconds and may be cancelled. Cancel aborts the browser request and prevents stale results from rendering; server-side work already started may still finish. Photo previews are revoked on replacement/unmount, and results stay in memory only. “Share my results” opens native text sharing where supported; otherwise it copies result text. It does not upload the selfie or create a public results URL.

## Checks

```bash
npm test
npm run build
cd backend
.venv/bin/python -m pytest -q
```

With the backend running and real local models/catalog prepared, run the opt-in HTTP test from the repository root:

```bash
CELEBRY_LIVE_API_TEST=1 npm test
```

It uses a public celebrity reference through the actual frontend API client, checks real top-five ranking, cache controls, and browser CORS. It does not exercise browser rendering. A native Chrome check also verified empty-upload validation, required consent, public-reference upload, and rendering of five real results. Desktop and mobile Chromium tests now cover layout, cancellation of slow requests, native share payloads, and clipboard fallback. Backend real-model detection tests are documented separately. Phase 5 adds local Docker verification, shared gateway rate limiting, operational limits, self-hosted fonts, and browser/accessibility/performance tests; no public deployment has been performed. See [Phase 5 verification](docs/phase-5.md).

## Expanded collection and local readiness

The catalog contains 35 real Hollywood celebrities, including Margot Robbie, Emma Watson, Scarlett Johansson, Tom Holland, Henry Cavill, Chris Evans, Chris Hemsworth, Ryan Reynolds, Leonardo DiCaprio, and Pedro Pascal. Source and licensing records are in `backend/data/hollywood-sources.json`. Rebuild the catalog after changing sources or upgrading from the older catalog without display thumbnails.

Optional local production stack: `docker compose up --build -d`, then open http://localhost:8080. Stop with `docker compose down`. This is local-only by default. See [docs/phase-5.md](docs/phase-5.md) for repeatable checks, limits, and remaining public-release requirements.
