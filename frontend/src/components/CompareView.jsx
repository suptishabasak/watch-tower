import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { fullDate } from "../lib/format.js";
import DiffView from "./DiffView.jsx";

const PIXEL_THRESHOLD = 40; // summed RGB difference below this is treated as compression noise

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not load screenshot."));
    img.src = src;
  });
}

/** Pixel diff in the browser: changed pixels are painted red over a dimmed copy of the newer screenshot. */
function ScreenshotDiff({ before, after }) {
  const canvasRef = useRef(null);
  const [state, setState] = useState({ status: "loading", percent: 0, message: "" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", percent: 0, message: "" });
    (async () => {
      try {
        const [a, b] = await Promise.all([loadImage(before), loadImage(after)]);
        if (cancelled) return;
        const w = b.naturalWidth;
        const h = b.naturalHeight;
        const read = (img) => {
          const c = document.createElement("canvas");
          c.width = w;
          c.height = h;
          const ctx = c.getContext("2d", { willReadFrequently: true });
          ctx.drawImage(img, 0, 0, w, h);
          return ctx.getImageData(0, 0, w, h);
        };
        const da = read(a);
        const db = read(b);
        const canvas = canvasRef.current;
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        const out = ctx.createImageData(w, h);
        let changed = 0;
        for (let i = 0; i < out.data.length; i += 4) {
          const d =
            Math.abs(da.data[i] - db.data[i]) +
            Math.abs(da.data[i + 1] - db.data[i + 1]) +
            Math.abs(da.data[i + 2] - db.data[i + 2]);
          if (d > PIXEL_THRESHOLD) {
            changed++;
            out.data[i] = 255;
            out.data[i + 1] = 40;
            out.data[i + 2] = 60;
            out.data[i + 3] = 255;
          } else {
            const gray = (db.data[i] + db.data[i + 1] + db.data[i + 2]) / 3;
            const v = 255 - (255 - gray) * 0.35; // washed-out background
            out.data[i] = out.data[i + 1] = out.data[i + 2] = v;
            out.data[i + 3] = 255;
          }
        }
        ctx.putImageData(out, 0, 0);
        if (!cancelled) setState({ status: "done", percent: (changed / (w * h)) * 100, message: "" });
      } catch (e) {
        if (!cancelled) setState({ status: "error", percent: 0, message: e.message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [before, after]);

  return (
    <div>
      {state.status === "loading" && <p className="mb-2 text-sm text-mute">Comparing screenshots…</p>}
      {state.status === "error" && <p className="mb-2 text-sm text-bad">{state.message}</p>}
      {state.status === "done" && (
        <p className="mb-2 text-sm text-mute">
          {state.percent < 0.01 ? "No visible pixel differences." : `${state.percent.toFixed(2)}% of pixels differ (shown in red).`}
        </p>
      )}
      <canvas ref={canvasRef} className="w-full rounded border border-line" style={{ display: state.status === "error" ? "none" : "block" }} />
    </div>
  );
}

function SideBySide({ before, after }) {
  const Shot = ({ src, label }) => (
    <figure className="min-w-0 flex-1">
      <figcaption className="mb-1 text-xs text-mute">{label}</figcaption>
      {src ? (
        <a href={src} target="_blank" rel="noopener noreferrer">
          <img src={src} alt={`${label} screenshot`} className="w-full rounded border border-line" />
        </a>
      ) : (
        <div className="flex aspect-video items-center justify-center rounded border border-dashed border-line text-xs text-mute">
          No screenshot saved
        </div>
      )}
    </figure>
  );
  return (
    <div className="flex gap-3">
      <Shot src={before.screenshot} label={`Before · ${fullDate(before.created_at)}`} />
      <Shot src={after.screenshot} label={`After · ${fullDate(after.created_at)}`} />
    </div>
  );
}

const TABS = [
  { id: "text", label: "Text diff" },
  { id: "side", label: "Side by side" },
  { id: "visual", label: "Highlighted screenshot" },
];

export default function CompareView({ monitor }) {
  const [snaps, setSnaps] = useState(null);
  const [error, setError] = useState(null);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("text");

  useEffect(() => {
    let cancelled = false;
    api
      .snapshots(monitor.id)
      .then((rows) => {
        if (cancelled) return;
        setSnaps(rows);
        if (rows.length >= 2) {
          setB(String(rows[0].id));
          setA(String(rows[1].id));
        }
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [monitor.id, monitor.last_changed_at]);

  useEffect(() => {
    if (!a || !b) return;
    let cancelled = false;
    setBusy(true);
    setError(null);
    api
      .compare(monitor.id, a, b)
      .then((r) => !cancelled && setResult(r))
      .catch((e) => !cancelled && (setError(e.message), setResult(null)))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [monitor.id, a, b]);

  if (error && !snaps) return <p className="rounded-md border border-bad/40 bg-bad/10 p-4 text-sm">{error}</p>;
  if (!snaps) return <div className="h-28 animate-pulse rounded-md bg-raised" aria-busy="true" />;
  if (snaps.length < 2) {
    return (
      <div className="rounded-md border border-dashed border-line p-8 text-center">
        <p className="font-medium">Not enough versions yet</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-mute">
          {snaps.length === 0 ? "The first check saves the first version." : "A second version is saved when the page content changes."}{" "}
          Then you can compare any two here.
        </p>
      </div>
    );
  }

  const label = (s, i) => `${fullDate(s.created_at)}${i === 0 ? " (latest)" : ""}`;
  const Select = ({ value, onChange, name }) => (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-mute">
      {name}
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {snaps.map((s, i) => (
          <option key={s.id} value={s.id}>
            {label(s, i)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <Select name="Version A" value={a} onChange={setA} />
        <Select name="Version B" value={b} onChange={setB} />
      </div>

      {a === b && <p className="text-sm text-mute">Pick two different versions to compare.</p>}
      {error && <p className="rounded-md border border-bad/40 bg-bad/10 p-3 text-sm">{error}</p>}

      <div role="tablist" className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm ${tab === t.id ? "border-b-2 border-accent font-medium" : "text-mute hover:text-ink"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {busy && <div className="h-20 animate-pulse rounded-md bg-raised" aria-busy="true" />}

      {result && !busy && a !== b && (
        <>
          {tab === "text" &&
            (result.changes.length === 0 ? (
              <p className="text-sm text-mute">The saved text of these two versions is identical.</p>
            ) : (
              <DiffView items={result.changes} omitted={result.omitted} />
            ))}
          {tab === "side" && <SideBySide before={result.before} after={result.after} />}
          {tab === "visual" &&
            (result.before.screenshot && result.after.screenshot ? (
              <ScreenshotDiff before={result.before.screenshot} after={result.after.screenshot} />
            ) : (
              <p className="text-sm text-mute">One of these versions has no saved screenshot.</p>
            ))}
        </>
      )}
    </div>
  );
}
