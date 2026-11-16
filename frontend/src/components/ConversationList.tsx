// The saved chats, newest first. Each row opens the chat, and has rename and delete actions.

import { Check, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import type { ConversationSummary } from "../api/types";
import Button from "./Button";
import ConfirmDialog from "./ConfirmDialog";

interface ConversationListProps {
  conversations: ConversationSummary[];
  activeId: number | null;
  onOpen: (id: number) => void;
  onRename: (id: number, title: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

export default function ConversationList({
  conversations,
  activeId,
  onOpen,
  onRename,
  onDelete,
}: ConversationListProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deleting, setDeleting] = useState<ConversationSummary | null>(null);

  if (conversations.length === 0) {
    return <p className="empty">No chats yet</p>;
  }

  function startRename(conversation: ConversationSummary) {
    setEditingId(conversation.id);
    setEditTitle(conversation.title ?? "");
  }

  async function saveRename(event: FormEvent) {
    event.preventDefault();
    const title = editTitle.trim();
    if (editingId !== null && title) {
      await onRename(editingId, title).catch(() => undefined); // the list simply keeps the old name
    }
    setEditingId(null);
  }

  return (
    <>
      <ul className="conversation-list" aria-label="Chats">
        {conversations.map((conversation) => {
          const title = conversation.title ?? "New chat";
          if (conversation.id === editingId) {
            return (
              <li key={conversation.id} className="conversation-row">
                <form className="rename-form" onSubmit={saveRename}>
                  <input
                    className="rename-input"
                    value={editTitle}
                    maxLength={100}
                    dir="auto"
                    aria-label="Chat name"
                    autoFocus
                    onChange={(event) => setEditTitle(event.target.value)}
                    onKeyDown={(event) => event.key === "Escape" && setEditingId(null)}
                  />
                  <Button
                    type="submit"
                    variant="ghost"
                    size="sm"
                    aria-label="Save name"
                    icon={<Check size={14} aria-hidden />}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Cancel renaming"
                    icon={<X size={14} aria-hidden />}
                    onClick={() => setEditingId(null)}
                  />
                </form>
              </li>
            );
          }
          return (
            <li
              key={conversation.id}
              className={`conversation-row ${conversation.id === activeId ? "active" : ""}`}
            >
              <button
                type="button"
                className="conversation-open"
                dir="auto"
                aria-current={conversation.id === activeId ? "true" : undefined}
                onClick={() => onOpen(conversation.id)}
              >
                {title}
              </button>
              <div className="row-actions">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Rename "${title}"`}
                  icon={<Pencil size={14} aria-hidden />}
                  onClick={() => startRename(conversation)}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  className="ghost-danger"
                  aria-label={`Delete "${title}"`}
                  icon={<Trash2 size={14} aria-hidden />}
                  onClick={() => setDeleting(conversation)}
                />
              </div>
            </li>
          );
        })}
      </ul>

      {deleting && (
        <ConfirmDialog
          title="Delete this chat?"
          message={`"${deleting.title ?? "New chat"}" and all its messages will be deleted. This can't be undone. Your documents are not affected.`}
          confirmLabel="Delete chat"
          onConfirm={async () => {
            await onDelete(deleting.id);
            setDeleting(null);
          }}
          onCancel={() => setDeleting(null)}
        />
      )}
    </>
  );
}
