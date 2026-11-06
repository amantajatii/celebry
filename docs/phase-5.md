# Phase 5: local release verification

Scope: strengthen the app and verify it locally; no VPS or public-domain deployment is requested. The collection grows from 5 to **35 Hollywood celebrities**. See `backend/data/sources.json` for curated file selections and `backend/data/hollywood-sources.json` for source/license/checksum records.

## Implemented

- Upload admission limits cover body reading, decoding, and inference; excess concurrent requests receive `MATCHING_BUSY` instead of accumulating in memory.
- A configurable total upload deadline and declared/streamed byte caps reject slow and oversized requests. Tests verify cleanup even when uploads spool to disk.
- `/api/ready` returns 503 if inference is unavailable. Docker refuses startup without compatible local models and catalog. Liveness remains separate.
- ONNX CPU threads are capped, and optional runtime telemetry is disabled. Models load once per process.
- Nginx uses shared-memory request and connection zones across its workers, overwrites client-supplied forwarding headers, and exposes only a loopback gateway by default. Backend/front-end container ports are not published.
- Frontend CSP, frame protection, MIME protection, referrer policy, and permissions policy are configured. Self-hosted licensed fonts remove the Google Fonts request. Public landing images use Next.js image optimization.
- Display thumbnails for all enrolled celebrities are precomputed in the catalog and served by the backend at `/media/celebrities/{id}.jpg`. These public photos may be cached; selfies, query embeddings, and match responses may not. Images have credits in the results.
- Skip navigation, keyboard focus after results, reduced-motion behavior, mobile layout, larger icon hit targets, and text contrast are verified or improved.
- Browser tests cover required consent, file validation, errors, cancellation/stale responses, ranking, reset, share API payload, clipboard fallback, and automated accessibility checks. Test share APIs are intercepted, so no social post is actually sent.
- Docker images run application processes as unprivileged users with read-only filesystems and bounded resources. Only Nginx's master uses the image's normal root startup to configure workers/TLS. Runtime upload/cache directories are temporary.
- CI runs frontend tests/build/browser checks and backend tests without auto-downloading restricted model weights.

## Local Docker use (optional)

Prepare the real models and catalog as described in `backend/README.md`. Docker packages those local artifacts into a private local image; do not publish model-bearing images without appropriate rights.

```bash
docker compose build
docker compose up -d
```

Open http://localhost:8080/match. The frontend and API share one origin, so no browser-facing backend port or public API URL is needed. Docker's API readiness check requires the catalog to load. Backend request logs include only method, a fixed route name, status, and duration; they omit IP, filename, image, consent body, and embedding. Nginx access logs are disabled. Its diagnostic error log can still include a client network address for failures; apply an appropriate host log-retention policy if this optional stack is used.

Stop the optional local stack:

```bash
docker compose down
```

If you change Nginx configuration while it is running, validate and reload it:

```bash
docker compose exec gateway nginx -t
docker compose exec gateway nginx -s reload
```

The backend trusts forwarded headers only inside this unpublished Docker network. Do not expose its port with this proxy configuration. Direct local Uvicorn continues using `--no-proxy-headers`.

## Repeat verification

```bash
npm test
npm run typecheck
npm run build
npm run test:e2e
```

The browser runner uses `.next-e2e` on port 3100 so it does not conflict with the app on port 3000. Default tests use explicit response fixtures. For real inference and production-only loading measurements against the local Docker stack:

```bash
CELEBRY_BROWSER_BASE_URL=http://localhost:8080 \
CELEBRY_REAL_BROWSER_TEST=1 CELEBRY_PERFORMANCE_TEST=1 npm run test:e2e
```

The real test uploads only the public Zendaya reference. Backend opt-in tests also encode all 35 enrolled references, check self-match ranking, verify public thumbnail decoding, and exercise no-face and multiple-face rejection. This is a pipeline sanity check, not an accuracy evaluation on new users.

## Boundaries

The gateway's shared limiter covers one gateway instance and its workers, not multiple independent ingress servers. The backend fallback limiter remains per process. Admission caps and upload deadlines do not forcefully interrupt a native inference call already executing; cancellation ignores its eventual result in the browser. Resource and upstream time limits still apply.

The static App Router CSP permits inline bootstrap scripts and styles; it blocks external scripts, framing, objects, and non-allowlisted connections. A strict nonce policy would require dynamic rendering. Automated axe checks do not prove complete accessibility, mobile Chromium emulation is not a physical iPhone/Safari test, and browser tests verify native share invocation rather than OS destination delivery.

Lab performance measurements are local, unthrottled, and can benefit from the image server cache. They are not field Core Web Vitals or a measurement of real-user INP. Production deployment, public DNS, and public TLS issuance are deliberately excluded at the user's request.

`compose.tls.yaml` and the TLS listener are optional templates for a later deployment with a valid `fullchain.pem` and `privkey.pem` under `CELEBRY_CERT_DIR`; their Compose schema is validated, but no certificate has been issued or public TLS endpoint tested. HTTP binding remains loopback by default.

The InsightFace-provided weights remain restricted to non-commercial research. Licensed reference photos do not imply celebrity endorsement or automatically resolve personality/biometric rights. A public commercial release still needs an appropriate rights review.


## Recorded results (2026-11-06)

[Machine-readable verification record](verification-2026-11-06.json). Local checks passed: 6 frontend/client HTTP tests, 39 backend tests (including all 35 real-reference self-matches), and 26 Chromium desktop/mobile browser tests. The browser run includes real inference and confirms all five display photos decode successfully. Automated WCAG-tagged scans found no violations in the checked landing, upload, and result states.

One unthrottled local production run recorded LCP 192 ms / 252 ms (desktop/mobile), CLS 0 in both, and 146,415 encoded script bytes. These are lab observations with potentially warm server caches, not mobile-network or field performance claims.

The gateway smoke check returned readiness with 35 subjects, a cacheable JPEG, HTTP 413 for an oversized declared upload, and 10 HTTP 429 responses out of 12 concurrent invalid requests even when each supplied a different fake forwarding address. The other two requests reached validation and returned 415.

The dependency audit found no known vulnerabilities in npm or the 36 exact Python runtime packages; none of the Python packages were skipped. Two upstream deprecation warnings remain in backend tests (Starlette's httpx test transport and InsightFace's scikit-image alignment API); inference passed on the tested versions. These dependency warnings are not suppressed.
