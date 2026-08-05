from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    script: str
    arguments: tuple[str, ...] = ()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ChatGPT collection and GEO correlation pipeline."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("questions.json"),
        help="Question configuration passed to chatgpt_macro.py (default: questions.json).",
    )
    parser.add_argument(
        "--pause-for-login",
        action="store_true",
        help="Pause the macro after Chrome opens so ChatGPT login can be completed.",
    )
    parser.add_argument(
        "--start-at",
        type=int,
        choices=range(1, 8),
        default=1,
        metavar="STEP",
        help="Start at this step (1-7), reusing existing earlier outputs.",
    )
    parser.add_argument(
        "--stop-after",
        type=int,
        choices=range(1, 8),
        default=7,
        metavar="STEP",
        help="Stop after this step (1-7).",
    )
    parser.add_argument("--eval-url", help="Override the GEO evaluator API URL.")
    parser.add_argument("--timeout", type=int, default=240, help="Evaluation request timeout.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Delay between evaluations.")
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Verify the GEO evaluator HTTPS certificate.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected commands without running them.",
    )
    args = parser.parse_args()
    if args.start_at > args.stop_after:
        parser.error("--start-at cannot be greater than --stop-after")
    return args


def build_steps(args: argparse.Namespace) -> list[Step]:
    config = args.config if args.config.is_absolute() else ROOT / args.config
    macro_arguments = ["--config", str(config)]
    if args.pause_for_login:
        macro_arguments.append("--pause-for-login")

    evaluate_arguments = ["--timeout", str(args.timeout), "--sleep", str(args.sleep)]
    if args.eval_url:
        evaluate_arguments.extend(["--eval-url", args.eval_url])
    if args.verify_ssl:
        evaluate_arguments.append("--verify-ssl")

    return [
        Step(1, "Collect ChatGPT answers", "chatgpt_macro.py", tuple(macro_arguments)),
        Step(2, "Extract URL mention counts", "extract_answer_urls.py"),
        Step(3, "Calculate mention rates and build URL input", "build_url_outputs.py"),
        Step(4, "Assign URL domains", "update_domains.py"),
        Step(5, "Crawl and preprocess URLs", "preprocess_urls.py"),
        Step(6, "Evaluate GEO scores", "evaluate.py", tuple(evaluate_arguments)),
        Step(7, "Calculate correlation and create plots", "visualize.py"),
    ]


def display_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def main() -> int:
    args = parse_args()
    selected_steps = [
        step for step in build_steps(args) if args.start_at <= step.number <= args.stop_after
    ]
    started_at = time.monotonic()

    print(f"Pipeline: steps {args.start_at}-{args.stop_after}")
    for step in selected_steps:
        command = [sys.executable, str(SRC / step.script), *step.arguments]
        print(f"\n=== Step {step.number}/7: {step.name} ===", flush=True)
        print(f"> {display_command(command)}", flush=True)
        if args.dry_run:
            continue

        step_started_at = time.monotonic()
        try:
            subprocess.run(command, cwd=ROOT, check=True)
        except KeyboardInterrupt:
            print(f"\n[STOPPED] Interrupted during step {step.number}: {step.name}")
            return 130
        except subprocess.CalledProcessError as exc:
            print(
                f"\n[FAILED] Step {step.number} ({step.name}) exited with code "
                f"{exc.returncode}. Fix the error and resume with --start-at {step.number}."
            )
            return exc.returncode or 1
        elapsed = time.monotonic() - step_started_at
        print(f"[DONE] Step {step.number} completed in {elapsed:.1f}s", flush=True)

    if args.dry_run:
        print("\n[DRY RUN] No commands were executed.")
    else:
        elapsed = time.monotonic() - started_at
        print(f"\n[SUCCESS] Pipeline completed in {elapsed:.1f}s.")
        print(f"Results: {ROOT / 'result-files'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
