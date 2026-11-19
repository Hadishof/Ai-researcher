// TypeScript copies of the backend's Pydantic models (backend/app/schemas/).
// Field names and types must match exactly: nothing checks the real JSON at runtime.

// --- schemas/documents.py ---

export interface DocumentResponse {
  document_id: string; // SHA-256 hash of the file's contents
  filename: string;
  pages: number;
  chunks: number;
  conversation_count: number; // how many chats have this document selected
  has_file: boolean; // the original PDF is stored and can be opened (api.fileUrl)
}

export interface DocumentListResponse {
  documents: DocumentResponse[];
}

// The body of a 409 "already uploaded" error.
export interface DuplicateDocumentResponse {
  detail: string;
  document_id: string;
  filename: string;
}

// --- schemas/chat.py ---

export interface ChatRequest {
  conversation_id: number;
  question: string;
}

export interface Source {
  document_id: string;
  filename: string;
  page: number;
  score: number; // 1 - cosine distance: higher is more relevant
}

export interface ChatResponse {
  answer: string;
  found: boolean; // false when the answer is "I couldn't find this in the documents"
  sources: Source[];
}

// --- schemas/conversations.py ---

export interface ConversationDocument {
  document_id: string;
  filename: string;
}

export interface ConversationDocumentsResponse {
  documents: ConversationDocument[];
}

export interface SavedSource extends Source {
  document_deleted: boolean;
}

export interface MessageResponse {
  id: number;
  role: "user" | "assistant";
  content: string;
  found: boolean | null; // null for the user's questions
  sources: SavedSource[];
  created_at: string; // ISO 8601 date and time
}

export interface ConversationSummary {
  id: number;
  title: string | null; // null until the first question
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
}

export interface ConversationResponse {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
  documents: ConversationDocument[];
  messages: MessageResponse[];
}
