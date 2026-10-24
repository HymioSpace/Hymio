import { Layers3, LoaderCircle } from 'lucide-react';
import { compactionState } from '@hymio/client';
import type { OathEvent } from '@hymio/protocol';
export function CompactionStatus({ events, now }: { events: OathEvent[]; now: number }) {
  const state = compactionState(events, now);
  if (!state) return null;
  return (
    <details className="compaction-status" key={state.id}>
      <summary>
        {state.working ? (
          <LoaderCircle size={14} className="compaction-spinner" />
        ) : (
          <Layers3 size={14} />
        )}
        <span role="status">{state.title}</span>
      </summary>
      <div className="compaction-detail">
        <p>{state.detail}</p>
        {state.metrics && <p>{state.metrics}</p>}
      </div>
    </details>
  );
}
