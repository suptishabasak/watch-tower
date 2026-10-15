import { useState } from "react";
import { INTERVALS } from "../lib/format.js";
import { api } from "../api.js";
import { useRef } from "react";

function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded border-line bg-bg accent-[#7f8cf5]"
      />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-mute">{hint}</span>}
      </span>
    </label>
  );
}

export default function MonitorForm({ monitor, config, onSubmit, onCancel, onTest }) {
  const editing = Boolean(monitor);
  const [name, setName] = useState(monitor?.name ?? "");
  const [url, setUrl] = useState(monitor?.url ?? "");
  const [interval, setIntervalValue] = useState(monitor?.interval_minutes ?? 60);
  const [focus, setFocus] = useState(monitor?.focus ?? "");
  const [sensitivity, setSensitivity] = useState(monitor?.sensitivity ?? 2);
  const [notifyEmail, setNotifyEmail] = useState(monitor?.notify_email ?? false);
  const [notifyTelegram, setNotifyTelegram] = useState(monitor?.notify_telegram ?? false);
  const [notifyDiscord, setNotifyDiscord] = useState(monitor?.notify_discord ?? true);
  const [notifyOnError, setNotifyOnError] = useState(monitor?.notify_on_error ?? false);
  const [webhook, setWebhook] = useState("");
  const [removeWebhook, setRemoveWebhook] = useState(false);
  const [watchSelectors, setWatchSelectors] = useState(monitor?.watch_selectors ?? []);
  const [ignoreSelectors, setIgnoreSelectors] = useState(monitor?.ignore_selectors ?? []);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerMode, setPickerMode] = useState("watch");
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const frameRef = useRef(null);
  const pickerModeRef = useRef(pickerMode);
  pickerModeRef.current = pickerMode;

  async function openPicker() {
    if (!url.trim()) { setError("Enter a URL before choosing regions."); return; }
    setPickerOpen(true); setPreviewLoading(true); setPreviewError("");
    try { setPreview(await api.regionPreview(url.trim())); }
    catch (err) { setPreviewError(err.message); }
    finally { setPreviewLoading(false); }
  }

  function makeSelector(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node.tagName.toLowerCase() !== "html") {
      let part = node.tagName.toLowerCase();
      const classes = [...node.classList].filter(c => /^[a-zA-Z_-][\w-]*$/.test(c)).slice(0, 2);
      if (classes.length) part += classes.map(c => `.${CSS.escape(c)}`).join("");
      else if (node.parentElement) {
        const siblings = [...node.parentElement.children].filter(x => x.tagName === node.tagName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      const candidate = parts.join(" > ");
      try { if (node.ownerDocument.querySelectorAll(candidate).length === 1) return candidate; } catch {}
      node = node.parentElement;
    }
    return parts.join(" > ");
  }

  function onPreviewLoad() {
    const doc = frameRef.current?.contentDocument;
    if (!doc || doc.body.dataset.pickerReady) return;
    doc.body.dataset.pickerReady = "1";
    const style = doc.createElement("style");
    style.textContent = `*{cursor:crosshair!important} .wt-hover{outline:3px solid #7f8cf5!important;outline-offset:1px!important;background-color:rgba(127,140,245,.12)!important} .wt-picked-watch{outline:3px solid #22c55e!important} .wt-picked-ignore{outline:3px solid #f97316!important}`;
    doc.head?.appendChild(style);
    doc.addEventListener("mouseover", e => { const el=e.target; if(el?.classList){doc.querySelectorAll('.wt-hover').forEach(n=>n.classList.remove('wt-hover'));el.classList.add('wt-hover');}}, true);
    doc.addEventListener("click", e => {
      e.preventDefault(); e.stopPropagation();
      const el=e.target; if(!el || !el.tagName) return;
      const selector=makeSelector(el);
      if(!selector) return;
      if(pickerModeRef.current === "watch") setWatchSelectors(prev => prev.includes(selector) ? prev : [...prev, selector].slice(-30));
      else setIgnoreSelectors(prev => prev.includes(selector) ? prev : [...prev, selector].slice(-30));
      el.classList.add(pickerModeRef.current === "watch" ? "wt-picked-watch" : "wt-picked-ignore");
    }, true);
  }


  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [test, setTest] = useState(null); // {state: "sending"|"ok"|"error", message}

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) return setError("Give this monitor a name.");
    if (!url.trim()) return setError("Enter the URL of the page to watch.");

    const payload = {
      name: name.trim(),
      url: url.trim(),
      interval_minutes: interval,
      focus: focus.trim(),
      sensitivity: Number(sensitivity),
      notify_email: notifyEmail,
      notify_telegram: notifyTelegram,
      notify_discord: notifyDiscord,
      notify_on_error: notifyOnError,
      watch_selectors: watchSelectors,
      ignore_selectors: ignoreSelectors,
    };
    if (removeWebhook) payload.discord_webhook_url = "";
    else if (webhook.trim()) payload.discord_webhook_url = webhook.trim();

    setSubmitting(true);
    try {
      await onSubmit(payload);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  async function handleTest() {
    setTest({ state: "sending" });
    try {
      await onTest();
      setTest({ state: "ok", message: "Test message sent. Check your Discord channel." });
    } catch (err) {
      setTest({ state: "error", message: err.message });
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <div>
        <label className="label" htmlFor="mf-url">
          Page URL
        </label>
        <input
          id="mf-url"
          className="input"
          type="url"
          inputMode="url"
          placeholder="https://example.com/product"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          autoFocus={!editing}
        />
        <p className="hint">Public http or https pages only.</p>
      </div>

      <div>
        <label className="label" htmlFor="mf-name">
          Name
        </label>
        <input
          id="mf-name"
          className="input"
          placeholder="Trail runner price"
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <fieldset>
        <legend className="label">Check every</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {INTERVALS.map((opt) => (
            <label
              key={opt.value}
              className={`cursor-pointer rounded-md border px-3 py-2 text-center text-sm transition-colors ${
                interval === opt.value ? "border-accent bg-accent/10 text-ink" : "border-line text-mute hover:text-ink"
              }`}
            >
              <input
                type="radio"
                name="interval"
                className="sr-only"
                checked={interval === opt.value}
                onChange={() => setIntervalValue(opt.value)}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label className="label" htmlFor="mf-focus">
          What do you care about? <span className="font-normal text-mute">(optional)</span>
        </label>
        <input
          id="mf-focus"
          className="input"
          placeholder="price, availability, registration open"
          maxLength={200}
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
        />
        <p className="hint">
          Separate topics with commas. Only changes that mention these are reported. Use “price” for any price change.
          Leave blank to report every meaningful change.
        </p>
      </div>

      <div>
        <label className="label" htmlFor="mf-sensitivity">Change sensitivity</label>
        <select id="mf-sensitivity" className="input" value={sensitivity} onChange={(e) => setSensitivity(Number(e.target.value))}>
          <option value={1}>Strict — report small changes</option>
          <option value={2}>Balanced — recommended</option>
          <option value={3}>High signal — filter tiny changes</option>
        </select>
        <p className="hint">Strict is more responsive; high signal reduces minor-change alerts.</p>
      </div>

      <section className="space-y-3 rounded-md border border-line p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><h3 className="text-sm font-medium">Visual regions</h3><p className="hint">Choose page elements to watch or ignore instead of monitoring all text.</p></div>
          <button type="button" className="btn" onClick={openPicker}>Choose regions visually</button>
        </div>
        {(watchSelectors.length > 0 || ignoreSelectors.length > 0) && <div className="space-y-2 text-xs">
          {watchSelectors.map(s => <div key={`w-${s}`} className="flex items-center gap-2"><span className="text-good">Watch</span><code className="min-w-0 flex-1 break-all">{s}</code><button type="button" className="btn btn-quiet" onClick={() => setWatchSelectors(v=>v.filter(x=>x!==s))}>Remove</button></div>)}
          {ignoreSelectors.map(s => <div key={`i-${s}`} className="flex items-center gap-2"><span className="text-warn">Ignore</span><code className="min-w-0 flex-1 break-all">{s}</code><button type="button" className="btn btn-quiet" onClick={() => setIgnoreSelectors(v=>v.filter(x=>x!==s))}>Remove</button></div>)}
          <button type="button" className="text-xs text-mute underline" onClick={() => {setWatchSelectors([]);setIgnoreSelectors([]);}}>Clear all regions</button>
        </div>}
      </section>

      {pickerOpen && <div className="fixed inset-0 z-[60] flex flex-col bg-bg/95 p-3 sm:p-5" role="dialog" aria-modal="true" aria-label="Visual region picker">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-3">
          <div><h2 className="font-semibold">Choose page regions</h2><p className="text-xs text-mute">Click an element in the preview to add its CSS selector.</p></div>
          <div className="flex flex-wrap gap-2"><button type="button" className={`btn ${pickerMode === "watch" ? "btn-primary" : ""}`} onClick={() => setPickerMode("watch")}>Watch (green)</button><button type="button" className={`btn ${pickerMode === "ignore" ? "btn-primary" : ""}`} onClick={() => setPickerMode("ignore")}>Ignore (orange)</button><button type="button" className="btn" onClick={() => setPickerOpen(false)}>Done</button></div>
        </div>
        {previewLoading && <p className="p-6 text-sm text-mute">Loading a safe page preview…</p>}
        {previewError && <p className="rounded border border-bad/40 p-4 text-sm text-bad">{previewError}</p>}
        {preview && !previewLoading && <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-line bg-white"><iframe ref={frameRef} title="Page region selection preview" sandbox="allow-same-origin" srcDoc={`<!doctype html><html><head><meta charset="utf-8"><base href="${preview.url.replace(/&/g,"&amp;").replace(/"/g,"&quot;")}">${preview.styles || ""}<style>body{font-family:Arial,sans-serif;padding:16px;color:#222} img{max-width:100%;height:auto} a{pointer-events:none} body:before{content:"Preview only — scripts and forms disabled";display:block;padding:8px;background:#fff3cd;margin-bottom:12px;font-size:12px}</style></head>${preview.html}</html>`} onLoad={onPreviewLoad} className="h-full w-full" /></div>}
        <p className="mt-2 text-xs text-mute">Preview is a static, script-free snapshot. Some dynamic layouts may look different from the live page.</p>
      </div>}

      <fieldset className="space-y-3 rounded-md border border-line p-4">
        <legend className="px-1 text-sm font-medium">Notifications</legend>
        <Toggle checked={notifyDiscord} onChange={setNotifyDiscord} label="Send changes to Discord" />
        <Toggle checked={notifyEmail} onChange={setNotifyEmail} label="Send changes by email"
          hint={config?.email_configured ? "Email is configured on the backend." : "Requires SMTP settings in backend/.env."} />
        <Toggle checked={notifyTelegram} onChange={setNotifyTelegram} label="Send changes to Telegram"
          hint={config?.telegram_configured ? "Telegram bot is configured on the backend." : "Requires bot token and chat ID in backend/.env."} />
        <Toggle
          checked={notifyOnError}
          onChange={setNotifyOnError}
          label="Also tell me if this page keeps failing"
          hint="Sent once after 3 failed checks in a row."
        />

        <div>
          <label className="label" htmlFor="mf-webhook">
            Discord webhook URL <span className="font-normal text-mute">(optional)</span>
          </label>
          <input
            id="mf-webhook"
            className="input font-mono text-xs"
            type="password"
            autoComplete="off"
            placeholder={
              monitor?.has_custom_webhook && !removeWebhook
                ? "Saved. Leave blank to keep it."
                : "https://discord.com/api/webhooks/..."
            }
            value={webhook}
            onChange={(e) => {
              setWebhook(e.target.value);
              setRemoveWebhook(false);
            }}
          />
          <p className="hint">
            {config?.discord_configured
              ? "Leave blank to use the server's default webhook."
              : "No default webhook is set on the server, so add one here or in the backend .env file."}{" "}
            It's stored on the server and never shown again.
          </p>
          {monitor?.has_custom_webhook && (
            <label className="mt-2 flex items-center gap-2 text-xs text-mute">
              <input
                type="checkbox"
                checked={removeWebhook}
                onChange={(e) => {
                  setRemoveWebhook(e.target.checked);
                  if (e.target.checked) setWebhook("");
                }}
                className="accent-[#7f8cf5]"
              />
              Remove the saved webhook
            </label>
          )}
        </div>

        {editing && (
          <div>
            <button type="button" className="btn" onClick={handleTest} disabled={test?.state === "sending"}>
              {test?.state === "sending" && <span className="spinner" aria-hidden="true" />}
              Send test message
            </button>
            <p className="hint">Uses the webhook that is already saved. Save any webhook change first.</p>
            {test && test.state !== "sending" && (
              <p className={`mt-2 text-sm ${test.state === "ok" ? "text-good" : "text-bad"}`} role="status">
                {test.message}
              </p>
            )}
          </div>
        )}
      </fieldset>

      {error && (
        <p className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <button type="button" className="btn" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting && <span className="spinner" aria-hidden="true" />}
          {editing ? "Save changes" : "Add monitor"}
        </button>
      </div>
    </form>
  );
}