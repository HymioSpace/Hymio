import { useState } from 'react';
export type Mood = 'idle' | 'working' | 'replying' | 'offline' | 'waiting';
export function Companion({ mood = 'idle', compact = false }: { mood?: Mood; compact?: boolean }) {
  const [wave, setWave] = useState(false);
  return (
    <button
      className={`companion ${compact ? 'compact' : ''} mood-${mood} ${wave ? 'waving' : ''}`}
      aria-label="和 Hymio 打个招呼"
      title="Hymio 在这里"
      onClick={() => {
        setWave(true);
        setTimeout(() => setWave(false), 1400);
      }}
    >
      <svg viewBox="0 0 220 210" fill="none" aria-hidden="true">
        <ellipse
          className="companion-shadow"
          cx="109"
          cy="191"
          rx="42"
          ry="5"
          fill="currentColor"
          opacity=".06"
        />
        <g
          className="companion-body"
          stroke="currentColor"
          strokeWidth="4.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path
            d="M66 143V88C66 55 84 39 110 39C138 39 154 57 154 88V143C154 159 145 169 131 169H89C75 169 66 159 66 143Z"
            fill="var(--companion-fill, #fff)"
          />
          <path d="M88 170L85 183M131 170L134 183" />
          <path className="companion-arm" d="M66 112C45 113 41 101 42 85M42 85L36 76M42 85L47 74" />
          <path className="companion-right" d="M154 115C171 117 177 127 176 140" />
          <path d="M105 40C100 28 110 24 120 28" strokeWidth="3.7" />
          <g className="companion-face">
            <path className="companion-eyes" d="M94 89V95M125 89V95" strokeWidth="6" />
            <path className="companion-smile" d="M103 112Q110 118 117 112" strokeWidth="3" />
            <path d="M82 107H86M134 107H138" stroke="#b9c9fa" strokeWidth="3" />
          </g>
          <path d="M74 137L145 151" stroke="#4b70ff" strokeWidth="10" />
          <path d="M143 149L151 159" stroke="#4b70ff" strokeWidth="6" />
        </g>
        <g className="companion-notes" stroke="#4b70ff" strokeWidth="2.5" strokeLinecap="round">
          <path d="M174 55V42L183 40V51" />
          <path d="M38 141V132L31 134" />
          <circle cx="170" cy="57" r="3" />
          <circle cx="180" cy="53" r="3" />
        </g>
        <g className="companion-thought" fill="#4b70ff">
          <circle cx="171" cy="53" r="3" />
          <circle cx="183" cy="47" r="3" />
          <circle cx="194" cy="39" r="3" />
        </g>
      </svg>
    </button>
  );
}
