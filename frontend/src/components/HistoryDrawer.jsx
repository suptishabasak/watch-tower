import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { fullDate, timeAgo } from "../lib/format.js";
import CompareView from "./CompareView.jsx";
import DiffView from "./DiffView.jsx";
import Modal from "./Modal.jsx";

function Screenshots({ change }) {
  if (!change.before_screenshot && !change.after_screenshot) return null;
  const Shot = ({ src, label }) => (
    <figure className="min-w-0 flex-1">
      <figcaption className="mb-1 text-xs text-mute">{label}</figcaption>
      {src ? (
        <a href={src} target="_blank" rel="noopener noreferrer">
          <img src={src} alt={`${label} screenshot`} loading="lazy" className="w-full rounded border border-line" />
        </a>
      ) : (
        <div className="flex aspect-video items-center justify-center rounded border border-dashed border-line text-xs text-mute">
          No screenshot
        </div>
      )}
    </figure>
  );
  return (
    <details className="mt-3 rounded-md border border-line">
      <summary className="cursor-pointer px-3 py-2 text-sm text-mute hover:text-ink">Screenshots</summary>
      <div className="flex gap-3 border-t border-line p-3">
        <Shot src={change.before_screenshot} label="Before" />
        <Shot src={change.after_screenshot} label="After" />
      </div>
    </details>
  );
}

function Counts({ change }) {
  const parts = [
    change.added_count && { text: `${change.added_count} added`, cls: "text-good" },
    change.modified_count && { text: `${change.modified_count} modified`, cls: "text-warn" },
    change.removed_count && { text: `${change.removed_count} removed`, cls: "text-bad" },
  ].filter(Boolean);
  return (
    <span className="flex flex-wrap gap-x-3 text-xs">
      {parts.map((p) => (
        <span key={p.text} className={p.cls}>
          {p.text}
        </span>
      ))}
    </span>
  );
}

export default function HistoryDrawer({ monitor, onClose, onSeen }) {
  const [changes, setChanges] = useState(null);
  const [error, setError] = useState(null);
  const markedRef = useRef(false);
  const [view, setView] = useState("changes"); // changes | compare

  async function load() {
    setChanges(null);
    setError(null);
    try {
      setChanges(await api.changes(monitor.id));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    if (!markedRef.current && monitor.unseen_changes > 0) {
      markedRef.current = true;
      api.markSeen(monitor.id).then(onSeen).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monitor.id]);

  return (
    <Modal variant="drawer" title={`${monitor.name}: change history`} description={monitor.url} onClose={onClose}>
      <div className="mb-4 flex gap-1 border-b border-line" role="tablist">
        {[["changes", "Change timeline"], ["compare", "Compare versions"]].map(([id, text]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={view === id}
            onClick={() => setView(id)}
            className={`px-3 py-2 text-sm ${view === id ? "border-b-2 border-accent font-medium" : "text-mute hover:text-ink"}`}
          >
            {text}
          </button>
        ))}
      </div>

      {view === "compare" && <CompareView monitor={monitor} />}

      {view === "changes" && error && (
        <div className="rounded-md border border-bad/40 bg-bad/10 p-4 text-sm">
          <p>{error}</p>
          <button type="button" className="btn mt-3" onClick={load}>
            Try again
          </button>
        </div>
      )}

      {view === "changes" && !error && changes === null && (
        <div className="space-y-4" aria-busy="true" aria-label="Loading history">
          {[0, 1].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-md bg-raised" />
          ))}
        </div>
      )}

      {view === "changes" && changes && changes.length === 0 && (
        <div className="rounded-md border border-dashed border-line p-8 text-center">
          <p className="font-medium">No changes yet</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-mute">
            The first check saves a baseline. Changes appear here when the page differs from it.
          </p>
        </div>
      )}

      {view === "changes" && changes && changes.length > 0 && (
        <ol className="space-y-6">
          {changes.map((c) => (
            <li key={c.id}>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <div>
                  <p className="text-sm font-medium">{fullDate(c.detected_at)}</p>
                  <p className="text-xs text-mute">{timeAgo(c.detected_at)}</p>
                </div>
                <Counts change={c} />
              </div>
              <DiffView items={c.changes} omitted={c.omitted} />
              <Screenshots change={c} />
              <p className="mt-2 text-xs text-mute">
                {c.notified ? "Discord notification sent." : c.notification_note || "No notification was sent."}
              </p>
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}