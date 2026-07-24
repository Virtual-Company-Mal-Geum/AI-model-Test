from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run_step(name: str, command: list[str]) -> None:
    print(f"\n=== {name} ===")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GEO correlation test steps 6-10.")
    parser.add_argument("--skip-preprocess", action="store_true")
    parser.add_argument("--skip-evaluate", action="store_true")
    parser.add_argument("--skip-visualize", action="store_true")
    parser.add_argument("--eval-url", help="Override GEO evaluator API URL.")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--verify-ssl", action="store_true")
    args = parser.parse_args()

    python = sys.executable

    if not args.skip_preprocess:
        run_step("Step 6: preprocess URLs", [python, str(SRC / "preprocess_urls.py")])

    if not args.skip_evaluate:
        evaluate_cmd = [
            python,
            str(SRC / "evaluate.py"),
            "--timeout",
            str(args.timeout),
            "--sleep",
            str(args.sleep),
        ]
        if args.eval_url:
            evaluate_cmd.extend(["--eval-url", args.eval_url])
        if args.verify_ssl:
            evaluate_cmd.append("--verify-ssl")
        run_step("Step 7-8: evaluate GEO scores and join mention rates", evaluate_cmd)

    if not args.skip_visualize:
        run_step("Step 9-10: visualize and calculate Spearman correlation", [python, str(SRC / "visualize.py")])


if __name__ == "__main__":
    main()
