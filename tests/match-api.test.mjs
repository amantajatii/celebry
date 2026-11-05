import assert from 'node:assert/strict';
import { test } from 'node:test';
import { findMatches, parseMatches } from '../lib/match-api.ts';

// Deterministic contract fixtures; never used by the production UI.
function result() {
  return {metric: 'cosine_similarity', notice: 'Entertainment only.', matches: Array.from({length: 5}, (_, i) => ({
    rank: i + 1, cosineSimilarity: 1 - i * .3, celebrity: {id: String(i), name: `Fixture ${i}`, imageUrl: 'https://example.org/image.jpg', sourceUrl: 'https://example.org/source', license: 'Test fixture', licenseUrl: null, attribution: 'Test fixture'},
  }))};
}

test('accepts five descending raw cosine scores, including negative scores', () => {
  const parsed = parseMatches(result());
  assert.equal(parsed.matches.length, 5);
  assert.ok(parsed.matches[4].cosineSimilarity < 0);
});

test('rejects incomplete, duplicate, invalid, and unsafe API data', () => {
  const mutations = [
    data => data.matches.pop(),
    data => { data.metric = 'probability'; },
    data => { data.matches[1].celebrity.id = '0'; },
    data => { data.matches[2].cosineSimilarity = 1.1; },
    data => { data.matches[2].cosineSimilarity = NaN; },
    data => { data.matches[1].cosineSimilarity = .99; data.matches[0].cosineSimilarity = .5; },
    data => { data.matches[0].celebrity.imageUrl = 'javascript:alert(1)'; },
    data => { data.matches[0].celebrity.sourceUrl = 'data:text/html,x'; },
    data => { data.matches[0].rank = 2; },
  ];
  for (const mutate of mutations) { const data = result(); mutate(data); assert.throws(() => parseMatches(data)); }
});

test('sends the actual file and consent as multipart without setting its boundary', async t => {
  const file = new File(['fixture'], 'photo.png', {type: 'image/png'});
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.endsWith('/api/match'));
    assert.equal(options.method, 'POST');
    assert.equal(options.headers, undefined);
    assert.equal(options.signal, controller.signal);
    assert.equal(options.body.get('consent'), 'true');
    assert.equal(await options.body.get('photo').text(), 'fixture');
    assert.equal(options.credentials, 'omit');
    assert.equal(options.cache, 'no-store');
    return Response.json(result());
  });
  assert.equal((await findMatches(file, controller.signal)).matches[0].rank, 1);
});

test('maps backend errors and non-JSON proxy failures to helpful messages', async t => {
  const file = new File(['fixture'], 'x.png');
  const signal = new AbortController().signal;
  const mocked = t.mock.method(globalThis, 'fetch');
  for (const [code, message] of [['NO_FACE', /No face/], ['MULTIPLE_FACES', /more than one/], ['MATCHING_NOT_READY', /unavailable/], ['RATE_LIMITED', /wait a minute/]]) {
    mocked.mock.mockImplementation(async () => Response.json({error: {code, message: 'server internals'}}, {status: 422}));
    await assert.rejects(findMatches(file, signal), message);
  }
  mocked.mock.mockImplementation(async () => new Response('<html>proxy error</html>', {status: 502}));
  await assert.rejects(findMatches(file, signal), /could not be completed/);
});

test('preserves cancellation so the UI can ignore a stale request', async t => {
  t.mock.method(globalThis, 'fetch', (_url, options) => { throw options.signal.reason; });
  const controller = new AbortController();
  controller.abort(new DOMException('Cancelled', 'AbortError'));
  await assert.rejects(findMatches(new File(['x'], 'x.jpg'), controller.signal), {name: 'AbortError'});
});
