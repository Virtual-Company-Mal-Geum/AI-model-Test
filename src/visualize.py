from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MEDIATE_DIR = ROOT / "mediate-files"
RESULT_DIR = ROOT / "result-files"
DEFAULT_INPUT = MEDIATE_DIR / "geo_correlation_dataset.csv"
DEFAULT_PLOT = RESULT_DIR / "geo_correlation_scatter.png"
DEFAULT_SUMMARY = RESULT_DIR / "geo_correlation_summary.json"
QUESTION_PLOTS_DIR = RESULT_DIR / "question-scatters"
KOREAN_FONT_PATHS = [
    Path("C:/Windows/Fonts/malgun.ttf"),
    Path("C:/Windows/Fonts/malgunbd.ttf"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
]


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows: list[dict[str, Any]] = []
        for row in csv.DictReader(csv_file):
            try:
                rows.append(
                    {
                        "question": row["question"],
                        "url": row["url"],
                        "Mention Rate": float(row["Mention Rate"]),
                        "Total Score": float(row["Total Score"]),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
        return rows


def rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_den == 0 or y_den == 0:
        return None
    return numerator / (x_den * y_den)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    return pearson(rank(xs), rank(ys))


def slugify(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-")
    return value[:100] or "question"


def configure_font() -> None:
    import matplotlib
    from matplotlib import font_manager

    for font_path in KOREAN_FONT_PATHS:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            font_name = font_manager.FontProperties(fname=str(font_path)).get_name()
            matplotlib.rcParams["font.family"] = font_name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return


def plot_scatter(path: Path, rows: list[dict[str, Any]], rho: float | None, title_prefix: str) -> None:
    import matplotlib.pyplot as plt

    configure_font()
    plt.figure(figsize=(11, 7))
    plt.scatter(
        [row["Mention Rate"] for row in rows],
        [row["Total Score"] for row in rows],
        alpha=0.78,
        s=46,
        color="#2563eb",
    )

    title = title_prefix
    if rho is not None:
        title += f" (Spearman rho={rho:.3f})"
    plt.title(title)
    plt.xlabel("ChatGPT Mention Rate")
    plt.ylabel("GEO Total Score")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize GEO score and ChatGPT mention-rate correlation.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--plot", type=Path, default=DEFAULT_PLOT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    QUESTION_PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows(args.input)
    xs = [row["Mention Rate"] for row in rows]
    ys = [row["Total Score"] for row in rows]
    rho = spearman(xs, ys)

    by_question: dict[str, dict[str, Any]] = {}
    for question in sorted({row["question"] for row in rows}):
        subset = [row for row in rows if row["question"] == question]
        qx = [row["Mention Rate"] for row in subset]
        qy = [row["Total Score"] for row in subset]
        question_rho = spearman(qx, qy)
        question_plot = QUESTION_PLOTS_DIR / f"{slugify(question)}.png"
        plot_scatter(question_plot, subset, question_rho, f"{question}: Mention Rate vs GEO Total Score")
        by_question[question] = {
            "n": len(subset),
            "spearman_correlation": question_rho,
            "plot": str(question_plot.relative_to(ROOT)),
        }

    summary = {
        "n": len(rows),
        "spearman_correlation": rho,
        "by_question": by_question,
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_scatter(args.plot, rows, rho, "ChatGPT Mention Rate vs GEO Total Score")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote plot to {args.plot.relative_to(ROOT)}")
    print(f"Wrote question plots to {QUESTION_PLOTS_DIR.relative_to(ROOT)}")
    print(f"Wrote summary to {args.summary.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
