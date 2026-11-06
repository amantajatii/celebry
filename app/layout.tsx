import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
const sans = localFont({ src: './fonts/dm-sans.ttf', variable: '--font-sans', display: 'swap' });
const editorial = localFont({ src: './fonts/playfair-italic.ttf', variable: '--font-editorial', style: 'italic', display: 'swap' });
export const metadata: Metadata = { title: 'Celebry | Find your famous twin', description: 'A little curiosity, a little star power. Meet Celebry.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" className={`${sans.variable} ${editorial.variable}`}><body><a className="skip-link" href="#main-content">Skip to content</a>{children}</body></html>; }
