// The main area: the chat's documents at the top, the message history, and the question box.

import { LoaderCircle, Menu, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Ref } from "react";

import { ApiError } from "../api/client";
import type { ConversationDocument, DocumentResponse, MessageResponse } from "../api/types";
import Button from "./Button";
import ChatInput from "./ChatInput";
import DocumentPicker from "./DocumentPicker";
import Message from "./Message";

/** The chat on screen. `id` is null for a new chat that is not saved yet. */
export interface OpenChat {
  id: number | null;
  title: string | null;
  documents: ConversationDocument[];
  messages: MessageResponse[];
}

interface ChatViewProps {
  chat: OpenChat;
  library: DocumentResponse[];
  loading: boolean; // the chat is being loaded from the backend
  onSend: (question: string) => Promise<void>;
  onChangeDocuments: (documents: ConversationDocument[]) => Promise<void>;
  onUploadClick: () => void;
  onOpenSidebar: () => void;
  // Wide screens: the sidebar was collapsed, so show the button that brings it back.
  // (Narrow screens always show it: there the sidebar is a drawer.)
  sidebarCollapsed: boolean;
  openSidebarButtonRef: Ref<HTMLButtonElement>; // App moves the keyboard focus here on collapse
}

export default function ChatView({
  chat,
  library,
  loading,
  onSend,
  onChangeDocuments,
  onUploadClick,
  onOpenSidebar,
  sidebarCollapsed,
  openSidebarButtonRef,
}: ChatViewProps) {
  // Source chips link to a PDF only if the document is still in the library with its file.
  const viewable = useMemo(
    () => new Set(library.filter((d) => d.has_file).map((d) => d.document_id)),
    [library],
  );
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const hasDocuments = chat.documents.length > 0;
  const isEmpty = chat.messages.length === 0;

  // Opening another chat: clear what belonged to the previous one.
  useEffect(() => {
    setDraft("");
    setError(null);
    setPickerOpen(false);
  }, [chat.id]);

  // Scroll to the newest message whenever one is added (or "Searching..." appears).
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [chat.messages.length, sending]);

  async function send() {
    const question = draft.trim();
    setDraft("");
    setError(null);
    setSending(true);
    try {
      await onSend(question);
    } catch (err) {
      // Nothing was saved, so give the question back to make retrying easy.
      setDraft(question);
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="chat">
      <header className="chat-header">
        <div className="column chat-header-inner">
          <div className="chat-title-row">
            <Button
              ref={openSidebarButtonRef}
              variant="ghost"
              size="sm"
              className={`menu-button ${sidebarCollapsed ? "menu-button-visible" : ""}`}
              aria-label="Open sidebar"
              icon={<Menu size={18} aria-hidden />}
              onClick={onOpenSidebar}
            />
            <h1 className="chat-title" dir="auto">
              {chat.title ?? "New chat"}
            </h1>
          </div>
          <DocumentPicker
            selected={chat.documents}
            library={library}
            open={pickerOpen}
            onOpenChange={setPickerOpen}
            onSave={onChangeDocuments}
          />
        </div>
      </header>

      <div className="chat-scroll">
        <div className="column thread">
          {loading ? (
            <p className="status">
              <LoaderCircle className="spin" size={16} aria-hidden /> Loading chat…
            </p>
          ) : isEmpty && !hasDocuments ? (
            <div className="empty-state">
              <h2>Choose the documents for this chat</h2>
              <p>
                This chat only searches the documents you select, so answers never mix in
                information from other files.
              </p>
              {library.length === 0 && <p>No documents yet — upload a PDF to start.</p>}
              <div className="empty-actions">
                {library.length > 0 && (
                  <Button variant="primary" onClick={() => setPickerOpen(true)}>
                    Choose documents
                  </Button>
                )}
                <Button icon={<Upload size={16} aria-hidden />} onClick={onUploadClick}>
                  Upload a PDF
                </Button>
              </div>
            </div>
          ) : isEmpty ? (
            <div className="empty-state">
              <p>Ask a question about the selected documents.</p>
            </div>
          ) : (
            chat.messages.map((message) => (
              <Message key={message.id} message={message} viewable={viewable} />
            ))
          )}

          {sending && (
            <p className="status">
              <LoaderCircle className="spin" size={16} aria-hidden /> Searching documents…
            </p>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="column chat-footer">
        {error && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}
        {!hasDocuments && !isEmpty && (
          <p className="hint">Select at least one document to ask a question.</p>
        )}
        <ChatInput
          value={draft}
          onChange={setDraft}
          onSubmit={send}
          disabled={!hasDocuments || loading}
          sending={sending}
          placeholder={
            hasDocuments ? "Ask a question about the selected documents…" : "Select documents first"
          }
        />
      </div>
    </main>
  );
}
