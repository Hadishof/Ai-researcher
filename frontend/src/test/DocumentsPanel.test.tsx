// The document library: uploads (added to the open chat), upload errors, and deleting.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "../App";
import { ApiError } from "../api/client";
import { HANDBOOK, POLICY, conversation, mockApi, summary } from "./fakeBackend";

const PDF = new File(["%PDF-1.7 fake"], "policy-2024.pdf", { type: "application/pdf" });

describe("Viewing a PDF", () => {
  it("shows a view link, opening in a new tab, only for documents with a stored PDF", async () => {
    mockApi({ documents: [HANDBOOK, POLICY] }); // POLICY has no stored file
    render(<App />);

    const link = await screen.findByRole("link", { name: "View handbook.pdf" });
    expect(link).toHaveAttribute("href", `http://localhost:8000/documents/${HANDBOOK.document_id}/file`);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByRole("link", { name: "View policy-2024.pdf" })).not.toBeInTheDocument();
  });
});

/** Render the app with chat 1 open (no documents selected yet). */
async function openChat(documents = [HANDBOOK]) {
  const backend = mockApi({
    conversations: [summary(1, "Company facts")],
    documents,
    opened: conversation(1, "Company facts", []),
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Company facts" }));
  await screen.findByRole("heading", { level: 1, name: "Company facts" });
  return { backend, user };
}

describe("DocumentsPanel", () => {
  it("adds an uploaded PDF to the open chat", async () => {
    const { backend, user } = await openChat();
    backend.uploadDocument.mockResolvedValue(POLICY);

    await user.upload(screen.getByTestId("file-input"), PDF);

    expect(backend.uploadDocument).toHaveBeenCalledWith(PDF);
    expect(backend.setConversationDocuments).toHaveBeenCalledWith(1, [POLICY.document_id]);
    expect(await screen.findByRole("status")).toHaveTextContent(
      'Uploaded "policy-2024.pdf" and added it to this chat.',
    );
  });

  it("adds the existing copy to the chat when the PDF is already in the library (409)", async () => {
    const { backend, user } = await openChat([HANDBOOK]);
    backend.uploadDocument.mockRejectedValue(
      new ApiError(409, "This document was already uploaded.", {
        detail: "This document was already uploaded.",
        document_id: HANDBOOK.document_id,
        filename: "handbook.pdf",
      }),
    );

    await user.upload(screen.getByTestId("file-input"), PDF);

    expect(backend.setConversationDocuments).toHaveBeenCalledWith(1, [HANDBOOK.document_id]);
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Already in your library — added to this chat.",
    );
    const chips = screen.getByRole("list", { name: "Documents in this chat" });
    expect(chips).toHaveTextContent("handbook");
  });

  // These go through the real client.ts with a fake fetch, to check the whole path from
  // the backend's error response to the message on screen.
  it.each([
    [400, { detail: "Only PDF files are supported." }, "Only PDF files are supported."],
    [413, { detail: "The file is larger than 20 MB." }, "The file is larger than 20 MB."],
    [
      422,
      { detail: "No readable text was found in this PDF (it may be a scanned image)." },
      "No readable text was found in this PDF",
    ],
    [
      429,
      { detail: "The AI service's rate limit was reached. Please try again in a minute." },
      "rate limit was reached",
    ],
    [502, { detail: "The embedding service failed. Please try again." }, "embedding service failed"],
    [502, null, "The AI service failed. Please try again."], // no readable body: fallback text
  ])("shows a clear message for a %i error", async (status, body, expected) => {
    const { backend, user } = await openChat();
    backend.uploadDocument.mockRestore(); // use the real upload function...
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      // ...talking to a fake backend
      new Response(body ? JSON.stringify(body) : "", { status }),
    );

    await user.upload(screen.getByTestId("file-input"), PDF);

    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(backend.setConversationDocuments).not.toHaveBeenCalled();
  });

  it("warns how many chats use a document before deleting it", async () => {
    const used = { ...HANDBOOK, conversation_count: 2 };
    const { backend, user } = await openChat([used]);

    await user.click(screen.getByRole("button", { name: "Delete handbook.pdf" }));

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(
      "This document is used in 2 chats. Deleting it removes it from those chats. This can't be undone.",
    );
    backend.listDocuments.mockResolvedValue({ documents: [] });
    await user.click(within(dialog).getByRole("button", { name: "Delete document" }));

    expect(backend.deleteDocument).toHaveBeenCalledWith(HANDBOOK.document_id);
    const library = screen.getByRole("region", { name: "Library" });
    expect(
      await within(library).findByText("No documents yet — upload a PDF to start."),
    ).toBeInTheDocument();
  });
});
