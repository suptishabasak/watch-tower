const TONES = {
  success: "border-l-good",
  error: "border-l-bad",
  info: "border-l-accent",
};

export default function Toasts({ toasts, onDismiss }) {
  return (
    <div
      className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto sm:w-96"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`pointer-events-auto flex w-full items-start gap-3 rounded-md border border-line border-l-4 bg-raised px-4 py-3 text-sm shadow-lg ${TONES[t.type] ?? TONES.info}`}
        >
          <p className="min-w-0 flex-1 break-words">{t.message}</p>
          <button type="button" className="text-mute hover:text-ink" onClick={() => onDismiss(t.id)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}