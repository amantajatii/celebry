'use client';
import Link from 'next/link';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main id="main-content" tabIndex={-1} className="error-page"><h1>Let’s try that again.</h1><p>Something interrupted your star moment. Your photo hasn’t been saved.</p><button className="button button-dark" onClick={reset}>Try again</button><Link href="/">Back to Celebry</Link></main>;
}
