# Celebry

**Find Your Famous Twin.**

Upload a selfie, choose a Hollywood collection, and discover your five closest celebrity matches. Celebry combines a responsive Next.js interface with a separate Python service that detects faces, generates ArcFace embeddings, and ranks real cosine similarity scores.

The app runs locally without an account. Its catalog contains **35 Hollywood celebrities and 105 licensed reference photos**, with three photos per celebrity. Matching requires local models and a prepared catalog; unavailable inference produces an error rather than sample results.

## Features

- Dedicated `/match` page with drag-and-drop upload, file browsing, preview, replacement, and explicit consent.
- JPEG, PNG, and WebP support, up to 10 MiB and 20 megapixels.
- Manual collection selection: All celebrities, Actors (17), or Actresses (18).
- Face detection and alignment, with feedback for missing or multiple faces.
- Ranked top-five results, selfie comparison, raw similarity scores, and per-photo credits.
- Loading, cancellation, retry, and text sharing through native sharing or the clipboard.
- Responsive layouts, keyboard navigation, reduced-motion support, and automated accessibility checks.
- Upload limits, rate limiting, readiness checks, and an optional local Docker stack.

Collection selection controls the comparison pool. Celebry does not infer the user's gender from their photo.

## Stack and architecture

| Layer | Implementation |
| --- | --- |
| Frontend | Next.js App Router, React, TypeScript, Tailwind CSS, Lucide icons |
| API | Python 3.12, FastAPI, Uvicorn |
| Computer vision | OpenCV, InsightFace, SCRFD detection, ArcFace embeddings |
| Inference and search | ONNX Runtime on CPU, NumPy cosine ranking |
| Catalog | Precomputed local NumPy archive with metadata and display thumbnails |
| Testing | pytest, Node test runner, Playwright, axe |
| Optional local packaging | Docker Compose and Nginx |

The frontend and inference service run independently and communicate over HTTP. The current catalog uses a linear NumPy search; PostgreSQL and pgvector are not required or implemented for this MVP. Uploaded selfies are never added to the catalog.

```text
Browser /match
    → consent + multipart upload + selected collection
FastAPI
    → validate image → detect one face → align → generate embedding
    → compare with precomputed celebrity profiles → rank within collection
Browser
    ← five matches + raw scores + public photo credits
```

## Getting started

Requirements: Node.js 22.18+, npm, Python 3.12, and compatible local ONNX model files. Dataset preparation needs an internet connection to Wikimedia Commons. Docker is optional.

### 1. Clone and install

```bash
git clone https://github.com/amantajatii/celebry.git
cd celebry
npm ci
cp .env.example .env.local

cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -r requirements-ml.txt
```

The commands below use macOS/Linux paths. On Windows, use the corresponding executables under `.venv/Scripts/`.

### 2. Prepare the models

For non-commercial research, obtain `buffalo_s.zip` from the [official InsightFace release](https://github.com/deepinsight/insightface/releases/tag/v0.7). Place these files inside `backend/`:

```text
models/buffalo_s/
├── det_500m.onnx
└── w600k_mbf.onnx
```

InsightFace's supplied pretrained weights are restricted to non-commercial research. A public commercial service requires appropriately licensed weights. See the [backend model setup and terms](backend/README.md#models-and-licensing).

Model weights, downloaded reference images, and generated catalogs are excluded from Git. A fresh clone must prepare them before real matching can run. The serving API never downloads model weights automatically.

### 3. Build the celebrity catalog

Run from `backend/`:

```bash
export CELEBRY_DETECTION_MODEL="$PWD/models/buffalo_s/det_500m.onnx"
export CELEBRY_RECOGNITION_MODEL="$PWD/models/buffalo_s/w600k_mbf.onnx"
export CELEBRY_CATALOG="$PWD/data/celebrities.npz"

.venv/bin/python scripts/prepare_dataset.py
.venv/bin/python -m scripts.build_catalog data/hollywood/celebrities.json "$CELEBRY_CATALOG"
```

Preparation downloads curated Commons photos and records their sources, licenses, authors, and checksums. The builder validates each image, requires exactly one face per reference, and precomputes a profile for each celebrity. It replaces the catalog only after a successful build.

### 4. Start the backend

In the same terminal, with those environment variables still set:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Check [readiness](http://127.0.0.1:8000/api/ready) or open the [interactive API documentation](http://127.0.0.1:8000/docs).

### 5. Start the frontend

In a second terminal, from the repository root:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) or go directly to [/match](http://localhost:3000/match). Choose a collection, upload one clear face, give consent, and start analysis. Stop each server with Ctrl+C in its terminal.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | API URL reachable by the browser; set before building the frontend | `http://127.0.0.1:8000` |
| `CELEBRY_DETECTION_MODEL` | Path to the detection ONNX file | Required for matching |
| `CELEBRY_RECOGNITION_MODEL` | Path to the recognition ONNX file | Required for matching |
| `CELEBRY_CATALOG` | Path to the generated catalog | Required for matching |
| `CELEBRY_CORS_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `CELEBRY_RATE_LIMIT` | Match attempts per client IP per 60 seconds, per API process | `10` |
| `CELEBRY_MAX_PROCESSING` | Concurrent admitted upload/processing requests per process | `2` |
| `CELEBRY_UPLOAD_TIMEOUT_SECONDS` | Total upload body-read deadline | `30` |
| `CELEBRY_INFERENCE_THREADS` | ONNX intra-op CPU threads | `2` |
| `CELEBRY_REQUIRE_READY` | Refuse startup without compatible models/catalog | Disabled; enabled in Docker |

Export backend variables before starting Uvicorn. The frontend reads its public configuration from `.env.local`. When accessing the app from another device, configure reachable LAN addresses for both services and the exact frontend CORS origin; loopback addresses point to that device itself.

## How similarity is calculated

1. Validate and decode the image, apply EXIF orientation, and convert it to OpenCV BGR.
2. Detect exactly one face with SCRFD and align it using five facial landmarks.
3. Generate a 512-dimensional ArcFace embedding and L2-normalize it.
4. Compare it with each eligible celebrity's precomputed profile.
5. Return the five highest cosine similarities in the selected collection.

For reference embeddings `r₁ … rₙ` and query embedding `q`:

```text
normalize(v) = v / ||v||₂
profile = normalize(mean(normalize(r₁), ..., normalize(rₙ)))
score = dot(normalize(q), profile)
```

Scores range from -1 to 1. Higher scores indicate closer model embeddings. The displayed value is not a percentage, an identity probability, or a calibrated measure of human-perceived resemblance.

Results are relative to a small catalog. There is no validated minimum similarity cutoff, so the highest-ranked result may still be a weak look-alike. Multiple reference photos reduce dependence on one photo, but resemblance accuracy on unseen users has not been measured. Celebry is for entertainment, not identity verification.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/match` | Analyze a consenting upload and return five ranked matches |
| `GET` | `/api/celebrities` | List enrolled celebrity metadata |
| `GET` | `/api/health` | Check liveness and report matching availability |
| `GET` | `/api/ready` | Return 200 when inference is ready, otherwise 503 |
| `GET` | `/media/celebrities/{id}.jpg` | Serve a curated public display thumbnail |

Example using a photo you consent to analyze:

```bash
curl http://127.0.0.1:8000/api/match \
  -F 'photo=@selfie.jpg;type=image/jpeg' \
  -F 'consent=true' \
  -F 'collection=actors'
```

`collection` accepts `all`, `actors`, or `actresses`, and defaults to `all`. Responses include `collection`, `catalogSize`, `metric`, `notice`, and five ranked matches with celebrity metadata and `cosineSimilarity`. Embeddings are never returned.

Errors use `{"error":{"code":"...","message":"..."}}`. Common cases include invalid images or face counts (422), upload limits (413), rate limits (429), and unavailable or busy inference (503). See the [backend API contract](backend/README.md#api-contract) for details.

## Privacy

Analysis requires explicit consent, and changing the photo resets consent. The browser uses a temporary local preview URL; the API processes uploads without enrolling them or permanently storing selfies or query embeddings. Multipart uploads may spool to OS temporary storage; the backend closes those files after processing or validation failure.

The app has no accounts or persistent result history. Results stay in browser memory. Sharing sends or copies result text; it does not upload the selfie or generate a public results page. Cancellation prevents stale results from rendering, although server inference already running may finish.

Celebrity thumbnails are served by the backend. Editorial landing photos use Wikimedia through Next.js image optimization. Public celebrity photos may be cached; private uploads and match responses are not added to that image cache. Hosting and proxy retention policies require separate review before a public release.

## Tests

From the repository root:

```bash
npm test
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

From `backend/`:

```bash
.venv/bin/python -m pytest -q

# Requires the model/catalog environment variables and prepared references.
CELEBRY_REAL_INFERENCE_TEST=1 .venv/bin/python -m pytest -q
```

With the real backend running, from the repository root:

```bash
CELEBRY_LIVE_API_TEST=1 npm test

# Also start the frontend on localhost:3000 before this command.
CELEBRY_BROWSER_BASE_URL=http://localhost:3000 CELEBRY_REAL_BROWSER_TEST=1 npm run test:e2e
```

The recorded multi-photo verification passed 46 backend tests, 7 frontend/client tests, and 26 desktop/mobile Chromium browser tests. These include real local inference using public celebrity photos. They establish pipeline and interface behavior, not accuracy on unseen users. See [matching verification](docs/matching-improvements.md) and [earlier local release checks](docs/phase-5.md) for scope and limitations.

## Project structure

```text
app/                         App Router pages and global styles
components/                  Landing page and upload/results experience
lib/match-api.ts             Typed API client and response validation
backend/app/                 API, image validation, inference, and ranking
backend/scripts/             Reference preparation and catalog generation
backend/data/sources.json    Curated celebrities and reference selections
backend/data/hollywood-sources.json
                             Recorded source, license, and checksum metadata
backend/tests/               Backend unit and integration tests
tests/                       Client tests and browser tests
deploy/                      Optional Nginx configuration
docs/                        Verification records and implementation notes
```

To expand the catalog, add reviewed references to `backend/data/sources.json`, prepare the dataset, rebuild the catalog, and restart the API. Preserve per-photo attribution and license terms. A filtered collection needs at least five enrolled celebrities; otherwise the API returns `COLLECTION_NOT_READY` rather than mixing collections.

## Optional Docker setup

Prepare the local model files and catalog first, then run from the repository root:

```bash
docker compose up --build -d
```

Open [http://localhost:8080](http://localhost:8080). Stop the stack with:

```bash
docker compose down
```

The gateway binds to loopback by default. This is a local runtime package; no public deployment is included. Rebuild images after changing the catalog or application. Model-bearing images inherit the model distribution restrictions. See [local runtime and deployment boundaries](docs/phase-5.md).

## Image and model credits

The reference manifest records each photo's Commons source, attribution, license, license URL where available, and checksum. Result credits expose every reference used for a matched celebrity. Retain attribution and applicable share-alike terms when redistributing images.

InsightFace code and supplied model weights have different licensing terms. Review the [upstream terms](https://github.com/deepinsight/insightface/tree/master/python-package#license) before use. Reference-image licenses do not imply celebrity endorsement or automatically resolve publicity and biometric rights.
