"""Writes evaluation results: a JSON file with everything, and a short markdown summary."""

import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def fraction(part: int, whole: int) -> str:
    return f"{part}/{whole}" if whole else "n/a"


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def save(name: str, data: dict, markdown: str) -> tuple[Path, Path]:
    """Save <date>_<name>.json and .md in eval/results/ and return both paths."""
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{datetime.now():%Y-%m-%d_%H%M%S}_{name}"
    json_path, md_path = RESULTS_DIR / f"{stem}.json", RESULTS_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


# ---------- Retrieval experiments ----------


def ranking_rows(setups: dict) -> list[list[str]]:
    rows = []
    for name, result in setups.items():
        metrics = result["ranking"]["metrics"]
        rows.append(
            [name, result["chunks"]]
            + [percent(metrics[m]["overall"]["value"]) for m in ("hit@1", "hit@3", "hit@5")]
            + [f"{metrics['mrr']['overall']['value']:.3f}"]
        )
    return rows


def breakdown_rows(metrics: dict) -> list[list[str]]:
    rows = []
    for group_key, label in (("by_language", "language"), ("by_type", "type")):
        for name, hit1 in metrics["hit@1"][group_key].items():
            if hit1["count"] == 0:
                continue  # not_found questions have no correct page to rank
            rows.append(
                [f"{label}: {name}", hit1["count"], percent(hit1["value"]),
                 percent(metrics["hit@5"][group_key][name]["value"]),
                 f"{metrics['mrr'][group_key][name]['value']:.3f}"]
            )
    return rows


def retrieval_markdown(data: dict) -> str:
    info, best = data["info"], data["suggested"]
    ranking_headers = ["Setup", "Chunks", "Hit@1", "Hit@3", "Hit@5", "MRR"]
    parts = [
        "# Retrieval experiments (dev set)",
        f"Run: {info['date']}. Questions: {info['questions']} from the dev set "
        f"({info['answerable']} answerable, {info['not_found']} not found). "
        "**The test set was not used.** "
        f"Embedding model: `{info['embedding_model']}`. Chunks sent to the LLM: top {info['top_k']}.",
    ]

    ours = {name: r for name, r in data["setups"].items() if name.startswith("ours")}
    if "chunk" in data["experiments"]:
        parts += ["## Chunk size (our chunker)", table(ranking_headers, ranking_rows(ours))]

    if "splitter" in data["experiments"]:
        paired = {}
        for name in ours:
            size = name.split("-")[1]
            paired[name] = data["setups"][name]
            if f"langchain-{size}" in data["setups"]:
                paired[f"langchain-{size}"] = data["setups"][f"langchain-{size}"]
        parts += ["## Our chunker vs LangChain's RecursiveCharacterTextSplitter",
                  table(ranking_headers, ranking_rows(paired))]

    parts += [
        f"## Breakdown for `{best['setup']}`",
        table(["Group", "Questions", "Hit@1", "Hit@5", "MRR"],
              breakdown_rows(data["setups"][best["setup"]]["ranking"]["metrics"])),
    ]

    if "threshold" in data["experiments"]:
        parts += [
            f"## MAX_DISTANCE sweep (`{best['setup']}`, margin {data['threshold_margin']})",
            table(
                ["MAX_DISTANCE", "Correct page kept", "Not-found blocked", "Conflicts complete", "Avg chunks sent"],
                [[row["max_distance"], fraction(row["page_kept"], row["answerable"]),
                  fraction(row["blocked"], row["not_found"]),
                  fraction(row["conflicts_all_pages"], row["conflicts"]),
                  f"{row['avg_chunks_sent']:.1f}"] for row in data["threshold_sweep"]],
            ),
        ]

    if "margin" in data["experiments"]:
        parts += [
            f"## Relative margin sweep (`{best['setup']}`, MAX_DISTANCE {best['max_distance']})",
            table(
                ["Margin", "Correct page kept", "Conflicts complete", "Avg chunks sent"],
                [["off" if row["margin"] is None else row["margin"],
                  fraction(row["page_kept"], row["answerable"]),
                  fraction(row["conflicts_all_pages"], row["conflicts"]),
                  f"{row['avg_chunks_sent']:.1f}"] for row in data["margin_sweep"]],
            ),
        ]

    parts += [
        "## Suggested settings",
        table(["Setting", "Current", "Suggested"], [
            ["Chunk size", info["current"]["chunk_size"], best["chunk_size"]],
            ["MAX_DISTANCE", info["current"]["max_distance"], best["max_distance"]],
            ["Relative margin", info["current"]["relative_margin"],
             "off" if best["relative_margin"] is None else best["relative_margin"]],
        ]),
        "Rules, fixed before the run: chunk size = highest MRR (ties: Hit@1, then the current "
        "setting); MAX_DISTANCE = most correct pages kept + not-found questions blocked (ties: "
        "the middle value); margin = the smallest one that loses no correct page or conflict page.",
        "## Misses at the suggested settings",
        misses_markdown(data["misses"]),
    ]
    return "\n\n".join(parts) + "\n"


def misses_markdown(misses: list[dict]) -> str:
    if not misses:
        return "None."
    return table(
        ["Id", "Lang", "Type", "Problem", "Question", "Expected", "Top results (distance)"],
        [[m["id"], m["language"], m["type"], m["problem"], m["question"],
          ", ".join(m["expected"]) or "-", ", ".join(m["got"])] for m in misses],
    )
