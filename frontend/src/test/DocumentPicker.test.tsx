// Choosing which documents a chat searches.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "../App";
import { HANDBOOK, POLICY, conversation, mockApi, summary } from "./fakeBackend";

describe("DocumentPicker", () => {
  it("saves the ticked documents for an open chat", async () => {
    const backend = mockApi({
      conversations: [summary(1, "Company facts")],
      documents: [HANDBOOK, POLICY],
      opened: conversation(1, "Company facts", [HANDBOOK]),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Company facts" }));
    await screen.findByRole("heading", { level: 1, name: "Company facts" });

    await user.click(screen.getByRole("button", { name: "Documents" }));
    const panel = screen.getByRole("dialog", { name: "Choose documents for this chat" });
    expect(within(panel).getByRole("checkbox", { name: /handbook\.pdf/ })).toBeChecked();
    await user.click(within(panel).getByRole("checkbox", { name: /policy-2024\.pdf/ }));
    await user.click(within(panel).getByRole("button", { name: "Save" }));

    expect(backend.setConversationDocuments).toHaveBeenCalledWith(1, [
      HANDBOOK.document_id,
      POLICY.document_id,
    ]);
    const chips = await screen.findByRole("list", { name: "Documents in this chat" });
    // Chips show the name without ".pdf"; the checkbox list above keeps the full filename.
    expect(within(chips).getAllByRole("listitem").map((chip) => chip.textContent)).toEqual([
      "handbook",
      "policy-2024",
    ]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cancel keeps the chat's documents unchanged", async () => {
    const backend = mockApi({
      conversations: [summary(1, "Company facts")],
      documents: [HANDBOOK, POLICY],
      opened: conversation(1, "Company facts", [HANDBOOK]),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Company facts" }));
    await screen.findByRole("heading", { level: 1, name: "Company facts" });

    await user.click(screen.getByRole("button", { name: "Documents" }));
    await user.click(screen.getByRole("checkbox", { name: /policy-2024\.pdf/ }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(backend.setConversationDocuments).not.toHaveBeenCalled();
    const chips = screen.getByRole("list", { name: "Documents in this chat" });
    expect(within(chips).getAllByRole("listitem")).toHaveLength(1);
  });

  it("in a new chat, remembers the choice and sends it when the first question creates the chat", async () => {
    const backend = mockApi({ documents: [HANDBOOK, POLICY] });
    backend.sendMessage.mockResolvedValue({ answer: "An answer.", found: true, sources: [] });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Choose documents" }));
    await user.click(screen.getByRole("checkbox", { name: /policy-2024\.pdf/ }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    // Not saved to the backend yet: the chat itself doesn't exist until the first question.
    expect(backend.setConversationDocuments).not.toHaveBeenCalled();
    expect(backend.createConversation).not.toHaveBeenCalled();
    const box = screen.getByRole("textbox", { name: "Question" });
    expect(box).toBeEnabled();

    await user.type(box, "How fast is support?{Enter}");

    expect(backend.createConversation).toHaveBeenCalledWith([POLICY.document_id]);
    expect(backend.sendMessage).toHaveBeenCalledWith(99, "How fast is support?");
    expect(await screen.findByText("An answer.")).toBeInTheDocument();
  });
});
