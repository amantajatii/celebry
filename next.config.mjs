import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const api = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
const apiOrigin = api.startsWith('/') ? '' : new URL(api).origin;
const dev = process.env.NODE_ENV !== 'production';
const policy = [
  "default-src 'self'", "base-uri 'self'", "object-src 'none'", "frame-ancestors 'none'",
  "form-action 'self'", `img-src 'self' blob: data: https://*.wikimedia.org ${apiOrigin}`,
  "font-src 'self'", "style-src 'self' 'unsafe-inline'",
  // Static App Router pages embed bootstrap scripts; nonce CSP requires dynamic rendering.
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ''}`,
  `connect-src 'self' ${apiOrigin}${dev ? ' ws:' : ''}`,
].join('; ');

export default {
  output: 'standalone',
  distDir: process.env.CELEBRY_BUILD_DIR || '.next',
  outputFileTracingRoot: root,
  turbopack: { root },
  poweredByHeader: false,
  images: { remotePatterns: [{ protocol: 'https', hostname: '**.wikimedia.org' }], maximumRedirects: 2 },
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'Content-Security-Policy', value: policy },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'no-referrer' },
      { key: 'Permissions-Policy', value: 'camera=(self), microphone=(), geolocation=()' },
    ] }];
  },
};
