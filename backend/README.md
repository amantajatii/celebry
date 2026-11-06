# Celebry backend (Phase 5)

Run from `backend/` with Python 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Stop the server with Ctrl+C. Interactive OpenAPI docs: http://127.0.0.1:8000/docs.

Environment variables (set before starting):

- `CELEBRY_CORS_ORIGINS`: comma-separated allowed browser origins, default `http://localhost:3000,http://127.0.0.1:3000`. Use explicit origins.
- `CELEBRY_RATE_LIMIT`: positive integer, default 10 match requests per client IP per 60 seconds.

## API contract

`GET /api/health` returns HTTP 200 with service liveness and independent model readiness:

```json
{"status":"ok","matchingReady":false,"reason":"Matching is unavailable. Configure compatible local models and celebrity catalog."}
```

`GET /api/celebrities` returns `{"celebrities":[],"total":0}`. The list represents enrolled matching subjects, not editorial portraits. It stays empty until models and the matching catalog load successfully. Celebrity metadata schema includes id, name, imageUrl, sourceUrl, license, and attribution. No embeddings are returned.

`POST /api/match` accepts multipart fields `photo` (one file), `consent` (literal string `true`), and optional `collection` (`all`, `actors`, or `actresses`; default `all`). Unknown or repeated fields are rejected. Collection is chosen by the user, never inferred from their face. Example using your own consenting photo:

```bash
curl -i http://127.0.0.1:8000/api/match \
  -F 'consent=true' \
  -F 'photo=@selfie.jpg;type=image/jpeg'
```

After validation, configured inference returns the top five real cosine-ranked matches. Without compatible models and catalog, it returns HTTP 503 `MATCHING_NOT_READY`.

Errors have a consistent body:

```json
{"error":{"code":"CONSENT_REQUIRED","message":"Explicit consent is required before processing a photo."}}
```

| Status | Meaning |
| --- | --- |
| 400 | Malformed multipart or too many parts |
| 413 | Photo exceeds 10 MiB, request exceeds 10 MiB + 64 KiB, or image exceeds 20 megapixels |
| 415 | Unsupported request/image type or content does not match MIME |
| 422 | Invalid fields/consent/image; `NO_FACE`, `MULTIPLE_FACES`, or failed alignment/embedding |
| 429 | Per-process client limit reached; includes `Retry-After: 60` |
| 503 | Inference unavailable (`MATCHING_NOT_READY`) or occupied (`MATCHING_BUSY`) |
| 500 | Unexpected error with generic client message |

## Validation and privacy

Only multipart requests are accepted. The body is bounded while streaming, including requests without Content-Length, before the multipart parser runs. Limit parsing to one file and two small fields. Verify decoded JPEG/PNG/WebP content with Pillow, check dimensions, reject animation, and fully decode to detect corruption. Expensive decoding runs in a worker thread. Pillow validates and applies EXIF orientation; OpenCV converts to BGR; InsightFace detects and aligns faces and generates ArcFace embeddings.

No selfie, EXIF, filename, embedding, or image bytes are logged or stored by application code. Multipart files can spool to OS temporary storage; file handles are closed on success and validation failures, removing those temporary files. Raw bytes are released after the request. There is no database, persistent gallery, or account system.

Rate limiting is bounded to 1024 recent client entries and runs within one process; restarts reset it and oldest entries can be evicted. Before public deployment, enforce shared rate limits, body limits, connection timeouts, and concurrency limits at your ingress. Keep proxy headers disabled unless explicitly restricted to a trusted proxy. CORS is a browser policy, not authentication. Use HTTPS and review platform logging/retention separately.

## Verification

Tests generate real small images locally and exercise all three endpoints, JPEG/PNG/WebP acceptance, content validation, size/dimension limits, missing consent, malformed multipart, rate limiting, CORS, and temporary-file closure. They use FastAPI TestClient, not a deployed network service.

## Real inference setup

Install the optional ML dependencies into the same environment:

```bash
.venv/bin/pip install -r requirements-ml.txt
```

### Models and licensing

The code uses InsightFace 2.1 model-zoo ONNX adapters with explicit local model paths and CPU ONNX Runtime. It never downloads weights while serving requests. The official InsightFace code is MIT, but **its supplied pretrained weights are restricted to non-commercial research**. This prototype's downloaded buffalo_s weights are for local research testing; obtain appropriate commercial model rights or compatible licensed replacements before offering a consumer service. Image copyright permissions do not grant biometric, publicity, or endorsement rights.

Official model package and terms:

- https://github.com/deepinsight/insightface/releases/tag/v0.7
- https://github.com/deepinsight/insightface/tree/master/python-package#license

For non-commercial research, download `buffalo_s.zip` from the official release and put only `det_500m.onnx` and `w600k_mbf.onnx` in `backend/models/buffalo_s/`. Model files are ignored by Git. They were downloaded and tested in this workspace, but are not included in a fresh checkout.

Run the following from `backend/`:

```bash
export CELEBRY_DETECTION_MODEL="$PWD/models/buffalo_s/det_500m.onnx"
export CELEBRY_RECOGNITION_MODEL="$PWD/models/buffalo_s/w600k_mbf.onnx"
export CELEBRY_CATALOG="$PWD/data/celebrities.npz"

.venv/bin/python scripts/prepare_dataset.py
.venv/bin/python -m scripts.build_catalog data/hollywood/celebrities.json "$CELEBRY_CATALOG"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

The setup prepares 105 public Hollywood reference photos for 35 celebrities from Wikimedia Commons, with selections in `data/sources.json`. Existing verified downloads are reused; metadata is fetched in a batch and rate-limited responses are retried with backoff. It retrieves author, source URL, license, and license URL; refuses unreviewed license names; and records the downloaded image SHA-256. `data/hollywood-sources.json` records the sources used in this run. Image bytes and generated embeddings stay ignored by Git. Retain attribution and applicable share-alike terms when distributing references. Runtime public metadata includes the image source and credits.

For expansion, add reviewed source entries to `data/sources.json` or prepare a manifest with the same fields. Rebuild the catalog, then restart the API. Each subject must have a unique ID and every reference must contain exactly one detected face. Add extra licensed photos under `additionalFiles` in sources, or `references` in the prepared manifest. Duplicate reference bytes within a subject are rejected. Each photo retains its own source, license, attribution, and checksum. The current catalog uses three photos per subject. Curated `actors`/`actresses` labels come from written public biographical descriptions linked by `collectionSourceUrl` in `sources.json`; no demographic classifier runs. Older single-photo manifests remain supported, but unclassified subjects are excluded from either filtered collection. This is a tiny, nonrepresentative research catalog, not a validated resemblance benchmark.

### Pipeline and score definition

1. Validate the encoded image and decode it locally, applying EXIF orientation.
2. Convert RGB to OpenCV BGR and cap the longest edge at 1600 pixels.
3. Run SCRFD at 640×640, confidence threshold 0.5; reject zero or multiple detections.
4. Use five detected landmarks and InsightFace's ArcFace `norm_crop` alignment; generate a 512-dimensional embedding. No age, gender, or ethnicity inference runs.
5. L2-normalize each reference embedding; average the references for each celebrity and L2-normalize that mean to make the cached profile: `profile = normalize(mean(normalize(reference_i)))`. L2-normalize the query.
6. Apply the requested collection before selecting the top five. Compute `cosineSimilarity = dot(query, profile)` for unit vectors, clamp floating-point roundoff to [-1, 1], and rank descending. Ties preserve catalog order. Return five distinct celebrities with rank and public metadata, never embeddings.

Higher cosine indicates closer model embeddings. The raw value is **not a percentage, identity probability, or calibrated human resemblance score**. There is no minimum similarity threshold: results are relative to this small catalog, so even a poor match can rank first. The response explicitly identifies the metric and entertainment limitation. `catalogSize` is the size of the selected collection, not the entire catalog. A selected collection with fewer than five subjects returns 503 `COLLECTION_NOT_READY` and is never padded with another group. Unknown choices return 422 `INVALID_COLLECTION`. Multi-photo profiles no longer produce cosine 1.0 for an individual enrollment reference. Averaging is intended to reduce single-photo dependence; it has not been validated as improving resemblance for new users.

Catalogs contain metadata, a finite 512D vector per subject, and a fingerprint combining model-file SHA-256 inputs with the preprocessing version. Startup rejects incompatible models, broken vectors, duplicate IDs, or fewer than five references. Rebuild after changing models or preprocessing. Models/catalog load once per API process, and inference runs in a worker thread. A nonblocking lock limits model execution to one request per process and returns `MATCHING_BUSY` for concurrent inference.

Catalog publication is atomic. API uploads are never added to the catalog; no selfie or query embedding is retained. NumPy linear search is intentional for 35 subjects; pgvector is not needed at this size.

Successful response fields are documented in `/docs` (`MatchResponse`). Example structure only, with no invented score:

```text
collection: "all" | "actors" | "actresses"
catalogSize: selected collection size
matches: [{rank, celebrity: {id, name, collection, referenceCount, references: [per-photo credits], imageUrl, sourceUrl, license, licenseUrl, attribution}, cosineSimilarity}]
metric: "cosine_similarity"
notice: "Entertainment only. Similarity is not an identity probability."
```

### Testing real weights

With the environment variables above set:

```bash
.venv/bin/python -m pytest -q
CELEBRY_REAL_INFERENCE_TEST=1 .venv/bin/python -m pytest tests/test_inference.py::test_real_inference_api -q
```

The opt-in test uses real local weights and reference images through FastAPI TestClient: reference self-match ranks first, a blank image returns `NO_FACE`, and a two-face collage returns `MULTIPLE_FACES`. This validates plumbing and basic detection, not accuracy on unseen people. Default tests use clearly marked deterministic vector fixtures for ranking and error cases; they are never available to production inference. InsightFace currently emits an upstream scikit-image deprecation warning during alignment; it does not prevent inference in the pinned environment.

Source APIs verified against:

- https://github.com/deepinsight/insightface/blob/master/python-package/insightface/model_zoo/arcface_onnx.py
- https://github.com/deepinsight/insightface/blob/master/python-package/insightface/app/face_analysis.py

Frontend `/match` now calls these endpoints using `NEXT_PUBLIC_API_BASE_URL`. It sends a photo only after consent and renders real top-five results. See the root README for the Phase 4 setup and HTTP integration test.


## Phase 5 operational limits and public photos

- `CELEBRY_MAX_PROCESSING`: maximum simultaneous upload/decode/inference requests per process, default 2. Excess requests return 503 before reading an upload.
- `CELEBRY_UPLOAD_TIMEOUT_SECONDS`: total body-read deadline, default 30 seconds. Expiry returns HTTP 408 `UPLOAD_TIMEOUT`.
- `CELEBRY_INFERENCE_THREADS`: ONNX intra-op thread count, default 2; inter-op count is 1. Optional ONNX telemetry is disabled.
- `CELEBRY_REQUIRE_READY=true`: fail startup rather than serve without compatible models/catalog; enabled in Docker.
- `GET /api/ready`: 200 with enrolled count when ready, otherwise 503. `GET /api/health` remains liveness.
- `GET /media/celebrities/{id}.jpg`: public JPEG display thumbnail, max 500×700, with one-day public caching. Unknown IDs return 404. Only curated celebrity IDs are served; no file paths or user uploads are accepted.

Catalog generation now includes resized, EXIF-oriented JPEG display photos along with metadata and embeddings. Rebuild older catalogs before starting the new backend; missing display photos make readiness fail. No user photo or embedding is ever added to this archive. Image source/license metadata is retained and displayed by the frontend. Match responses also expose `catalogSize` to explain the ranking context, never embeddings or private photo data.

Production-style local Docker setup, headers, ingress limits, CI, verification results, and explicit limitations are documented in [Phase 5](../docs/phase-5.md). Run direct Uvicorn with `--no-proxy-headers`; the unpublished Docker API trusts only its container network where the gateway overwrites forwarding headers.
