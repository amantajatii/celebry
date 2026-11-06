'use client';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, ImagePlus, RotateCcw, Share2, X } from 'lucide-react';
import { findMatches, celebrityImageUrl, type MatchResponse } from '@/lib/match-api';

const loadingMessages = ['Looking for your famous twin...', 'Analyzing facial features...', 'Finding your closest matches...'];

export default function MatchExperience() {
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<MatchResponse | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!file) { setPreview(''); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => () => { request.current?.abort(); request.current = null; }, []);
  useEffect(() => {
    if (!busy) return;
    setLoadingStep(0);
    const timer = setInterval(() => setLoadingStep(step => Math.min(step + 1, loadingMessages.length - 1)), 1600);
    return () => clearInterval(timer);
  }, [busy]);
  useEffect(() => { if (result) resultHeading.current?.focus(); }, [result]);

  function choose(next?: File) {
    if (!next || busy) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(next.type)) { setError('Please choose a JPEG, PNG, or WebP image.'); return; }
    if (!next.size || next.size > 10 * 1024 * 1024) { setError('Please choose a non-empty photo under 10 MB.'); return; }
    setFile(next); setConsent(false); setResult(null); setError(''); setNotice('');
  }
  function cancel() {
    request.current?.abort(); request.current = null;
    setBusy(false); setNotice('Request cancelled. You can try again.');
  }
  function reset() {
    request.current?.abort(); request.current = null;
    setBusy(false); setFile(null); setResult(null); setError(''); setConsent(false); setNotice('');
    if (input.current) input.current.value = '';
  }
  async function analyze() {
    if (request.current) return;
    if (!file) { setError('Choose a photo first.'); return; }
    if (!consent) { setError('Please agree to photo analysis first.'); return; }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(''); setNotice('');
    const timeout = setTimeout(() => controller.abort('timeout'), 60_000);
    try {
      const matches = await findMatches(file, controller.signal);
      if (request.current === controller) setResult(matches);
    } catch (error) {
      if (request.current !== controller) return;
      setError(controller.signal.reason === 'timeout'
        ? 'Analysis took too long. Please try again.'
        : error instanceof TypeError ? 'Couldn’t reach the matching service. Check your connection and try again.'
        : error instanceof Error ? error.message : 'Something went wrong. Please try again.');
    } finally {
      clearTimeout(timeout);
      if (request.current === controller) { request.current = null; setBusy(false); }
    }
  }
  async function share() {
    if (!result) return;
    const best = result.matches[0];
    const text = `My closest Hollywood match on Celebry is ${best.celebrity.name}! Cosine similarity: ${best.cosineSimilarity.toFixed(3)}. Just for fun, not an identity probability.`;
    try {
      if (navigator.share) await navigator.share({ title: 'My Celebry match', text });
      else { await navigator.clipboard.writeText(text); setNotice('Result copied. Paste it wherever you’d like to share.'); }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      setNotice('Sharing wasn’t available. Please try again in a supported browser.');
    }
  }
  const top = result?.matches[0];
  return <div className="page-shell match-page">
    <header className="nav"><Link href="/" className="logo" aria-label="Celebry home">celebry<span>✳</span></Link><Link href="/" className="nav-cta"><ArrowLeft size={16}/> Back to home</Link></header>
    <main id="main-content" tabIndex={-1}>
      <section className={`find-section match-section${result ? ' has-results' : ''}`} id="find">
        <div className="section-intro"><div className="eyebrow"><span className="dot"/> {result ? 'YOUR STAR MOMENT' : 'THE FUN STARTS HERE'}</div><h1>{result ? <>A familiar<br/><em>kind of famous.</em></> : <>Find your<br/><em>famous twin.</em></>}</h1><p>{result ? 'Your closest faces from our small Hollywood collection. A little resemblance, a little curiosity, all for fun.' : 'Choose a clear photo with just you in the frame. We’ll compare your facial features with our Hollywood collection.'}</p><div className="hand-note">Your moment<br/>in the spotlight <span>↗</span></div></div>
        <div className="upload-card">
          <div className="card-top"><span>{result ? 'YOUR RESULTS' : 'YOUR PHOTO'}</span><span>{result ? '02 / 02' : '01 / 02'}</span></div>
          {!result ? <>
            <div className={'dropzone ' + (dragging ? 'dragging' : '')} onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length !== 1) setError('Please choose one photo at a time.'); else choose(event.dataTransfer.files[0]); }}>
              {preview ? <div className="preview"><img src={preview} alt="Your selected selfie preview"/><button className="remove" onClick={reset} disabled={busy} aria-label="Remove photo"><X size={18}/></button><span>{file?.name}</span></div> : <><div className="upload-icon"><ImagePlus size={30} strokeWidth={1.5}/></div><h2 className="upload-title">Drop your selfie here</h2><p>or <button className="text-button" onClick={() => input.current?.click()}>browse your files</button></p><small>JPG, PNG or WebP · up to 10 MB</small></>}
            </div>
            <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Choose your selfie" onChange={event => { choose(event.target.files?.[0]); event.target.value = ''; }} hidden/>
            {file && <button className="replace" disabled={busy} onClick={() => input.current?.click()}><RotateCcw size={14}/> Replace photo</button>}
            <label className="consent"><input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)}/><span>I consent to sending this photo for facial analysis and look-alike matching. <Link href="/#privacy">About my photo</Link></span></label>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="button button-purple full" disabled={busy} onClick={analyze}>{busy ? loadingMessages[loadingStep] : 'Find my celebrity twin'}{busy ? <span className="loading-dots" aria-hidden="true">···</span> : <ArrowRight size={18}/>}</button>
            {busy && <div className="analysis-status"><p role="status" aria-atomic="true">{loadingMessages[loadingStep]}</p><button className="text-button" onClick={cancel}>Cancel request</button></div>}
            <p className="demo-note">Your photo is processed by our backend and discarded after analysis.</p>
          </> : top && <div className="result live-result">
            <div className="result-heading"><div><span className="sample">YOUR CLOSEST MATCH</span><h2 ref={resultHeading} tabIndex={-1}>Your star moment.</h2></div><button className="remove-inline" onClick={reset} aria-label="Start over"><X size={18}/></button></div>
            <div className="comparison"><div><img src={preview} alt="Your uploaded selfie"/><span>YOU</span></div><b aria-hidden="true">✳</b><div><img width={360} height={420} src={celebrityImageUrl(top.celebrity.id)} alt={top.celebrity.name}/><span>CLOSEST OF {result.catalogSize} FACES</span></div></div>
            <div className="result-name"><strong>{top.celebrity.name} <i aria-hidden="true">✦</i></strong><small>Cosine similarity <b>{top.cosineSimilarity.toFixed(3)}</b></small></div>
            <p className="score-explanation">Cosine scores range from −1 to 1; higher means closer facial embeddings. These are relative matches in this collection of {result.catalogSize} celebrities, not percentages or identity probabilities.</p>
            <h3 className="ranking-title">Your Hollywood top five</h3>
            <ol className="match-ranking">{result.matches.map(match => <li key={match.celebrity.id}><span className="rank-number">{String(match.rank).padStart(2, '0')}</span><img src={celebrityImageUrl(match.celebrity.id)} alt="" loading="lazy" width={44} height={52}/><span className="rank-name">{match.celebrity.name}</span><span className="rank-score" aria-label={`Cosine similarity ${match.cosineSimilarity.toFixed(3)}`}>{match.cosineSimilarity.toFixed(3)}</span></li>)}</ol>
            <div className="result-actions"><button className="button button-dark full" onClick={reset}>Try another photo <RotateCcw size={16}/></button><button className="button button-purple full" onClick={share}>Share my results <Share2 size={16}/></button></div>
            <p className="demo-note">{result.notice}</p>
            <details className="photo-credits"><summary>Celebrity photo credits</summary>{result.matches.map(({ celebrity }) => <p key={celebrity.id}><a href={celebrity.sourceUrl} target="_blank" rel="noreferrer">{celebrity.name}</a>: {celebrity.attribution}. {celebrity.licenseUrl ? <a href={celebrity.licenseUrl} target="_blank" rel="noreferrer">{celebrity.license}</a> : celebrity.license}.</p>)}</details>
          </div>}
          {notice && <p className="interaction-notice" role="status">{notice}</p>}
        </div>
      </section>
      <p className="match-privacy">Your face, your choice. No account needed. <Link href="/#privacy">About your privacy</Link></p>
    </main>
  </div>;
}
