// The question box: Enter sends, Shift+Enter adds a new line, and it grows as you type.

import { ArrowUp } from "lucide-react";
import { useEffect, useRef } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import Button from "./Button";

const MAX_HEIGHT = 200; // px; after this the box scrolls instead of growing

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean; // no documents selected
  sending: boolean;
  placeholder: string;
}

export default function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  sending,
  placeholder,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && !sending && value.trim() !== "";

  // Grow with the text: reset the height, then set it to the height the text needs.
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // isComposing: the user is still typing a character with an input method; don't send yet.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault(); // no new line
      if (canSend) onSubmit();
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault(); // stop the browser from reloading the page
    if (canSend) onSubmit();
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <textarea
        ref={textareaRef}
        className="composer-input"
        rows={1}
        dir="auto"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        aria-label="Question"
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <Button
        type="submit"
        variant="primary"
        loading={sending}
        disabled={!canSend}
        icon={<ArrowUp size={16} aria-hidden />}
      >
        Send
      </Button>
    </form>
  );
}
