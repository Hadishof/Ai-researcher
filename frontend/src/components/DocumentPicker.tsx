// The documents this chat searches, shown as chips, plus a "Documents" button that opens
// a checkbox list of the whole library. Changes are saved only when the user clicks Save.

import { Files } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import type { ConversationDocument, DocumentResponse } from "../api/types";
import Button from "./Button";
import { chipName } from "./SourceChips";

interface DocumentPickerProps {
  selected: ConversationDocument[]; // the chat's documents
  library: DocumentResponse[]; // every uploaded document
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (documents: ConversationDocument[]) => Promise<void>;
}

export default function DocumentPicker({
  selected,
  library,
  open,
  onOpenChange,
  onSave,
}: DocumentPickerProps) {
  // The ticks in the list. Kept separate from `selected` until Save, so Cancel undoes them.
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Each time the list opens, start from the chat's current documents.
  useEffect(() => {
    if (open) {
      setChecked(new Set(selected.map((d) => d.document_id)));
      setError(null);
    }
  }, [open, selected]);

  // Escape closes the list without saving.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  function toggle(documentId: string) {
    const next = new Set(checked); // a new Set, so React notices the change
    if (next.has(documentId)) next.delete(documentId);
    else next.add(documentId);
    setChecked(next);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const documents = library
        .filter((d) => checked.has(d.document_id))
        .map((d) => ({ document_id: d.document_id, filename: d.filename }));
      await onSave(documents);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="picker">
      {selected.length === 0 ? (
        <span className="muted">No documents selected</span>
      ) : (
        <ul className="chips" aria-label="Documents in this chat">
          {selected.map((d) => (
            <li key={d.document_id} className="chip" title={d.filename}>
              <span className="chip-name">{chipName(d.filename)}</span>
            </li>
          ))}
        </ul>
      )}

      <Button
        size="sm"
        icon={<Files size={14} aria-hidden />}
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        Documents
      </Button>

      {open && (
        <div className="picker-panel" role="dialog" aria-label="Choose documents for this chat">
          <p className="picker-hint">This chat only searches the documents you tick.</p>
          {library.length === 0 ? (
            <p className="empty">No documents yet — upload a PDF to start.</p>
          ) : (
            <ul className="picker-list">
              {library.map((d) => (
                <li key={d.document_id}>
                  <label className="picker-option">
                    <input
                      type="checkbox"
                      checked={checked.has(d.document_id)}
                      onChange={() => toggle(d.document_id)}
                    />
                    <span className="picker-name" dir="auto">
                      {d.filename}
                    </span>
                    <span className="mono muted">{d.pages} p.</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {error && (
            <p className="notice notice-error" role="alert">
              {error}
            </p>
          )}
          <div className="picker-actions">
            <Button size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={save}
              loading={saving}
              disabled={library.length === 0}
            >
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
