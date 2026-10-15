import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import HistoryDrawer from "./components/HistoryDrawer.jsx";
import Modal from "./components/Modal.jsx";
import MonitorCard from "./components/MonitorCard.jsx";
import MonitorForm from "./components/MonitorForm.jsx";
import Toasts from "./components/Toasts.jsx";

const FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "changed", label: "Changes", test: (m) => m.status === "changed" },
  { id: "error", label: "Errors", test: (m) => m.status === "error" || m.status === "blocked" },
  { id: "blocked", label: "Blocked", test: (m) => m.status === "blocked" },
  { id: "paused", label: "Paused", test: (m) => m.paused },
];

function SkeletonCard() {
  return <div className="h-64 animate-pulse rounded-lg border border-line bg-panel" aria-hidden="true" />;
}

export default function App() {
  const [monitors, setMonitors] = useState(null);
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [form, setForm] = useState(null); // {monitor?: Monitor}
  const [historyId, setHistoryId] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState({}); // monitorId -> action
  const [waiting, setWaiting] = useState({}); // monitorId -> last_checked_at before manual check
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);

  const toast = useCallback((type, message) => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, type, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === "error" ? 8000 : 4500);
  }, []);
  const dismissToast = (id) => setToasts((t) => t.filter((x) => x.id !== id));

  const refresh = useCallback(async () => {
    try {
      setMonitors(await api.listMonitors());
      setLoadError(null);
    } catch (e) {
      setLoadError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    api.config().then(setConfig).catch(() => {});
  }, [refresh]);

  const anyChecking = monitors?.some((m) => m.checking) ?? false;
  const fast = anyChecking || Object.keys(waiting).length > 0;
  useEffect(() => {
    const t = setInterval(refresh, fast ? 2000 : 15000);
    return () => clearInterval(t);
  }, [refresh, fast]);

  // Report the outcome of checks the user started manually
  useEffect(() => {
    if (!monitors || Object.keys(waiting).length === 0) return;
    const finished = [];
    for (const m of monitors) {
      if (m.id in waiting && !m.checking && m.last_checked_at !== waiting[m.id]) finished.push(m);
    }
    if (finished.length === 0) return;
    setWaiting((w) => {
      const next = { ...w };
      finished.forEach((m) => delete next[m.id]);
      return next;
    });
    finished.forEach((m) => {
      if (m.status === "error") toast("error", `${m.name}: ${m.last_error}`);
      else if (m.status === "changed") toast("success", `${m.name}: change detected.`);
      else toast("success", `${m.name}: checked, no meaningful changes.`);
    });
  }, [monitors, waiting, toast]);

  const setBusyFor = (id, action) =>
    setBusy((b) => {
      const next = { ...b };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });

  async function checkNow(m) {
    setBusyFor(m.id, "check");
    try {
      await api.checkNow(m.id);
      setWaiting((w) => ({ ...w, [m.id]: m.last_checked_at }));
      toast("info", `Checking ${m.name}…`);
    } catch (e) {
      toast(e.status === 409 ? "info" : "error", e.message);
    } finally {
      setBusyFor(m.id, null);
      refresh();
    }
  }

  async function togglePause(m) {
    setBusyFor(m.id, "pause");
    try {
      await (m.paused ? api.resume(m.id) : api.pause(m.id));
      toast("success", m.paused ? `Resumed ${m.name}. It will be checked shortly.` : `Paused ${m.name}.`);
    } catch (e) {
      toast("error", e.message);
    } finally {
      setBusyFor(m.id, null);
      refresh();
    }
  }

  async function createMonitor(payload) {
    const created = await api.createMonitor(payload);
    setForm(null);
    setWaiting((w) => ({ ...w, [created.id]: created.last_checked_at }));
    toast("success", `Added ${created.name}. The first check saves a baseline to compare against.`);
    refresh();
  }

  async function updateMonitor(id, payload) {
    const updated = await api.updateMonitor(id, payload);
    setForm(null);
    toast("success", `Saved changes to ${updated.name}.`);
    refresh();
  }

  function askDelete(m) {
    setConfirm({
      title: `Delete ${m.name}?`,
      message: "This removes the monitor, its change history and its screenshots. This can't be undone.",
      confirmLabel: "Delete monitor",
      danger: true,
      run: async () => {
        await api.deleteMonitor(m.id);
        toast("success", `Deleted ${m.name}.`);
      },
    });
  }

  function askRemoveDemo() {
    setConfirm({
      title: "Remove sample data?",
      message: "Only the sample monitors are removed. Monitors you added stay.",
      confirmLabel: "Remove sample data",
      danger: true,
      run: async () => {
        await api.removeDemo();
        toast("success", "Sample data removed.");
      },
    });
  }

  async function loadDemo() {
    try {
      await api.seedDemo();
      toast("success", "Sample monitors added.");
      refresh();
    } catch (e) {
      toast("error", e.message);
    }
  }

  async function runConfirm() {
    try {
      await confirm.run();
    } catch (e) {
      toast("error", e.message);
    } finally {
      setConfirm(null);
      refresh();
    }
  }

  const counts = useMemo(() => {
    const list = monitors ?? [];
    return Object.fromEntries(FILTERS.map((f) => [f.id, list.filter(f.test).length]));
  }, [monitors]);

  const visible = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter) ?? FILTERS[0];
    return (monitors ?? []).filter(f.test);
  }, [monitors, filter]);

  const historyMonitor = monitors?.find((m) => m.id === historyId) ?? null;
  const hasDemo = monitors?.some((m) => m.is_demo);

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 pt-8 sm:px-6">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Watchtower</h1>
          <p className="mt-1 text-sm text-mute">Get told when a page you care about actually changes.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setForm({})}>
          Add monitor
        </button>
      </header>

      {config && !config.scheduler_enabled && (
        <p className="mb-4 rounded-md border border-warn/40 bg-warn/10 px-4 py-3 text-sm">
          Scheduled checks are turned off on the server. Monitors only run when you press Check now.
        </p>
      )}

      {hasDemo && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-panel px-4 py-3 text-sm">
          <p className="text-mute">
            Sample monitors are simulated. Check now on them invents a change so you can try the dashboard.
          </p>
          <button type="button" className="btn btn-quiet" onClick={askRemoveDemo}>
            Remove sample data
          </button>
        </div>
      )}

      {loadError && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-bad/40 bg-bad/10 px-4 py-3 text-sm" role="alert">
          <p>{loadError}</p>
          <button type="button" className="btn" onClick={refresh}>
            Try again
          </button>
        </div>
      )}

      {monitors && monitors.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-1.5" role="tablist" aria-label="Filter monitors">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={`rounded-md border px-3 py-1 text-sm transition-colors ${
                filter === f.id ? "border-line bg-raised text-ink" : "border-transparent text-mute hover:text-ink"
              }`}
            >
              {f.label} <span className="text-mute">{counts[f.id]}</span>
            </button>
          ))}
        </div>
      )}

      {monitors === null && !loadError && (
        <div className="grid gap-4 lg:grid-cols-2" aria-busy="true" aria-label="Loading monitors">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {monitors && monitors.length === 0 && (
        <div className="rounded-lg border border-dashed border-line px-6 py-16 text-center">
          <h2 className="text-base font-medium">No monitors yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-mute">
            Add a page to watch, such as a product, an announcements page or a results table. Watchtower checks it on a
            schedule and tells you what changed.
          </p>
          <div className="mt-5 flex justify-center gap-2">
            <button type="button" className="btn btn-primary" onClick={() => setForm({})}>
              Add monitor
            </button>
            <button type="button" className="btn" onClick={loadDemo}>
              Load sample data
            </button>
          </div>
        </div>
      )}

      {monitors && monitors.length > 0 && visible.length === 0 && (
        <p className="rounded-lg border border-dashed border-line px-6 py-12 text-center text-sm text-mute">
          No monitors match this filter.
        </p>
      )}

      {visible.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {visible.map((m) => (
            <MonitorCard
              key={m.id}
              monitor={m}
              busy={busy[m.id]}
              onCheck={() => checkNow(m)}
              onTogglePause={() => togglePause(m)}
              onHistory={() => setHistoryId(m.id)}
              onEdit={() => setForm({ monitor: m })}
              onDelete={() => askDelete(m)}
            />
          ))}
        </div>
      )}

      {form && (
        <Modal
          title={form.monitor ? "Edit monitor" : "Add monitor"}
          description={form.monitor ? form.monitor.url : undefined}
          onClose={() => setForm(null)}
        >
          <MonitorForm
            monitor={form.monitor}
            config={config}
            onCancel={() => setForm(null)}
            onSubmit={(payload) =>
              form.monitor ? updateMonitor(form.monitor.id, payload) : createMonitor(payload)
            }
            onTest={() => api.testNotification(form.monitor.id)}
          />
        </Modal>
      )}

      {historyMonitor && (
        <HistoryDrawer monitor={historyMonitor} onClose={() => setHistoryId(null)} onSeen={refresh} />
      )}

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.confirmLabel}
          danger={confirm.danger}
          onConfirm={runConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}

      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}