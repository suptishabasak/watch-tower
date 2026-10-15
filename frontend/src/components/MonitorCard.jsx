import { displayUrl, fullDate, intervalLabel, timeAgo, timeUntil } from "../lib/format.js";
import StatusBadge from "./StatusBadge.jsx";

function Meta({ label, children, title }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-mute">{label}</dt>
      <dd className="truncate text-sm" title={title}>
        {children}
      </dd>
    </div>
  );
}

export default function MonitorCard({ monitor: m, busy, onCheck, onTogglePause, onHistory, onEdit, onDelete }) {
  const running = busy === "check" || m.checking;
  const nextCheck = m.paused ? "Paused" : m.checking ? "Running now" : timeUntil(m.next_check_at);

  return (
    <article className="flex flex-col gap-4 rounded-lg border border-line bg-panel p-4">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-medium">{m.name}</h2>
          <a
            href={m.url}
            target="_blank"
            rel="noopener noreferrer"
            title={m.url}
            className="block truncate text-sm text-mute hover:text-ink hover:underline"
          >
            {displayUrl(m.url)}
          </a>
        </div>
        <StatusBadge status={m.status} />
      </header>

      {m.status === "error" && (
        <p className="rounded-md border border-bad/30 bg-bad/10 px-3 py-2 text-sm">
          <span className="font-medium">Last check failed.</span> {m.last_error}
          {m.consecutive_failures > 1 && <span className="text-mute"> ({m.consecutive_failures} in a row)</span>}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Meta label="Last checked" title={fullDate(m.last_checked_at)}>
          {m.last_result === "pending" && !m.last_checked_at ? "Not yet" : timeAgo(m.last_checked_at)}
        </Meta>
        <Meta label="Next check" title={fullDate(m.next_check_at)}>
          {nextCheck}
        </Meta>
        <Meta label="Frequency">Every {intervalLabel(m.interval_minutes)}</Meta>
        <Meta label="Changes found" title={fullDate(m.last_changed_at)}>
          {m.change_count === 0 ? "None yet" : `${m.change_count}, latest ${timeAgo(m.last_changed_at)}`}
        </Meta>
      </dl>

      {m.focus && (
        <p className="truncate text-xs text-mute" title={m.focus}>
          Watching for: <span className="text-ink">{m.focus}</span>
        </p>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
        <button type="button" className="btn" onClick={onCheck} disabled={running}>
          {running && <span className="spinner" aria-hidden="true" />}
          {running ? "Checking" : "Check now"}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onTogglePause} disabled={busy === "pause"}>
          {m.paused ? "Resume" : "Pause"}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onHistory}>
          History
          {m.unseen_changes > 0 && (
            <span className="rounded-full bg-accent px-1.5 text-xs font-semibold text-[#0b0c10]">{m.unseen_changes}</span>
          )}
        </button>
        <span className="flex-1" />
        <button type="button" className="btn btn-quiet" onClick={onEdit}>
          Edit
        </button>
        <button type="button" className="btn btn-danger" onClick={onDelete}>
          Delete
        </button>
      </div>
    </article>
  );
}