// Generative SVG accents. Deterministic (no Math.random), so server and client agree.

/** Parametric wave divider: a few superposed sines, phase-shifted per line. */
export function WaveDivider({ seed = 1, className = "" }: { seed?: number; className?: string }) {
  const W = 1200;
  const lines = Array.from({ length: 5 }, (_, k) => {
    const pts: string[] = [];
    for (let x = 0; x <= W; x += 12) {
      const t = x / W;
      const env = Math.sin(Math.PI * t);
      const y =
        30 +
        env * (10 * Math.sin(t * 9 + seed + k * 0.55) + 5 * Math.sin(t * 23 + seed * 2.1 + k * 0.3)) +
        (k - 2) * 3.2;
      pts.push(`${x},${y.toFixed(2)}`);
    }
    return pts.join(" ");
  });
  return (
    <svg viewBox={`0 0 ${W} 60`} preserveAspectRatio="none" aria-hidden className={`h-14 w-full ${className}`}>
      {lines.map((p, k) => (
        <polyline key={k} points={p} fill="none" stroke={k === 2 ? "#22D3EE" : "#fff"} strokeOpacity={k === 2 ? 0.45 : 0.1} strokeWidth="1" vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  );
}

/** Radial calibration rings with degree ticks, as on a servo horn protractor. */
export function CalibrationRings({ size = 320, className = "" }: { size?: number; className?: string }) {
  const c = size / 2;
  const ticks = Array.from({ length: 72 }, (_, i) => {
    const a = (i * 5 * Math.PI) / 180;
    const major = i % 6 === 0;
    const r1 = c - 6;
    const r0 = r1 - (major ? 12 : 5);
    return (
      <line key={i} x1={c + r0 * Math.cos(a)} y1={c + r0 * Math.sin(a)} x2={c + r1 * Math.cos(a)} y2={c + r1 * Math.sin(a)} stroke="#fff" strokeOpacity={major ? 0.28 : 0.12} />
    );
  });
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className={className}>
      {ticks}
      {[0.82, 0.6, 0.36].map((k, i) => (
        <circle key={k} cx={c} cy={c} r={c * k} fill="none" stroke="#fff" strokeOpacity={0.09} strokeDasharray={i === 1 ? "2 6" : undefined} />
      ))}
      <path d={`M ${c} ${c} L ${c + c * 0.82} ${c}`} stroke="#FF6A1A" strokeOpacity="0.6" />
      <circle cx={c} cy={c} r="2.5" fill="#FF6A1A" />
    </svg>
  );
}

/** Isometric grid framing element. */
export function IsoGrid({ className = "" }: { className?: string }) {
  const W = 480;
  const H = 240;
  const step = 24;
  const lines: [number, number, number, number][] = [];
  const dy = Math.tan(Math.PI / 6);
  for (let x = -H / dy; x < W + H / dy; x += step) {
    lines.push([x, 0, x + H / dy, H]);
    lines.push([x, H, x + H / dy, 0]);
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} aria-hidden className={className} preserveAspectRatio="xMidYMid slice">
      <defs>
        <radialGradient id="iso-fade">
          <stop offset="0" stopColor="#fff" stopOpacity="1" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
        <mask id="iso-mask">
          <rect width={W} height={H} fill="url(#iso-fade)" />
        </mask>
      </defs>
      <g mask="url(#iso-mask)" stroke="#fff" strokeOpacity="0.1">
        {lines.map(([x1, y1, x2, y2], i) => (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />
        ))}
      </g>
    </svg>
  );
}
