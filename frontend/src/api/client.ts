// Every call to the backend lives in this file. Components call `api.something()`
// and never use fetch() or build URLs themselves.

import type {
  ChatResponse,
  ConversationDocumentsResponse,
  ConversationListResponse,
  ConversationResponse,
  ConversationSummary,
  DocumentListResponse,
  DocumentResponse,
  DuplicateDocumentResponse,
} from "./types";

// Set VITE_API_URL in frontend/.env to use another backend address.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Used when the backend sends no readable message (for example a 422 from FastAPI's
// automatic validation, which is a list of problems, not one sentence).
const FALLBACK_MESSAGES: Record<number, string> = {
  0: "Can't reach the server. Is the backend running?",
  400: "The request was not accepted.",
  404: "Not found. It may have been deleted.",
  409: "This document was already uploaded.",
  413: "The file is too large.",
  422: "The request was not valid.",
  429: "The AI service's rate limit was reached. Please try again in a minute.",
  502: "The AI service failed. Please try again.",
};

/** An error from the backend, with its HTTP status and a message to show the user. */
export class ApiError extends Error {
  status: number;
  // Only for a 409 on upload: the document that is already in the library.
  duplicate: DuplicateDocumentResponse | null;

  constructor(status: number, message: string, duplicate: DuplicateDocumentResponse | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.duplicate = duplicate;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    // fetch() itself fails only when there is no answer at all (server down, no network).
    throw new ApiError(0, FALLBACK_MESSAGES[0]);
  }

  if (response.status === 204) {
    return undefined as T; // "No Content": success with no body
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : (FALLBACK_MESSAGES[response.status] ?? `Something went wrong (error ${response.status}).`);
    const duplicate = response.status === 409 && body?.document_id ? body : null;
    throw new ApiError(response.status, message, duplicate);
  }
  return body as T;
}

/** A request with a JSON body. */
function sendJson<T>(method: string, path: string, data: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export const api = {
  // --- Documents (one shared library) ---

  listDocuments: (): Promise<DocumentListResponse> => request("/documents"),

  uploadDocument: (file: File): Promise<DocumentResponse> => {
    const form = new FormData();
    form.append("file", file);
    // No Content-Type header: the browser sets it, including the multipart boundary.
    return request("/documents", { method: "POST", body: form });
  },

  deleteDocument: (documentId: string): Promise<void> =>
    request(`/documents/${documentId}`, { method: "DELETE" }),

  // --- Conversations ---

  listConversations: (): Promise<ConversationListResponse> => request("/conversations"),

  getConversation: (id: number): Promise<ConversationResponse> => request(`/conversations/${id}`),

  createConversation: (documentIds: string[]): Promise<ConversationResponse> =>
    sendJson("POST", "/conversations", { document_ids: documentIds }),

  renameConversation: (id: number, title: string): Promise<ConversationSummary> =>
    sendJson("PATCH", `/conversations/${id}`, { title }),

  setConversationDocuments: (
    id: number,
    documentIds: string[],
  ): Promise<ConversationDocumentsResponse> =>
    sendJson("PUT", `/conversations/${id}/documents`, { document_ids: documentIds }),

  deleteConversation: (id: number): Promise<void> =>
    request(`/conversations/${id}`, { method: "DELETE" }),

  deleteAllConversations: (): Promise<void> => request("/conversations", { method: "DELETE" }),

  // --- Chat ---

  sendMessage: (conversationId: number, question: string): Promise<ChatResponse> =>
    sendJson("POST", "/chat", { conversation_id: conversationId, question }),
};
