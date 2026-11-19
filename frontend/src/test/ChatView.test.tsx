// The chat area: sending with Enter, answers with sources, "not found", and saved history.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import App from "../App";
import { ApiError } from "../api/client";
import type { MessageResponse } from "../api/types";
import { HANDBOOK, POLICY, conversation, mockApi, summary } from "./fakeBackend";

/** Render the app and open chat 1, which has the handbook and the policy selected. */
async function openChat(messages: MessageResponse[] = []) {
  const backend = mockApi({
    conversations: [summary(1, "Company facts")],
    documents: [HANDBOOK, POLICY],
    opened: conversation(1, "Company facts", [HANDBOOK, POLICY], messages),
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
    // The handbook's PDF is stored, so its chip is a link to the cited page.
    const chip = within(sources).getByRole("link");
    expect(chip).toHaveTextContent(/^handbook · p\. 3$/); // no ".pdf", no score, one space
    expect(chip).toHaveAttribute("title", "Relevance: 0.76. Opens page 3 in a new tab.");
    expect(chip).toHaveAccessibleName("Open handbook, page 3, relevance 0.76");
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveValue(""); // box is cleared
  });

  it("links a source chip to its PDF at the cited page, in a new tab", async () => {
    await openChat([
      { id: 1, role: "user", content: "Who founded it?", found: null, sources: [], created_at: "" },
      {
        id: 2,
        role: "assistant",
        content: "Dana Levi founded it.",
        found: true,
        sources: [
          { document_id: HANDBOOK.document_id, filename: "handbook.pdf", page: 6, score: 0.81, document_deleted: false },
        ],
        created_at: "",
      },
    ]);

    const link = screen.getByRole("link", { name: "Open handbook, page 6, relevance 0.81" });
    expect(link).toHaveAttribute("href", `http://localhost:8000/documents/${HANDBOOK.document_id}/file#page=6`);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer"); // the new tab can't control this one
  });

  it("does not link a chip whose document has no stored PDF", async () => {
    await openChat([
      { id: 1, role: "user", content: "Is there a policy?", found: null, sources: [], created_at: "" },
      {
        id: 2,
        role: "assistant",
        content: "Yes.",
        found: true,
        sources: [
          { document_id: POLICY.document_id, filename: "policy-2024.pdf", page: 2, score: 0.7, document_deleted: false },
        ],
        created_at: "",
      },
    ]);

    const sources = screen.getByRole("list", { name: "Sources" });
    expect(within(sources).queryByRole("link")).not.toBeInTheDocument();
    expect(within(sources).getByLabelText("policy-2024, page 2, relevance 0.70")).toBeInTheDocument();
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
    const sources = screen.getByRole("list", { name: "Sources" });
    // A deleted document's chip is not a link: there is no PDF to open any more.
    expect(within(sources).queryByRole("link")).not.toBeInTheDocument();
    const chip = within(sources).getByLabelText("old-handbook, page 1, deleted from the library");
    expect(chip).toHaveClass("chip-deleted");
    expect(chip).toHaveTextContent(/^old-handbook · p\. 1 · deleted$/);
    expect(chip).toHaveAttribute("title", "Deleted from the library");
  });
});
