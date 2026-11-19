"""
Runs the evaluation. Run from the eval/ folder.

  python run_eval.py retrieval --dry-run     # show the Gemini calls needed, call nothing
  python run_eval.py retrieval               # run the retrieval experiments (dev set only)
  python run_eval.py full --part test --chunk-size 500 --max-distance 0.34 --margin 0.10

Retrieval options: --experiments chunk,splitter,threshold,margin   --chunk-sizes 500,1000,1500
Full-run options:  --part test|dev|all   --pace-generate 15
Both:              --ids en-01,he-03   --limit 10   --pace 60   --dry-run
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
from cached_client import CachedGeminiClient, DailyLimitReached, GenerationCache  # noqa: E402
from chunkers import OVERLAP_RATIO, Setup, load_pdfs, make_chunks  # noqa: E402
from dataset import Question, load_dataset  # noqa: E402
from embedder import DOCUMENT, QUERY, PacedEmbedder  # noqa: E402
from experiments import (  # noqa: E402
    RANK_DEPTH,
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
from full_run import (  # noqa: E402
    ANSWER_METRICS,
    RETRIEVAL_METRICS,
    Outcome,
    cached_rewrite,
    failure,
    history_messages,
    score,
)
from metrics import breakdown  # noqa: E402
from report import full_markdown, retrieval_markdown, save  # noqa: E402
from split import load_split  # noqa: E402

EXPERIMENTS = ["chunk", "splitter", "threshold", "margin"]


def comma_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def select_questions(part: str, ids: list[str], limit: int | None) -> list[Question]:
    """The questions of one part of the split ("dev", "test" or "all"), optionally narrowed down."""
    split = load_split()
    allowed = set(split["dev"]) | set(split["test"]) if part == "all" else set(split[part])
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


def daily_limit_message(done: int, total: int) -> str:
    """What to tell the user when the free tier's daily limit stops a full run."""
    return (
        f"\nGemini's daily free-tier limit is reached. {done} of {total} questions are done "
        "and their answers are saved in the cache.\n"
        "Run the same command tomorrow to continue: finished questions are not sent again."
    )


def run_full(args: argparse.Namespace) -> None:
    from app.api.routes.chat import answer_from_chunks
    from app.services.retrieval import filter_results
    from app.services.rewriting import rewrite_question

    # The settings under test, passed as flags. The app's own defaults are not changed.
    settings = get_settings().model_copy(
        update={
            "chunk_size": args.chunk_size,
            "chunk_overlap": round(args.chunk_size * OVERLAP_RATIO),
            "max_distance": args.max_distance,
            "relative_margin": args.margin,
        }
    )
    questions = select_questions(args.part, comma_list(args.ids), args.limit)
    split = load_split()
    part_of = {qid: part for part in ("dev", "test") for qid in split[part]}

    setup = Setup("ours", args.chunk_size)
    pdfs = load_pdfs()
    chunks = make_chunks(pdfs, setup)
    embedder = PacedEmbedder(EmbeddingCache(settings.embedding_model), args.pace)
    generations = GenerationCache()

    # --- Dry run: count what is not cached yet. ---
    follow_ups = [q for q in questions if q.history]
    known_rewrites = {q.id: cached_rewrite(q, settings, generations) for q in follow_ups}
    rewrites_needed = [q for q in follow_ups if known_rewrites[q.id] is None]
    known_queries = [q.question for q in questions if not q.history]
    known_queries += [text for text in known_rewrites.values() if text is not None]
    missing = embedder.plan({QUERY: known_queries, DOCUMENT: [c.text for c in chunks]})
    # A rewrite that is not cached yet is unknown until Gemini writes it: count it as
    # one more question to embed.
    unknown_queries = len(rewrites_needed)
    missing_count = {QUERY: missing[QUERY] + [""] * unknown_queries, DOCUMENT: missing[DOCUMENT]}

    print(f"Questions: {len(questions)} ({args.part} set). Setup: {setup.name}, {len(chunks)} chunks. "
          f"MAX_DISTANCE {settings.max_distance}, margin {settings.relative_margin}, top {settings.top_k}.")
    print("Gemini calls needed (cached results are not sent):")
    print(f"  Embedding texts: {len(missing[DOCUMENT])} chunks + {len(missing[QUERY])} questions"
          f" + up to {unknown_queries} rewritten follow-ups")
    print(f"  Embedding requests: {embedder.count_requests(missing_count)}")
    print(f"  Generation calls: {len(rewrites_needed)} follow-up rewrites + at most {len(questions)} answers")
    print("    (a question whose answer is cached, or where nothing passes the filters, costs no call)")
    if args.dry_run:
        return

    from app.core.gemini import get_gemini_client

    gemini = get_gemini_client()
    client = CachedGeminiClient(gemini, generations, args.pace_generate)

    # 1. Follow-ups: rewrite into a standalone question first, like POST /chat.
    search_question = {q.id: q.question for q in questions}
    for q in follow_ups:
        history = history_messages(q, settings.history_messages)
        try:
            search_question[q.id] = rewrite_question(client, settings.generation_model, history, q.question)
        except DailyLimitReached:
            raise SystemExit(daily_limit_message(0, len(questions))) from None
        print(f"  rewrote {q.id}: {q.question!r} -> {search_question[q.id]!r}")

    # 2. Embeddings: everything still missing, in as few requests as possible.
    missing = embedder.plan({QUERY: list(search_question.values()), DOCUMENT: [c.text for c in chunks]})
    embedding_requests = embedder.count_requests(missing)
    if embedding_requests:
        embedder.fetch(gemini, missing)

    # 3. Search, filter and answer each question, in a temporary ChromaDB.
    ids_by_filename = {pdf.filename: pdf.document_id for pdf in pdfs}
    outcomes = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        store = build_index(Path(folder), setup, chunks, embedder.cache)
        for number, q in enumerate(questions, 1):
            embedding = embedder.cache.get(search_question[q.id], QUERY)
            document_ids = [ids_by_filename[name] for name in q.documents]
            ranked = store.search(embedding, top_k=RANK_DEPTH, document_ids=document_ids)
            kept = filter_results(ranked[: settings.top_k], settings.max_distance, settings.relative_margin)
            try:
                response = answer_from_chunks(q.question, search_question[q.id], kept, client, settings)
            except DailyLimitReached:
                raise SystemExit(daily_limit_message(len(outcomes), len(questions))) from None
            outcomes.append(Outcome(q, search_question[q.id], ranked, kept, response))
            print(f"  [{number}/{len(questions)}] {q.id}: {'found' if response.found else 'not found'}"
                  f" (Gemini calls so far: {client.models.calls})")

    # 4. Score, per part of the split.
    records = []
    for outcome in outcomes:
        record = score(outcome) | {"part": part_of[outcome.question.id]}
        records.append(record)
    parts = [p for p in ("test", "dev") if any(r["part"] == p for r in records)]
    summary = {
        part: {m: breakdown([r for r in records if r["part"] == part], m) for m in ANSWER_METRICS + RETRIEVAL_METRICS}
        for part in parts
    }
    if len(parts) > 1:
        summary["all"] = {m: breakdown(records, m) for m in ANSWER_METRICS + RETRIEVAL_METRICS}

    failures = []
    for outcome, record in zip(outcomes, records):
        problem = failure(outcome, record)
        if problem:
            failures.append(problem | {"part": record["part"]})

    data = {
        "info": {
            "date": f"{datetime.now():%Y-%m-%d %H:%M}",
            "part": args.part,
            "questions": len(questions),
            "generation_model": settings.generation_model,
            "embedding_model": settings.embedding_model,
            "settings": {
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "max_distance": settings.max_distance,
                "relative_margin": settings.relative_margin,
                "top_k": settings.top_k,
            },
            "gemini_calls": {"generation": client.models.calls, "embedding_requests": embedding_requests},
        },
        "summary": summary,
        "failures": failures,
        "questions": [
            record | {
                "question": o.question.question,
                "search_question": o.search_question,
                "answer": o.response.answer,
                "found": o.response.found,
                "sources": [f"{s.filename} p.{s.page}" for s in o.response.sources],
            }
            for o, record in zip(outcomes, records)
        ],
    }
    json_path, md_path = save(f"full_{args.part}", data, full_markdown(data))
    print(f"\nSaved {json_path.name} and {md_path.name} in eval/results/")
    print(f"Gemini calls made: {client.models.calls} generation, {embedding_requests} embedding requests")


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

    full = modes.add_parser("full", help="the whole pipeline with answers, scored")
    full.add_argument("--part", choices=["test", "dev", "all"], default="test")
    full.add_argument("--chunk-size", type=int, required=True)
    full.add_argument("--max-distance", type=float, required=True)
    full.add_argument("--margin", type=float, required=True)
    full.add_argument("--ids", default="", help="only these question ids, comma-separated")
    full.add_argument("--limit", type=int, help="only the first N questions")
    full.add_argument("--pace", type=float, default=60.0, help="seconds between embedding requests")
    full.add_argument("--pace-generate", type=float, default=15.0, help="seconds between answer requests")
    full.add_argument("--dry-run", action="store_true", help="only print the Gemini calls needed")
    full.set_defaults(run=run_full)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
