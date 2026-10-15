const STATUS = {
  ok: { label: "Monitoring", dot: "bg-good", text: "text-good" },
  changed: { label: "Change detected", dot: "bg-accent", text: "text-accent" },
  error: { label: "Error", dot: "bg-bad", text: "text-bad" },
  blocked: { label: "Blocked / challenge", dot: "bg-warn", text: "text-warn" },
  paused: { label: "Paused", dot: "bg-mute", text: "text-mute" },
  checking: { label: "Checking", dot: null, text: "text-accent" },
  pending: { label: "Waiting for first check", dot: "bg-warn", text: "text-warn" },
};

export default function StatusBadge({ status }) {
  const s = STATUS[status] ?? STATUS.pending;
  return (
    <span className={`inline-flex shrink-0 items-center gap-2 whitespace-nowrap text-xs font-medium ${s.text}`}>
      {s.dot ? <span className={`h-2 w-2 rounded-full ${s.dot}`} aria-hidden="true" /> : <span className="spinner" aria-hidden="true" />}
      {s.label}
    </span>
  );
}