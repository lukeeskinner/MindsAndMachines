import type { CoachContext } from '../../../../contracts/api';
import { Button } from '../ui/primitives';

export function FocusRanking({ analytics, busy, onPractice }: {
  analytics?: CoachContext;
  busy: boolean;
  onPractice?: (id: string) => void;
}) {
  if (!analytics?.focus_ranking.length) return null;
  return <section className="focus-ranking" aria-label="Practice priorities">
    <h3>What needs attention</h3>
    <p>Low estimates and uncertainty both matter. Practice continues your existing learner model.</p>
    <ol>{analytics.focus_ranking.map(c => <li key={c.concept_id}>
      <strong>{c.concept_name}</strong>
      <p>{(c.mastery_mean * 100).toFixed(1)}% estimate · {c.evidence_count} observations</p>
      <p>{c.reasons.map(r => r.replaceAll('_', ' ')).join(' · ')}</p>
      {onPractice && <Button size="sm" variant="secondary" disabled={busy}
        onClick={() => onPractice(c.concept_id)}>Practice {c.concept_name}</Button>}
    </li>)}</ol>
  </section>;
}
