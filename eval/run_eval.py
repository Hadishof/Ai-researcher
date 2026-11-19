"""
Runs the evaluation. Run from the eval/ folder.

  python run_eval.py retrieval --dry-run     # show the Gemini calls needed, call nothing
  python run_eval.py retrieval               # run the retrieval experiments (dev set only)

Options: --experiments chunk,splitter,threshold,margin   --chunk-sizes 500,1000,1500
         --ids en-01,he-03   --limit 10   --pace 20
"""

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# The evaluation reuses the app's own code, so the backend folder must be importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from cache import EmbeddingCache  # noqa: E402
from chunkers import Setup, load_pdfs, make_chunks  # noqa: E402
from dataset import Question, load_dataset  # noqa: E402
from embedder import DOCUMENT, QUERY, PacedEmbedder  # noqa: E402
from experiments import (  # noqa: E402
    build_index,
    find_misses,
    margin_sweep,
    pick_best_setup,
    pick_margin,
    pick_threshold,
    ranking_summary,
    search_all,
    threshold_sweep,
)
from report import retrieval_markdown, save  # noqa: E402
from split import load_split  # noqa: E402

EXPERIMENTS = ["chunk", "splitter", "threshold", "margin"]


def comma_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def select_questions(part: str, ids: list[str], limit: int | None) -> list[Question]:
    """The questions of one part of the split ("dev" or "test"), optionally narrowed down."""
    split = load_split()
    allowed = set(split[part])
    questions = [q for q in load_dataset() if q.id in allowed]
    if ids:
        outside = [i for i in ids if i not in allowed]
        if outside:
            raise SystemExit(f"Not in the {part} set: {', '.join(outside)}")
        questions = [q for q in questions if q.id in ids]
    return questions[:limit] if limit else questions


def run_retrieval(args: argparse.Namespace) -> None:
    settings = get_settings()
    experiments = comma_list(args.experiments)
    unknown = set(experiments) - set(EXPERIMENTS)
    if unknown:
        raise SystemExit(f"Unknown experiment(s): {', '.join(sorted(unknown))}")

    # Tuning uses only the dev set; the test set is kept for the final run.
    questions = select_questions("dev", comma_list(args.ids), args.limit)
    sizes = [int(size) for size in comma_list(args.chunk_sizes)]
    setups = [Setup("ours", size) for size in sizes]
    if "splitter" in experiments:
        setups += [Setup("langchain", size) for size in sizes]

    # 1. Chunk everything locally (free) and work out which embeddings are missing.
    pdfs = load_pdfs()
    chunks = {setup: make_chunks(pdfs, setup) for setup in setups}
    embedder = PacedEmbedder(EmbeddingCache(settings.embedding_model), args.pace)
    needed = {
        QUERY: [q.question for q in questions],
        DOCUMENT: [chunk.text for setup_chunks in chunks.values() for chunk in setup_chunks],
    }
    missing = embedder.plan(needed)

    print(f"Questions: {len(questions)} (dev set). Setups: {', '.join(s.name for s in setups)}")
    for setup in setups:
        print(f"  {setup.name}: {len(chunks[setup])} chunks")
    print("Gemini calls needed (texts already cached are not sent):")
    for task_type, texts in missing.items():
        unique = len(set(needed[task_type]))
        print(f"  {task_type}: {len(texts)} of {unique} texts not cached")
    print(f"  Embedding requests: {embedder.count_requests(missing)} (up to 100 texts each)")
    print("  Generation calls: 0")
    if args.dry_run:
        return

    # 2. Fetch only the missing embeddings (paced, saved as they arrive).
    if embedder.count_requests(missing):
        from app.core.gemini import get_gemini_client

        embedder.fetch(get_gemini_client(), missing)

    # 3. Index each setup in a temporary ChromaDB and search every question.
    results: dict[str, dict] = {}
    searches = {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        for setup in setups:
            store = build_index(Path(folder), setup, chunks[setup], embedder.cache)
            searches[setup.name] = search_all(store, questions, pdfs, embedder.cache)
            results[setup.name] = {
                "chunks": len(chunks[setup]),
                "ranking": ranking_summary(searches[setup.name]),
            }

    # 4. Apply the fixed rules. The app can only use our own chunker.
    ours = {
        s.name: {m: results[s.name]["ranking"]["metrics"][m]["overall"]["value"] for m in ("mrr", "hit@1")}
        for s in setups if s.chunker == "ours"
    }
    best_setup = pick_best_setup(ours, default=f"ours-{settings.chunk_size}")
    best = searches[best_setup]

    sweep = threshold_sweep(best, settings.top_k, settings.relative_margin)
    max_distance = pick_threshold(sweep) if "threshold" in experiments else settings.max_distance
    margins = margin_sweep(best, settings.top_k, max_distance)
    margin = pick_margin(margins) if "margin" in experiments else settings.relative_margin

    data = {
        "info": {
            "date": f"{datetime.now():%Y-%m-%d %H:%M}",
            "questions": len(questions),
            "answerable": sum(q.expect_found for q in questions),
            "not_found": sum(not q.expect_found for q in questions),
            "embedding_model": settings.embedding_model,
            "top_k": settings.top_k,
            "current": {
                "chunk_size": settings.chunk_size,
                "max_distance": settings.max_distance,
                "relative_margin": settings.relative_margin,
            },
        },
        "experiments": experiments,
        "setups": results,
        "threshold_margin": settings.relative_margin,
        "threshold_sweep": sweep,
        "margin_sweep": margins,
        "suggested": {
            "setup": best_setup,
            "chunk_size": int(best_setup.split("-")[1]),
            "max_distance": max_distance,
            "relative_margin": margin,
        },
        "misses": find_misses(
            best, settings.top_k, max_distance, margin if margin is not None else 2.0
        ),
    }
    json_path, md_path = save("retrieval", data, retrieval_markdown(data))
    print(f"\nSaved {json_path.name} and {md_path.name} in eval/results/")
    print(f"Suggested: {data['suggested']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the AI Researcher.")
    modes = parser.add_subparsers(dest="mode", required=True)

    retrieval = modes.add_parser("retrieval", help="retrieval experiments on the dev set (no answers)")
    retrieval.add_argument("--experiments", default=",".join(EXPERIMENTS))
    retrieval.add_argument("--chunk-sizes", default="500,1000,1500")
    retrieval.add_argument("--ids", default="", help="only these dev question ids, comma-separated")
    retrieval.add_argument("--limit", type=int, help="only the first N dev questions")
    retrieval.add_argument("--pace", type=float, default=20.0, help="seconds between Gemini requests")
    retrieval.add_argument("--dry-run", action="store_true", help="only print the Gemini calls needed")
    retrieval.set_defaults(run=run_retrieval)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
