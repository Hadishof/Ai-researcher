// The chat list in the sidebar: deleting one chat, and deleting all chats.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "../App";
import { HANDBOOK, conversation, mockApi, summary } from "./fakeBackend";

const VACATION = summary(1, "Vacation policy");
const SUPPORT = summary(2, "Support hours");

describe("Sidebar", () => {
  it("deletes a chat after the user confirms", async () => {
    const backend = mockApi({ conversations: [VACATION, SUPPORT] });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: 'Delete "Vacation policy"' }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Your documents are not affected.");

    backend.listConversations.mockResolvedValue({ conversations: [SUPPORT] });
    await user.click(within(dialog).getByRole("button", { name: "Delete chat" }));

    expect(backend.deleteConversation).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.queryByText("Vacation policy")).not.toBeInTheDocument());
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("does not delete when the user cancels", async () => {
    const backend = mockApi({ conversations: [VACATION] });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: 'Delete "Vacation policy"' }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(backend.deleteConversation).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("Vacation policy")).toBeInTheDocument();
  });

  it("starts a new chat when the open chat is deleted", async () => {
    const backend = mockApi({
      conversations: [VACATION],
      documents: [HANDBOOK],
      opened: conversation(1, "Vacation policy", [HANDBOOK]),
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Vacation policy" }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Vacation policy");

    backend.listConversations.mockResolvedValue({ conversations: [] });
    await user.click(screen.getByRole("button", { name: 'Delete "Vacation policy"' }));
    await user.click(screen.getByRole("button", { name: "Delete chat" }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("New chat"),
    );
    expect(screen.getByText("No chats yet")).toBeInTheDocument();
  });

  it("asks before deleting all chats, and says how many", async () => {
    const backend = mockApi({
      conversations: [VACATION, SUPPORT, summary(3, null)],
      documents: [HANDBOOK],
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Delete all chats" }));

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(
      "Delete all 3 chats? This can't be undone. Your documents are not affected.",
    );
    expect(backend.deleteAllConversations).not.toHaveBeenCalled(); // nothing happens before confirming

    await user.click(within(dialog).getByRole("button", { name: "Delete all" }));

    expect(backend.deleteAllConversations).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("No chats yet")).toBeInTheDocument();
    expect(screen.getByText("handbook.pdf")).toBeInTheDocument(); // documents are still listed
  });
});
