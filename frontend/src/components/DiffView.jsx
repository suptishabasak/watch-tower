function Line({ sign, tone, label, children, dim }) {
  const tones = {
    add: "bg-good/10 border-good/40",
    del: "bg-bad/10 border-bad/40",
  };
  return (
    <div className={`flex gap-3 border-l-2 px-3 py-1.5 font-mono text-[13px] leading-relaxed ${tones[tone]} ${dim ? "opacity-60" : ""}`}>
      <span aria-hidden="true" className={tone === "add" ? "text-good" : "text-bad"}>
        {sign}
      </span>
      <span className="sr-only">{label}:</span>
      <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{children}</span>
    </div>
  );
}

function Segments({ segments, show }) {
  return segments
    .filter((s) => s.type === "equal" || s.type === show)
    .map((s, i) =>
      s.type === "equal" ? (
        <span key={i}>{s.text}</span>
      ) : (
        <mark key={i} className={`rounded-sm px-0.5 text-inherit ${show === "del" ? "bg-bad/40" : "bg-good/40"}`}>
          {s.text}
        </mark>
      )
    );
}

function Item({ item, dim }) {
  if (item.kind === "added") {
    return (
      <Line sign="+" tone="add" label="Added" dim={dim}>
        {item.after}
      </Line>
    );
  }
  if (item.kind === "removed") {
    return (
      <Line sign="−" tone="del" label="Removed" dim={dim}>
        {item.before}
      </Line>
    );
  }
  return (
    <div className="space-y-px">
      <Line sign="−" tone="del" label="Previous" dim={dim}>
        {item.segments ? <Segments segments={item.segments} show="del" /> : item.before}
      </Line>
      <Line sign="+" tone="add" label="Current" dim={dim}>
        {item.segments ? <Segments segments={item.segments} show="add" /> : item.after}
      </Line>
    </div>
  );
}

export default function DiffView({ items, omitted = 0 }) {
  const relevant = items.filter((i) => i.relevant !== false);
  const other = items.filter((i) => i.relevant === false);

  return (
    <div className="space-y-3">
      <div className="space-y-2 overflow-hidden rounded-md border border-line">
        {relevant.map((item, i) => (
          <Item key={i} item={item} />
        ))}
      </div>

      {other.length > 0 && (
        <details className="rounded-md border border-line">
          <summary className="cursor-pointer px-3 py-2 text-sm text-mute hover:text-ink">
            {other.length} other change{other.length === 1 ? "" : "s"} outside what you're watching
          </summary>
          <div className="space-y-2 border-t border-line">
            {other.map((item, i) => (
              <Item key={i} item={item} dim />
            ))}
          </div>
        </details>
      )}

      {omitted > 0 && <p className="text-xs text-mute">{omitted} more changes were not stored to keep history small.</p>}
    </div>
  );
}