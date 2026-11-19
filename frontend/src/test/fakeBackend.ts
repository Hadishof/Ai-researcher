// Shared test data and mockApi(), which replaces every backend call with a fake ("spy"),
// so tests need no server and can control and check each call.

import { vi } from "vitest";

import { api } from "../api/client";
import type { ConversationResponse, ConversationSummary, DocumentResponse } from "../api/types";

// --- Sample data ---------------------------------------------------------------

export const HANDBOOK: DocumentResponse = {
  document_id: "a".repeat(64),
  filename: "handbook.pdf",
  pages: 4,
  chunks: 4,
  conversation_count: 1,
  has_file: true, // its PDF can be opened
};

export const POLICY: DocumentResponse = {
  document_id: "b".repeat(64),
  filename: "policy-2024.pdf",
  pages: 2,
  chunks: 3,
  conversation_count: 0,
  has_file: false, // uploaded before PDFs were stored: no file to open
};

export function summary(id: number, title: string | null): ConversationSummary {
  return { id, title, updated_at: "2026-11-16T10:00:00+00:00" };
}

export function conversation(
  id: number,
  title: string | null,
  documents: DocumentResponse[] = [],
  messages: ConversationResponse["messages"] = [],
): ConversationResponse {
  return {
    id,
    title,
    created_at: "2026-11-16T09:00:00+00:00",
    updated_at: "2026-11-16T10:00:00+00:00",
    documents: documents.map((d) => ({ document_id: d.document_id, filename: d.filename })),
    messages,
  };
}

// --- Fake backend --------------------------------------------------------------

interface FakeBackend {
  conversations?: ConversationSummary[];
  documents?: DocumentResponse[];
  opened?: ConversationResponse; // what getConversation returns
}

/** Replace every api call with a fake (a "spy"), so tests can control and check them. */
export function mockApi({ conversations = [], documents = [], opened }: FakeBackend = {}) {
  return {
    listConversations: vi.spyOn(api, "listConversations").mockResolvedValue({ conversations }),
    listDocuments: vi.spyOn(api, "listDocuments").mockResolvedValue({ documents }),
    getConversation: vi
      .spyOn(api, "getConversation")
      .mockResolvedValue(opened ?? conversation(1, null)),
    createConversation: vi
      .spyOn(api, "createConversation")
      .mockImplementation(async (ids) =>
        conversation(
          99,
          null,
          documents.filter((d) => ids.includes(d.document_id)),
        ),
      ),
    renameConversation: vi.spyOn(api, "renameConversation"),
    setConversationDocuments: vi
      .spyOn(api, "setConversationDocuments")
      .mockImplementation(async (_id, ids) => ({
        documents: ids.map((id) => {
          const document = documents.find((d) => d.document_id === id);
          return { document_id: id, filename: document?.filename ?? "uploaded.pdf" };
        }),
      })),
    deleteConversation: vi.spyOn(api, "deleteConversation").mockResolvedValue(undefined),
    deleteAllConversations: vi.spyOn(api, "deleteAllConversations").mockResolvedValue(undefined),
    uploadDocument: vi.spyOn(api, "uploadDocument"),
    deleteDocument: vi.spyOn(api, "deleteDocument").mockResolvedValue(undefined),
    sendMessage: vi.spyOn(api, "sendMessage"),
  };
}
