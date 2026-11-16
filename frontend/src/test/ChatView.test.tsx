// The chat area: sending with Enter, answers with sources, "not found", and saved history.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "../App";
import { ApiError } from "../api/client";
import type { MessageResponse } from "../api/types";
import { HANDBOOK, conversation, mockApi, summary } from "./fakeBackend";

/** Render the app and open chat 1, which has the handbook selected. */
async function openChat(messages: MessageResponse[] = []) {
  const backend = mockApi({
    conversations: [summary(1, "Company facts")],
    documents: [HANDBOOK],
    opened: conversation(1, "Company facts", [HANDBOOK], messages),
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Company facts" }));
  await screen.findByRole("heading", { level: 1, name: "Company facts" });
  return { backend, user };
}

describe("ChatView", () => {
  it("asks a new chat to choose documents first", async () => {
    mockApi({ documents: [HANDBOOK] });
    render(<App />);

    expect(await screen.findByText("Choose the documents for this chat")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Question" })).toBeDisabled();
  });

  it("sends with Enter and shows the answer with its source chips", async () => {
    const { backend, user } = await openChat();
    backend.sendMessage.mockResolvedValue({
      answer: "Nimbus Robotics was founded by Dana Levi.",
      found: true,
      sources: [{ document_id: HANDBOOK.document_id, filename: "handbook.pdf", page: 3, score: 0.76 }],
    });

    await user.type(screen.getByRole("textbox", { name: "Question" }), "Who founded it?{Enter}");

    expect(backend.sendMessage).toHaveBeenCalledWith(1, "Who founded it?");
    expect(await screen.findByText("Nimbus Robotics was founded by Dana Levi.")).toBeInTheDocument();
    expect(screen.getByText("Who founded it?")).toBeInTheDocument(); // the question stays on screen
    const sources = screen.getByRole("list", { name: "Sources" });
    const chip = within(sources).getByRole("listitem");
    expect(chip).toHaveTextContent(/^handbook · p\. 3$/); // no ".pdf", no score, one space
    expect(chip).toHaveAttribute("title", "Relevance: 0.76"); // the score is in the tooltip
    expect(chip).toHaveAccessibleName("handbook, page 3, relevance 0.76");
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveValue(""); // box is cleared
  });

  it("adds a new line with Shift+Enter instead of sending", async () => {
    const { backend, user } = await openChat();
    const box = screen.getByRole("textbox", { name: "Question" });

    await user.type(box, "First line{Shift>}{Enter}{/Shift}second line");

    expect(backend.sendMessage).not.toHaveBeenCalled();
    expect(box).toHaveValue("First line\nsecond line");
  });

  it("shows a 'not found' answer in its own style", async () => {
    const { backend, user } = await openChat();
    backend.sendMessage.mockResolvedValue({
      answer: "I couldn't find this in the documents.",
      found: false,
      sources: [],
    });

    await user.type(screen.getByRole("textbox", { name: "Question" }), "What's the weather?{Enter}");

    const answer = await screen.findByTestId("answer");
    expect(answer).toHaveClass("answer-not-found");
    expect(answer).toHaveTextContent("Not in the selected documents");
  });

  it("puts source chips on the right under Hebrew answers and on the left under English ones", async () => {
    const source = {
      document_id: HANDBOOK.document_id,
      filename: "handbook.pdf",
      page: 3,
      score: 0.8,
      document_deleted: false,
    };
    await openChat([
      { id: 1, role: "user", content: "כמה ימי חופשה?", found: null, sources: [], created_at: "" },
      { id: 2, role: "assistant", content: "עשרים ימים בשנה.", found: true, sources: [source], created_at: "" },
      { id: 3, role: "user", content: "How many vacation days?", found: null, sources: [], created_at: "" },
      { id: 4, role: "assistant", content: "Twenty days a year.", found: true, sources: [source], created_at: "" },
      { id: 5, role: "user", content: "מה מזג האוויר?", found: null, sources: [], created_at: "" },
      { id: 6, role: "assistant", content: "לא מצאתי את זה במסמכים.", found: false, sources: [], created_at: "" },
    ]);

    // jsdom can't measure layout, so we check the direction the chips inherit: in a
    // right-to-left block, the browser starts the row of chips on the right.
    const [hebrew, english, hebrewNotFound] = screen.getAllByTestId("answer");
    expect(hebrew).toHaveAttribute("dir", "rtl");
    expect(english).toHaveAttribute("dir", "ltr");
    const [hebrewChips, englishChips] = screen.getAllByRole("list", { name: "Sources" });
    expect(hebrewChips.closest("[dir]")).toBe(hebrew);
    expect(englishChips.closest("[dir]")).toBe(english);
    // Each chip keeps its own direction, so an English filename still reads "handbook · p. 3".
    expect(within(hebrewChips).getByRole("listitem")).toHaveAttribute("dir", "auto");
    // The English "not found" label doesn't decide the direction; the Hebrew answer does.
    expect(hebrewNotFound).toHaveAttribute("dir", "rtl");
  });

  it("gives the question back when sending fails", async () => {
    const { backend, user } = await openChat();
    backend.sendMessage.mockRejectedValue(
      new ApiError(429, "The AI service's rate limit was reached. Please try again in a minute."),
    );

    await user.type(screen.getByRole("textbox", { name: "Question" }), "Who founded it?{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("rate limit was reached");
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveValue("Who founded it?");
  });

  it("shows a saved chat's history, with sources of deleted documents marked", async () => {
    await openChat([
      { id: 1, role: "user", content: "Who founded it?", found: null, sources: [], created_at: "" },
      {
        id: 2,
        role: "assistant",
        content: "Dana Levi founded it.",
        found: true,
        sources: [
          {
            document_id: "c".repeat(64),
            filename: "old-handbook.pdf",
            page: 1,
            score: 0.9,
            document_deleted: true,
          },
        ],
        created_at: "",
      },
    ]);

    expect(screen.getByText("Dana Levi founded it.")).toBeInTheDocument();
    const chip = within(screen.getByRole("list", { name: "Sources" })).getByRole("listitem");
    expect(chip).toHaveClass("chip-deleted");
    expect(chip).toHaveTextContent(/^old-handbook · p\. 1 · deleted$/);
    expect(chip).toHaveAttribute("title", "Deleted from the library");
  });
});
