import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { findMatches } from '../lib/match-api.ts';

// Opt-in: real HTTP + real models; never uploads any private user photo.
test('frontend API client reaches real inference and receives ranked matches', {skip: !process.env.CELEBRY_LIVE_API_TEST}, async () => {
  const reference = await readFile(new URL('../backend/data/hollywood/zendaya.jpg', import.meta.url));
  const result = await findMatches(new File([reference], 'reference.jpg', {type: 'image/jpeg'}), AbortSignal.timeout(60_000));
  assert.equal(result.matches.length, 5);
  assert.equal(result.matches[0].celebrity.id, 'zendaya');
  assert.ok(result.matches[0].cosineSimilarity > .99);
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
  const health = await fetch(`${base}/api/health`);
  assert.equal((await health.json()).matchingReady, true);
  assert.equal(health.headers.get('cache-control'), 'no-store');
  const preflight = await fetch(`${base}/api/match`, {method: 'OPTIONS', headers: {'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST'}});
  assert.equal(preflight.headers.get('access-control-allow-origin'), 'http://localhost:3000');
});
