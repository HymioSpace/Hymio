import { LoaderCircle } from 'lucide-react';
import { compactionState } from '@hymio/client';
import type { OathEvent } from '@hymio/protocol';
export function CompactionStatus({ events, now }: { events: OathEvent[]; now: number }) {
  const state = compactionState(events, now);
  if (!state) return null;
  return (
    <div className="compaction-status" key={state.id}>
      <LoaderCircle size={14} className="compaction-spinner" />
      <span role="status">{state.title}</span>
    </div>
  );
}
