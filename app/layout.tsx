import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Celebry | Find your famous twin', description: 'A little curiosity, a little star power. Meet Celebry.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
