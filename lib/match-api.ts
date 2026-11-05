export interface Celebrity {
  id: string;
  name: string;
  imageUrl: string;
  sourceUrl: string;
  license: string;
  licenseUrl: string | null;
  attribution: string;
}
export interface Match {
  rank: number;
  celebrity: Celebrity;
  cosineSimilarity: number;
}
export interface MatchResponse {
  matches: Match[];
  metric: 'cosine_similarity';
  notice: string;
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid API response. Please try again.');
  return value as Record<string, unknown>;
}
function text(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) throw new Error('Invalid API response. Please try again.');
  return value;
}
function httpUrl(value: unknown): string {
  try {
    const url = new URL(text(value));
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error();
    return url.href;
  } catch { throw new Error('The service returned an invalid image or credit URL.'); }
}
export function parseMatches(value: unknown): MatchResponse {
  const body = record(value);
  if (body.metric !== 'cosine_similarity' || !Array.isArray(body.matches) || body.matches.length !== 5) {
    throw new Error('The service returned incomplete results. Please try again.');
  }
  const matches = body.matches.map((value, index): Match => {
    const match = record(value);
    const celebrity = record(match.celebrity);
    if (match.rank !== index + 1 || typeof match.cosineSimilarity !== 'number' || !Number.isFinite(match.cosineSimilarity) || Math.abs(match.cosineSimilarity) > 1) {
      throw new Error('The service returned invalid similarity scores.');
    }
    return { rank: index + 1, cosineSimilarity: match.cosineSimilarity, celebrity: {
      id: text(celebrity.id), name: text(celebrity.name), imageUrl: httpUrl(celebrity.imageUrl),
      sourceUrl: httpUrl(celebrity.sourceUrl), license: text(celebrity.license),
      licenseUrl: celebrity.licenseUrl == null ? null : httpUrl(celebrity.licenseUrl), attribution: text(celebrity.attribution),
    } };
  });
  if (new Set(matches.map(match => match.celebrity.id)).size !== 5 || matches.some((match, i) => i > 0 && match.cosineSimilarity > matches[i - 1].cosineSimilarity)) {
    throw new Error('The service returned an invalid ranking. Please try again.');
  }
  return { matches, metric: 'cosine_similarity', notice: text(body.notice) };
}

const errors: Record<string, string> = {
  NO_FACE: 'No face found. Try a clear, front-facing selfie.',
  MULTIPLE_FACES: 'We found more than one face. Choose a photo with just you.',
  FACE_ALIGNMENT_FAILED: 'We couldn’t align your face. Try a clearer, front-facing photo.',
  FACE_ENCODING_FAILED: 'We couldn’t analyze this face. Please try another photo.',
  MATCHING_NOT_READY: 'Matching is unavailable right now. Please try again later.',
  MATCHING_BUSY: 'Someone else is having their star moment. Please try again shortly.',
  RATE_LIMITED: 'Too many attempts. Please wait a minute before trying again.',
  CONSENT_REQUIRED: 'Please agree to photo analysis before continuing.',
  IMAGE_TOO_LARGE: 'Choose a photo no larger than 10 MB.',
  REQUEST_TOO_LARGE: 'Choose a photo no larger than 10 MB.',
  IMAGE_DIMENSIONS_TOO_LARGE: 'Choose a smaller photo, up to 20 megapixels.',
  INVALID_IMAGE: 'This photo could not be read. Please choose another image.',
  EMPTY_IMAGE: 'This file is empty. Please choose another photo.',
  ANIMATED_IMAGE: 'Choose a still photo instead of an animation.',
  UNSUPPORTED_IMAGE: 'Please use a JPEG, PNG, or WebP image.',
  IMAGE_TYPE_MISMATCH: 'The file content doesn’t match its image type. Try another photo.',
};

export async function findMatches(photo: File, signal: AbortSignal): Promise<MatchResponse> {
  const form = new FormData();
  form.append('photo', photo);
  form.append('consent', 'true');
  const base = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
  const response = await fetch(`${base}/api/match`, { method: 'POST', body: form, signal, cache: 'no-store', credentials: 'omit' });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    let code = '';
    try { code = text(record(record(body).error).code); } catch { /* An upstream proxy may return a non-JSON error. */ }
    throw new Error(errors[code] || (response.status === 429 ? errors.RATE_LIMITED : 'Matching could not be completed. Please try again.'));
  }
  return parseMatches(body);
}
