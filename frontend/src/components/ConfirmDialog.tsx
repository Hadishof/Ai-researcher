// A confirmation step in the app's own style (instead of the browser's confirm() popup).
// Escape or clicking outside cancels; focus starts on Cancel, the safe choice.

import { useEffect, useId, useRef, useState } from "react";

import { ApiError } from "../api/client";
import Button from "./Button";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>; // the dialog shows a spinner while this runs
  onCancel: () => void;
}

export default function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId(); // unique ids link the dialog to its title and text for screen readers
  const messageId = useId();

  // When the dialog appears, put the keyboard focus on Cancel.
  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  // Escape cancels (but not while the action is running).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown); // clean up
  }, [busy, onCancel]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={busy ? undefined : onCancel}>
      <div
        className="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        onMouseDown={(event) => event.stopPropagation()} // clicks inside don't cancel
      >
        <h2 id={titleId} className="dialog-title">
          {title}
        </h2>
        <p id={messageId} className="dialog-message">
          {message}
        </p>
        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          <Button ref={cancelRef} onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} loading={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
