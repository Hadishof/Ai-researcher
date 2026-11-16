// The sources under an answer, as small chips: "handbook · p. 3".
// The relevance score is in the tooltip and the accessible label, not on the chip.
// A source whose document was deleted keeps its name, marked "deleted".

import type { SavedSource } from "../api/types";

/** The filename as shown on chips: without the ".pdf" extension. */
export function chipName(filename: string): string {
  return filename.replace(/\.pdf$/i, "");
}

export default function SourceChips({ sources }: { sources: SavedSource[] }) {
  if (sources.length === 0) return null;

  return (
    <ul className="chips" aria-label="Sources">
      {sources.map((source) => {
        const name = chipName(source.filename);
        const score = source.score.toFixed(2);
        return (
          <li
            key={`${source.document_id}-${source.page}`}
            // Each chip keeps its own direction (from its filename), so under a Hebrew
            // answer an English chip still reads "name · p. 1", not "p. 1 · name".
            dir="auto"
            className={`chip ${source.document_deleted ? "chip-deleted" : ""}`}
            // title: the tooltip on hover. aria-label: what a screen reader says instead
            // of the chip's visible text, so the score is not lost for those users.
            title={source.document_deleted ? "Deleted from the library" : `Relevance: ${score}`}
            aria-label={
              source.document_deleted
                ? `${name}, page ${source.page}, deleted from the library`
                : `${name}, page ${source.page}, relevance ${score}`
            }
          >
            <span className="chip-name">{name}</span>
            <span className="chip-sep" aria-hidden>
              {" · "}
            </span>
            {/* "p." in the normal font: a space in the mono font is wider and looked doubled. */}
            <span className="chip-page">
              p. <span className="mono">{source.page}</span>
            </span>
            {source.document_deleted && (
              <>
                <span className="chip-sep" aria-hidden>
                  {" · "}
                </span>
                <span className="chip-label">deleted</span>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
