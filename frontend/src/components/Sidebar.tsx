// The left column: app name, theme toggle, "New chat", the chat list with "Delete all chats",
// and the document library. On narrow screens it slides in over the chat as a drawer.
// On wide screens it can be resized (drag the right edge, or arrow keys) and collapsed.

import { Moon, PanelLeftClose, Plus, Sun, X } from "lucide-react";
import { useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent, ReactNode, Ref } from "react";

import type { ConversationSummary } from "../api/types";
import { SIDEBAR_MAX, SIDEBAR_MIN } from "../hooks/useSidebarLayout";
import type { Theme } from "../hooks/useTheme";
import Button from "./Button";
import ConfirmDialog from "./ConfirmDialog";
import ConversationList from "./ConversationList";

const KEY_STEP = 16; // pixels per arrow-key press on the resize handle

interface SidebarProps {
  open: boolean; // narrow screens: is the drawer shown?
  onClose: () => void;
  width: number; // wide screens: the current width in pixels
  onResize: (width: number) => void;
  onCollapse: () => void;
  collapseButtonRef: Ref<HTMLButtonElement>; // App moves the keyboard focus here on expand
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
  width,
  onResize,
  onCollapse,
  collapseButtonRef,
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
  // While dragging: where the pointer and the sidebar edge were when the drag started.
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);
  const count = conversations.length;

  function startDrag(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault(); // no text selection while dragging
    // Pointer capture: keep getting move events even when the pointer leaves the thin handle.
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drag.current = { startX: event.clientX, startWidth: width };
    document.body.classList.add("resizing"); // col-resize cursor everywhere while dragging
  }

  function moveDrag(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    onResize(drag.current.startWidth + event.clientX - drag.current.startX);
  }

  function endDrag() {
    drag.current = null;
    document.body.classList.remove("resizing");
  }

  // The keyboard way to resize, for people who don't use a mouse.
  function resizeWithKeys(event: KeyboardEvent<HTMLDivElement>) {
    const next = {
      ArrowLeft: width - KEY_STEP,
      ArrowRight: width + KEY_STEP,
      Home: SIDEBAR_MIN,
      End: SIDEBAR_MAX,
    }[event.key];
    if (next === undefined) return;
    event.preventDefault(); // don't also scroll the page
    onResize(next);
  }

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
          ref={collapseButtonRef}
          variant="ghost"
          size="sm"
          className="collapse-button"
          aria-label="Collapse sidebar"
          title="Collapse sidebar"
          icon={<PanelLeftClose size={16} aria-hidden />}
          onClick={onCollapse}
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

      {/* The drag handle on the right edge. role="separator" with a value is the standard
          pattern for a resizable splitter: screen readers announce it and its width. */}
      <div
        className="resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        aria-valuemin={SIDEBAR_MIN}
        aria-valuemax={SIDEBAR_MAX}
        aria-valuenow={width}
        tabIndex={0}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={resizeWithKeys}
      />

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
