import { useEffect, useMemo, useState } from 'react';

/**
 * AssemblingTitle — J.A.R.V.I.S letters fly in from random offsets and
 * snap into place; HUD ring sweeps underneath. §10 of the implementation
 * plan. Honours `prefers-reduced-motion` by rendering the final frame
 * statically with no transforms.
 */
const LETTERS = ['J', '.', 'A', '.', 'R', '.', 'V', '.', 'I', '.', 'S'];
const STAGGER_MS = 80;

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (e) => setReduced(e.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

function rand(min, max) {
  return Math.random() * (max - min) + min;
}

export default function AssemblingTitle() {
  const reduceMotion = useReducedMotion();

  // Pre-compute per-letter random offsets once per mount so re-renders
  // don't retrigger the tween mid-animation.
  const offsets = useMemo(
    () => LETTERS.map(() => ({
      rx: `${rand(-400, 400)}px`,
      ry: `${rand(-160, 160)}px`,
      rz: `${rand(-60, 60)}deg`,
    })),
    []
  );

  return (
    <div className={`assembling-title ${reduceMotion ? 'static' : 'animate'}`}>
      <svg className="hud-ring" viewBox="0 0 240 240" aria-hidden="true">
        <circle cx="120" cy="120" r="110" className="hud-ring-arc" />
      </svg>
      <h1 className="splash-title" aria-label="JARVIS">
        {LETTERS.map((ch, i) => (
          <span
            key={i}
            className="letter"
            style={{
              '--i': i,
              '--rx': offsets[i].rx,
              '--ry': offsets[i].ry,
              '--rz': offsets[i].rz,
              animationDelay: `${i * STAGGER_MS}ms`,
            }}
          >
            {ch}
          </span>
        ))}
      </h1>
    </div>
  );
}
