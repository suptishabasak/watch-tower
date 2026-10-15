import { useState } from "react";
import Modal from "./Modal.jsx";

export default function ConfirmDialog({ title, message, confirmLabel, danger = false, onConfirm, onCancel }) {
  const [working, setWorking] = useState(false);

  async function handle() {
    setWorking(true);
    try {
      await onConfirm();
    } finally {
      setWorking(false);
    }
  }

  return (
    <Modal title={title} onClose={onCancel} size="sm">
      <p className="text-sm text-mute">{message}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button type="button" className="btn" onClick={onCancel} disabled={working}>
          Cancel
        </button>
        <button type="button" className={`btn ${danger ? "btn-danger-solid" : "btn-primary"}`} onClick={handle} disabled={working}>
          {working && <span className="spinner" aria-hidden="true" />}
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}