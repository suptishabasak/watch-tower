import { useEffect, useRef } from "react";

export default function Modal({ title, description, onClose, children, variant = "center", size = "md" }) {
  const panelRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement;
    const onKey = (e) => {
      if (e.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    if (panelRef.current && !panelRef.current.contains(document.activeElement)) {
      panelRef.current.focus();
    }
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previous?.focus?.();
    };
  }, []);

  const widths = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl" };
  const isDrawer = variant === "drawer";

  return (
    <div
      className={`fixed inset-0 z-40 flex ${isDrawer ? "justify-end" : "items-start justify-center p-4 sm:items-center"}`}
    >
      <div className="absolute inset-0 bg-black/60" onMouseDown={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`relative flex w-full flex-col border border-line bg-panel shadow-2xl focus:outline-none ${
          isDrawer ? "h-full max-w-2xl border-y-0 border-r-0" : `max-h-[90vh] rounded-lg ${widths[size]}`
        }`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{title}</h2>
            {description && <p className="mt-0.5 truncate text-sm text-mute">{description}</p>}
          </div>
          <button type="button" className="btn btn-quiet -mr-2 px-2" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
            </svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}