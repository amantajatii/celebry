# Collection selection and multi-photo profiles

Celebry now lets the user choose **All celebrities**, **Actors**, or **Actresses** before upload analysis. The choice filters eligible candidates before ranking, giving five results from that collection only. The current catalog contains 17 actors and 18 actresses. Labels follow written public biographical descriptions linked in `backend/data/sources.json`; no gender inference runs on the uploaded face.

Each of the 35 celebrity profiles uses three licensed public reference photos (105 total). The builder checks every photo's checksum, image content, and single-face detection, and rejects repeated bytes within a subject. Each photo retains its own source, author, and license in `backend/data/hollywood-sources.json` and result credits. Commons downloads use a standard 330px thumbnail for new files, retain already verified larger files, and resume with a per-photo cache. A changed source or checksum forces a download from the current source URL. Manifest and catalog publication remain atomic.

The profile calculation is:

```text
profile = normalize(mean(normalize(reference_embedding_i)))
score = dot(normalize(query_embedding), profile)
```

Scores remain raw cosine values in [-1, 1]. Averaging reduces a profile's dependence on one photo; human-perceived resemblance accuracy has not been measured. Individual enrollment photos no longer necessarily score 1.0 against their multi-photo profile. Top-five results remain relative to the selected collection, with no invented probability or unvalidated cutoff.

Rebuild the catalog and restart the backend after upgrading, following `backend/README.md`. Single-photo manifests remain supported. Legacy subjects without collection labels can appear in All celebrities, but cannot fill Actors or Actresses. Collections with fewer than five enrolled subjects return `COLLECTION_NOT_READY` instead of silently mixing groups. The frontend rejects responses that ignore its selected collection.

## Local verification, 2026-11-06

- Catalog build: 35 profiles from 105 references; all references passed image/one-face checks.
- Backend: 46 tests passed with real local models enabled, including both filtered collections, all 35 primary-reference self-rank checks, numerical cosine agreement, normalized-mean aggregation, credits, and downloader cache invalidation.
- Frontend client: 7 tests passed, including real HTTP inference and the Actors filter.
- Browser: 26 Chromium tests passed across desktop and mobile emulation. Real public Zendaya and Tom Holland photos exercised All celebrities and Actors end to end. Checked layout, selection retention on reset, image decoding, consent, cancellation, sharing payloads, and automated WCAG-tagged scans. Two production performance checks were skipped because this run used the development server.
- Frontend production build and TypeScript checks passed.

These checks establish pipeline correctness and collection selection. Enrollment self-matching is not an unseen-user resemblance benchmark. No private user selfie was used in these tests. Docker images were not rebuilt for this change; rebuild them before using the optional container stack. Physical Safari and public deployment were not tested.
