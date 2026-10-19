import { useEffect, useRef, useState } from 'react';
export type Mood = 'idle' | 'working' | 'replying' | 'offline' | 'waiting';
const atlas = new URL('./assets/companion-atlas.png', import.meta.url).href;
function Sprite() {
  return (
    <span
      className="companion-sprite"
      style={{ backgroundImage: `url(${atlas})` }}
      aria-hidden="true"
    />
  );
}

/** History uses a quiet portrait; larger companions can greet. */
export function Companion({ mood = 'idle', compact = false }: { mood?: Mood; compact?: boolean }) {
  return compact ? (
    <span className={`companion compact mood-${mood}`} aria-hidden="true">
      <Sprite />
    </span>
  ) : (
    <InteractiveCompanion mood={mood} />
  );
}
function InteractiveCompanion({ mood }: { mood: Mood }) {
  const [wave, setWave] = useState(false);
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || !document.hidden);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    const visibility = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      document.removeEventListener('visibilitychange', visibility);
      clearTimeout(timer.current);
    };
  }, []);
  return (
    <button
      type="button"
      className={`companion mood-${mood} ${wave ? 'waving' : ''} ${visible ? '' : 'companion-paused'}`}
      aria-label="和 Hymio 打个招呼"
      title="Hymio 在这里"
      onClick={() => {
        clearTimeout(timer.current);
        setWave(true);
        timer.current = setTimeout(() => setWave(false), 1200);
      }}
    >
      <Sprite />
    </button>
  );
}
