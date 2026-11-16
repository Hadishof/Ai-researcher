// The top of the app: it owns the shared state (chat list, open chat, document library)
// and passes data and actions down to the sidebar and the chat area as props.

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "./api/client";
import type {
  ConversationDocument,
  ConversationSummary,
  DocumentResponse,
  MessageResponse,
} from "./api/types";
import Button from "./components/Button";
import ChatView from "./components/ChatView";
import type { OpenChat } from "./components/ChatView";
import DocumentsPanel from "./components/DocumentsPanel";
import Sidebar from "./components/Sidebar";
import { useTheme } from "./hooks/useTheme";

const NEW_CHAT: OpenChat = { id: null, title: null, documents: [], messages: [] };

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [library, setLibrary] = useState<DocumentResponse[]>([]);
  const [chat, setChat] = useState<OpenChat>(NEW_CHAT);
  const [chatLoading, setChatLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const uploadInputRef = useRef<HTMLInputElement>(null);
  // Which chat the user asked for last. If they click quickly between chats, an older,
  // slower response must not replace the chat they opened most recently.
  const requestedChatId = useRef<number | null>(null);
  // Temporary negative ids for messages shown before the backend has saved them.
  const nextTempId = useRef(-1);

  // --- Loading from the backend ---

  async function refreshConversations(): Promise<ConversationSummary[]> {
    const { conversations } = await api.listConversations();
    setConversations(conversations);
    return conversations;
  }

  async function refreshLibrary() {
    const { documents } = await api.listDocuments();
    setLibrary(documents);
  }

  async function loadAll() {
    try {
      await Promise.all([refreshConversations(), refreshLibrary()]);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorText(err));
    }
  }

  // Runs once, after the first render: load the chat list and the library.
  useEffect(() => {
    loadAll();
  }, []);

  // --- Chats ---

  function startNewChat() {
    requestedChatId.current = null;
    setChat(NEW_CHAT);
    setChatLoading(false);
    setSidebarOpen(false);
  }

  async function openConversation(id: number) {
    requestedChatId.current = id;
    setSidebarOpen(false);
    setChatLoading(true);
    try {
      const conversation = await api.getConversation(id);
      if (requestedChatId.current !== id) return; // the user has opened another chat since
      setChat({
        id: conversation.id,
        title: conversation.title,
        documents: conversation.documents,
        messages: conversation.messages,
      });
    } catch (err) {
      if (requestedChatId.current !== id) return;
      setLoadError(errorText(err));
      startNewChat();
      refreshConversations().catch(() => undefined);
    } finally {
      if (requestedChatId.current === id) setChatLoading(false);
    }
  }

  async function renameConversation(id: number, title: string) {
    const renamed = await api.renameConversation(id, title);
    setChat((current) => (current.id === id ? { ...current, title: renamed.title } : current));
    await refreshConversations();
  }

  async function deleteConversation(id: number) {
    await api.deleteConversation(id);
    if (chat.id === id) startNewChat(); // the open chat is gone: start fresh
    await Promise.all([refreshConversations(), refreshLibrary()]); // chat counts changed
  }

  async function deleteAllConversations() {
    await api.deleteAllConversations();
    startNewChat();
    setConversations([]);
    await refreshLibrary();
  }

  // --- The open chat's documents ---

  async function changeChatDocuments(documents: ConversationDocument[]) {
    if (chat.id === null) {
      // Not saved yet: just remember the choice; it is sent when the first question creates the chat.
      setChat((current) => ({ ...current, documents }));
      return;
    }
    const id = chat.id;
    const saved = await api.setConversationDocuments(
      id,
      documents.map((d) => d.document_id),
    );
    setChat((current) => (current.id === id ? { ...current, documents: saved.documents } : current));
    await refreshLibrary(); // chat counts changed
  }

  async function addDocumentToChat(document: ConversationDocument) {
    if (chat.documents.some((d) => d.document_id === document.document_id)) return;
    await changeChatDocuments([...chat.documents, document]);
  }

  async function documentDeleted(documentId: string) {
    await refreshLibrary();
    if (chat.id === null) {
      setChat((current) => ({
        ...current,
        documents: current.documents.filter((d) => d.document_id !== documentId),
      }));
    } else {
      // Reload the chat: the document leaves its list, and old sources show "deleted".
      const id = chat.id;
      const conversation = await api.getConversation(id);
      setChat((current) =>
        current.id === id
          ? { ...current, documents: conversation.documents, messages: conversation.messages }
          : current,
      );
    }
  }

  // --- Asking a question ---

  async function sendQuestion(question: string) {
    // A new chat is saved only now, with the documents chosen for it.
    let id = chat.id;
    if (id === null) {
      const created = await api.createConversation(chat.documents.map((d) => d.document_id));
      id = created.id;
      requestedChatId.current = id;
      setChat((current) => ({ ...current, id: created.id, documents: created.documents }));
    }
    const chatId = id;

    // Show the question right away, before the answer arrives.
    const now = new Date().toISOString();
    const userMessage: MessageResponse = {
      id: nextTempId.current--,
      role: "user",
      content: question,
      found: null,
      sources: [],
      created_at: now,
    };
    setChat((current) =>
      current.id === chatId ? { ...current, messages: [...current.messages, userMessage] } : current,
    );

    try {
      const response = await api.sendMessage(chatId, question);
      const answer: MessageResponse = {
        id: nextTempId.current--,
        role: "assistant",
        content: response.answer,
        found: response.found,
        sources: response.sources.map((source) => ({ ...source, document_deleted: false })),
        created_at: new Date().toISOString(),
      };
      setChat((current) =>
        current.id === chatId ? { ...current, messages: [...current.messages, answer] } : current,
      );
    } catch (err) {
      // Not saved by the backend, so remove it from the screen too (ChatView shows the error).
      setChat((current) =>
        current.id === chatId
          ? { ...current, messages: current.messages.filter((m) => m.id !== userMessage.id) }
          : current,
      );
      throw err;
    } finally {
      // The first question gives the chat its title, and the chat moves to the top of the list.
      const list = await refreshConversations().catch(() => null);
      const saved = list?.find((c) => c.id === chatId);
      if (saved) {
        setChat((current) => (current.id === chatId ? { ...current, title: saved.title } : current));
      }
    }
  }

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        theme={theme}
        onToggleTheme={toggleTheme}
        conversations={conversations}
        activeId={chat.id}
        onNewChat={startNewChat}
        onOpen={openConversation}
        onRename={renameConversation}
        onDelete={deleteConversation}
        onDeleteAll={deleteAllConversations}
      >
        <DocumentsPanel
          documents={library}
          inputRef={uploadInputRef}
          onLibraryChanged={refreshLibrary}
          onAddToChat={addDocumentToChat}
          onDeleted={documentDeleted}
        />
      </Sidebar>

      {/* Narrow screens: a dark layer behind the open sidebar; clicking it closes the sidebar. */}
      {sidebarOpen && <div className="backdrop" onClick={() => setSidebarOpen(false)} />}

      <div className="main">
        {loadError && (
          <div className="banner" role="alert">
            <span>{loadError}</span>
            <Button size="sm" onClick={loadAll}>
              Try again
            </Button>
          </div>
        )}
        <ChatView
          chat={chat}
          library={library}
          loading={chatLoading}
          onSend={sendQuestion}
          onChangeDocuments={changeChatDocuments}
          onUploadClick={() => {
            setSidebarOpen(true); // on narrow screens, show the library being used
            uploadInputRef.current?.click();
          }}
          onOpenSidebar={() => setSidebarOpen(true)}
        />
      </div>
    </div>
  );
}
