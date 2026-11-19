// The sources under an answer, as small chips: "handbook · p. 3".
// A chip whose PDF is available is a link: it opens the PDF in a new tab at the cited
// page, so the answer can be checked in one click.
// The relevance score is in the tooltip and the accessible label, not on the chip.
// A source whose document was deleted keeps its name, marked "deleted", and is not a link.

import { api } from "../api/client";
import type { SavedSource } from "../api/types";

/** The filename as shown on chips: without the ".pdf" extension. */
export function chipName(filename: string): string {
  return filename.replace(/\.pdf$/i, "");
}

interface SourceChipsProps {
  sources: SavedSource[];
  // Ids of the documents whose PDF is stored and can be opened.
  viewable: ReadonlySet<string>;
}

export default function SourceChips({ sources, viewable }: SourceChipsProps) {
  if (sources.length === 0) return null;

  return (
    <ul className="chips" aria-label="Sources">
      {sources.map((source) => {
        const name = chipName(source.filename);
        const score = source.score.toFixed(2);
        const deleted = source.document_deleted;
        const clickable = !deleted && viewable.has(source.document_id);

        const content = (
          <>
            <span className="chip-name">{name}</span>
            <span className="chip-sep" aria-hidden>
              {" · "}
            </span>
            {/* "p." in the normal font: a space in the mono font is wider and looked doubled. */}
            <span className="chip-page">
              p. <span className="mono">{source.page}</span>
            </span>
            {deleted && (
              <>
                <span className="chip-sep" aria-hidden>
                  {" · "}
                </span>
                <span className="chip-label">deleted</span>
              </>
            )}
          </>
        );

        return (
          // Each chip keeps its own direction (from its filename), so under a Hebrew
          // answer an English chip still reads "name · p. 1", not "p. 1 · name".
          <li key={`${source.document_id}-${source.page}`} dir="auto">
            {clickable ? (
              <a
                className="chip chip-link"
                href={api.fileUrl(source.document_id, source.page)}
                target="_blank"
                rel="noopener noreferrer"
                title={`Relevance: ${score}. Opens page ${source.page} in a new tab.`}
                // What a screen reader says instead of the visible text: the action first.
                aria-label={`Open ${name}, page ${source.page}, relevance ${score}`}
              >
                {content}
              </a>
            ) : (
              <span
                className={`chip ${deleted ? "chip-deleted" : ""}`}
                // title: the tooltip on hover. aria-label: what a screen reader says instead
                // of the chip's visible text, so the score is not lost for those users.
                title={deleted ? "Deleted from the library" : `Relevance: ${score}`}
                aria-label={
                  deleted
                    ? `${name}, page ${source.page}, deleted from the library`
                    : `${name}, page ${source.page}, relevance ${score}`
                }
              >
                {content}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
