// The left column: app name, theme toggle, "New chat", the chat list with "Delete all chats",
// and the document library. On narrow screens it slides in over the chat as a drawer.

import { Moon, Plus, Sun, X } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import type { ConversationSummary } from "../api/types";
import type { Theme } from "../hooks/useTheme";
import Button from "./Button";
import ConfirmDialog from "./ConfirmDialog";
import ConversationList from "./ConversationList";

interface SidebarProps {
  open: boolean; // narrow screens: is the drawer shown?
  onClose: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  conversations: ConversationSummary[];
  activeId: number | null;
  onNewChat: () => void;
  onOpen: (id: number) => void;
  onRename: (id: number, title: string) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onDeleteAll: () => Promise<void>;
  children: ReactNode; // the documents panel
}

export default function Sidebar({
  open,
  onClose,
  theme,
  onToggleTheme,
  conversations,
  activeId,
  onNewChat,
  onOpen,
  onRename,
  onDelete,
  onDeleteAll,
  children,
}: SidebarProps) {
  const [confirmingDeleteAll, setConfirmingDeleteAll] = useState(false);
  const count = conversations.length;

  return (
    <aside className={`sidebar ${open ? "open" : ""}`}>
      <div className="sidebar-header">
        <span className="app-name">AI Researcher</span>
        <Button
          variant="ghost"
          size="sm"
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          icon={theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
          onClick={onToggleTheme}
        />
        <Button
          variant="ghost"
          size="sm"
          className="close-button"
          aria-label="Close sidebar"
          icon={<X size={16} aria-hidden />}
          onClick={onClose}
        />
      </div>

      <div className="sidebar-new">
        <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={onNewChat}>
          New chat
        </Button>
      </div>

      <section className="chats" aria-labelledby="chats-heading">
        <h2 id="chats-heading" className="section-title">
          Chats
        </h2>
        <ConversationList
          conversations={conversations}
          activeId={activeId}
          onOpen={onOpen}
          onRename={onRename}
          onDelete={onDelete}
        />
        {count > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="ghost-danger delete-all"
            onClick={() => setConfirmingDeleteAll(true)}
          >
            Delete all chats
          </Button>
        )}
      </section>

      {children}

      {confirmingDeleteAll && (
        <ConfirmDialog
          title="Delete all chats?"
          message={`Delete all ${count} ${count === 1 ? "chat" : "chats"}? This can't be undone. Your documents are not affected.`}
          confirmLabel="Delete all"
          onConfirm={async () => {
            await onDeleteAll();
            setConfirmingDeleteAll(false);
          }}
          onCancel={() => setConfirmingDeleteAll(false)}
        />
      )}
    </aside>
  );
}
