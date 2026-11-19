// The document library: upload a PDF (it is added to the open chat), see every document,
// open its PDF in a new tab, and delete one, with a warning when chats use it.

import { ExternalLink, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import type { ChangeEvent, RefObject } from "react";

import { ApiError, api } from "../api/client";
import type { ConversationDocument, DocumentResponse } from "../api/types";
import Button from "./Button";
import ConfirmDialog from "./ConfirmDialog";

interface DocumentsPanelProps {
  documents: DocumentResponse[];
  // The hidden file input. App holds it, so the chat's empty state can open it too.
  inputRef: RefObject<HTMLInputElement | null>;
  onLibraryChanged: () => Promise<void>; // reload the document list
  onAddToChat: (document: ConversationDocument) => Promise<void>;
  onDeleted: (documentId: string) => Promise<void>;
}

interface Notice {
  kind: "success" | "error";
  text: string;
}

function deleteWarning(document: DocumentResponse): string {
  const count = document.conversation_count;
  if (count === 0) return `"${document.filename}" will be deleted. This can't be undone.`;
  const chats = count === 1 ? "1 chat" : `${count} chats`;
  const those = count === 1 ? "that chat" : "those chats";
  return `This document is used in ${chats}. Deleting it removes it from ${those}. This can't be undone.`;
}

export default function DocumentsPanel({
  documents,
  inputRef,
  onLibraryChanged,
  onAddToChat,
  onDeleted,
}: DocumentsPanelProps) {
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [deleting, setDeleting] = useState<DocumentResponse | null>(null);

  async function addToChat(document: ConversationDocument, success: string) {
    try {
      await onAddToChat(document);
      setNotice({ kind: "success", text: success });
    } catch (err) {
      const reason = err instanceof ApiError ? ` ${err.message}` : "";
      setNotice({ kind: "error", text: `In your library, but couldn't add it to this chat.${reason}` });
    }
  }

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // so choosing the same file again still triggers a change
    if (!file) return;

    setUploading(true);
    setNotice(null);
    try {
      const uploaded = await api.uploadDocument(file);
      await onLibraryChanged();
      await addToChat(uploaded, `Uploaded "${uploaded.filename}" and added it to this chat.`);
    } catch (err) {
      if (err instanceof ApiError && err.duplicate) {
        // 409: the same file is already in the library, so use that copy.
        const { document_id, filename } = err.duplicate;
        await addToChat({ document_id, filename }, "Already in your library — added to this chat.");
      } else {
        // 400, 413, 422, 429, 502...: the backend's message explains what went wrong.
        setNotice({
          kind: "error",
          text: err instanceof ApiError ? err.message : "The upload failed. Please try again.",
        });
      }
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="library" aria-labelledby="library-heading">
      <div className="section-header">
        <h2 id="library-heading" className="section-title">
          Library
        </h2>
        <Button
          size="sm"
          loading={uploading}
          icon={<Upload size={14} aria-hidden />}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? "Uploading…" : "Upload PDF"}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          data-testid="file-input"
          onChange={handleFile}
        />
      </div>

      {notice && (
        <p
          className={`notice ${notice.kind === "error" ? "notice-error" : "notice-success"}`}
          role={notice.kind === "error" ? "alert" : "status"}
        >
          {notice.text}
        </p>
      )}

      {documents.length === 0 ? (
        <p className="empty">No documents yet — upload a PDF to start.</p>
      ) : (
        <ul className="document-list" aria-label="Documents">
          {documents.map((document) => (
            <li key={document.document_id} className="document-row">
              <div className="document-info">
                <span className="document-name" dir="auto" title={document.filename}>
                  {document.filename}
                </span>
                <span className="document-meta">
                  <span className="mono">{document.pages}</span> pages ·{" "}
                  <span className="mono">{document.chunks}</span> chunks
                </span>
              </div>
              <div className="row-actions">
                {document.has_file && (
                  // A real link, not a button: it opens a new tab, and the browser's
                  // "open in new tab" and middle-click work too. Same look as the icon buttons.
                  <a
                    className="btn btn-ghost btn-sm btn-icon"
                    href={api.fileUrl(document.document_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`View ${document.filename}`}
                    title="Open the PDF in a new tab"
                  >
                    <ExternalLink size={14} aria-hidden />
                  </a>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="ghost-danger"
                  aria-label={`Delete ${document.filename}`}
                  icon={<Trash2 size={14} aria-hidden />}
                  onClick={() => setDeleting(document)}
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete this document?"
          message={deleteWarning(deleting)}
          confirmLabel="Delete document"
          onConfirm={async () => {
            await api.deleteDocument(deleting.document_id);
            setDeleting(null);
            await onDeleted(deleting.document_id);
          }}
          onCancel={() => setDeleting(null)}
        />
      )}
    </section>
  );
}
