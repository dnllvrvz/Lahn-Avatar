// Stacked-bar visualization of a request's latency, broken down by pipeline component.
// segments: [{ label, ms, color }] in trip order; zero-duration segments are hidden.
export default function LatencyBreakdown({ segments, totalMs }) {
  const shown = segments.filter(s => s.ms > 0);
  if (shown.length === 0) return null;

  const sum = shown.reduce((acc, s) => acc + s.ms, 0);
  const total = totalMs && totalMs >= sum ? totalMs : sum;

  return (
    <div className="space-y-2">
      <p className="font-poetic text-stone-700 text-sm">
        Most recent request — total:{" "}
        <span className="font-semibold">{(total / 1000).toFixed(2)}s</span>
      </p>

      {/* Stacked bar */}
      <div className="flex w-full h-4 rounded overflow-hidden border border-stone-300">
        {shown.map(s => (
          <div
            key={s.label}
            style={{
              width: `${Math.max((s.ms / total) * 100, 1)}%`,
              backgroundColor: s.color,
            }}
            title={`${s.label}: ${s.ms} ms`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="space-y-1">
        {shown.map(s => (
          <div key={s.label} className="flex items-center gap-2 text-xs font-poetic text-stone-600">
            <span
              className="w-3 h-3 rounded-sm shrink-0"
              style={{ backgroundColor: s.color }}
            />
            <span className="flex-1">{s.label}</span>
            <span className="font-mono">{s.ms} ms</span>
            <span className="w-10 text-right text-stone-400">
              {((s.ms / total) * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
