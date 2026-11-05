import type { Metadata } from 'next';
import MatchExperience from '@/components/match-experience';

export const metadata: Metadata = {
  title: 'Find your twin | Celebry',
  description: 'Upload a selfie and discover your closest Hollywood look-alikes with real facial similarity matching.',
};

export default function MatchPage() {
  return <MatchExperience />;
}
