// One message: the user's question, or the answer with its sources.
// Hebrew text is shown right-to-left, English left-to-right.

import type { MessageResponse } from "../api/types";
import SourceChips from "./SourceChips";

// The first letter that has a direction decides, the same rule the browser uses for dir="auto".
const FIRST_LETTER = /[A-Za-z֐-׿؀-ۿ]/;
const RIGHT_TO_LEFT = /[֐-׿؀-ۿ]/; // Hebrew (and Arabic) letters

export function textDirection(text: string): "rtl" | "ltr" {
  const first = text.match(FIRST_LETTER)?.[0];
  return first && RIGHT_TO_LEFT.test(first) ? "rtl" : "ltr";
}

export default function Message({ message }: { message: MessageResponse }) {
  if (message.role === "user") {
    return (
      <p className="question" dir="auto">
        {message.content}
      </p>
    );
  }

  const notFound = message.found === false;
  // The whole answer block follows the answer's language: the text, the "not found"
  // border, and the row of source chips all start on the right for Hebrew.
  // (dir="auto" can't be used here: it would look at the first text inside the block,
  // which may be the English "not found" label instead of the answer.)
  return (
    <div
      className={`answer ${notFound ? "answer-not-found" : ""}`}
      dir={textDirection(message.content)}
      data-testid="answer"
    >
      {notFound && <p className="answer-label">Not in the selected documents</p>}
      <p className="answer-text">{message.content}</p>
      <SourceChips sources={message.sources} />
    </div>
  );
}
