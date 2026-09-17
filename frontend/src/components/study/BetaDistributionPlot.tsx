import type { ConceptEstimate } from "../../../../contracts/api";

export function betaCurve(alpha: number, beta: number) {
  if (![alpha, beta].every(n => Number.isInteger(n) && n >= 1 && n <= 100000)) return [];
  const logFactorial = (n: number) => {
    let result = 0;
    for (let i = 2; i <= n; i++) result += Math.log(i);
    return result;
  };
  const normalizer = logFactorial(alpha + beta - 1) - logFactorial(alpha - 1) - logFactorial(beta - 1);
  const xs = [...Array.from({ length: 161 }, (_, i) => i / 160),
    alpha / (alpha + beta), ...(alpha + beta > 2 ? [(alpha - 1) / (alpha + beta - 2)] : [])];
  return [...new Set(xs)].sort((a, b) => a - b).map(x => {
    const log = normalizer + (alpha === 1 ? 0 : (alpha - 1) * Math.log(x))
      + (beta === 1 ? 0 : (beta - 1) * Math.log1p(-x));
    return { x, y: Math.exp(log) };
  });
}

export function BetaDistributionPlot({ current, before, compact = false, beforeLabel = "session start" }: {
  current: ConceptEstimate; before?: ConceptEstimate; compact?: boolean; beforeLabel?: string;
}) {
  if (current.alpha == null || current.beta == null) return null;
  const points = betaCurve(current.alpha, current.beta);
  const previous = before?.alpha && before.beta ? betaCurve(before.alpha, before.beta) : [];
  if (!points.length) return null;
  const top = Math.max(...points.map(p => p.y), ...previous.map(p => p.y), 1) * 1.08;
  const x = (n: number) => 18 + 244 * n;
  const y = (n: number) => 91 - 74 * n / top;
  const path = (data: typeof points) => data.map((p, i) => `${i ? "L" : "M"}${x(p.x).toFixed(2)},${y(p.y).toFixed(2)}`).join(" ");
  const band = points.filter(p => p.x >= current.interval90.lower && p.x <= current.interval90.upper);
  const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
  const description = `Beta(${current.alpha}, ${current.beta}); mean ${pct(current.mean)}; 90% interval ${pct(current.interval90.lower)} to ${pct(current.interval90.upper)}; ${current.evidence_count} observations.`;
  return <figure className={`beta-plot ${compact ? "beta-compact" : ""}`}>
    <svg viewBox="0 0 280 116" role="img" aria-label={description}>
      <title>{description}</title>
      <line x1="18" x2="262" y1="91" y2="91" stroke="currentColor" opacity=".25" />
      {!!band.length && <path d={`M${x(band[0].x)},91 ${path(band).replace(/^M/, "L")} L${x(band.at(-1)!.x)},91 Z`} fill="currentColor" opacity=".15" />}
      {!!previous.length && <path d={path(previous)} fill="none" stroke="#9ba6b5" strokeWidth="2" strokeDasharray="4 3" />}
      <path d={path(points)} fill="none" stroke="currentColor" strokeWidth="2.5" />
      <line x1={x(current.mean)} x2={x(current.mean)} y1="14" y2="91" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2 3" />
      <line x1={x(current.interval90.lower)} x2={x(current.interval90.upper)} y1="94" y2="94" stroke="currentColor" strokeWidth="3" />
      <text x="18" y="110" fontSize="10" fill="currentColor">0</text>
      <text x="140" y="110" textAnchor="middle" fontSize="10" fill="currentColor">Mastery probability</text>
      <text x="262" y="110" textAnchor="end" fontSize="10" fill="currentColor">1</text>
    </svg>
    {!compact && <figcaption>
      {before && <span>Dashed: {beforeLabel} · Solid: now. </span>}
      Mean {pct(current.mean)} · 90% interval {pct(current.interval90.lower)}–{pct(current.interval90.upper)}.
      <span className="beta-scale"> Density height scaled per plot{before ? "; both curves share the same scale" : ""}.</span>
    </figcaption>}
  </figure>;
}
