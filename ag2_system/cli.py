from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ag2_system.core import load_cases, load_experiment_config
from ag2_system.orchestration.run_many_agent import run_many_agent_case


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the standalone AG2 hierarchical many-agent system")
    parser.add_argument("--config", default="configs/experiment.json", help="experiment JSON file")
    parser.add_argument("--dataset", help="override dataset JSON path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="run deterministic control flow without API calls")
    mode.add_argument("--live", action="store_true", help="force live AG2 model calls")
    parser.add_argument("--limit", type=int, help="maximum number of cases")
    parser.add_argument("--case-index", type=int, help="run one zero-based dataset index")
    parser.add_argument("--force", action="store_true", help="overwrite an existing case result")
    return parser.parse_args()


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return cleaned or "case"


def main() -> None:
    args = parse_args()
    config = load_experiment_config(args.config)
    if args.dataset:
        config.dataset_path = str(Path(args.dataset).resolve())
    if args.mock:
        config.mock = True
    if args.live:
        config.mock = False
    if args.limit is not None:
        config.limit = max(0, args.limit)

    cases = load_cases(config.dataset_path)
    if args.case_index is not None:
        if args.case_index < 0 or args.case_index >= len(cases):
            raise IndexError(f"case-index must be between 0 and {len(cases) - 1}")
        selected = [cases[args.case_index]]
    else:
        limit = config.limit or len(cases)
        selected = cases[:limit]

    output_dir = Path(config.output_dir) / config.stage / _safe_filename(config.model_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in selected:
        output_path = output_dir / f"{_safe_filename(case.case_url)}.json"
        if output_path.exists() and not args.force:
            print(f"[SKIP] {output_path}")
            continue
        print(f"[RUN] case={case.case_url} stage={config.stage} mock={config.mock}")
        result = run_many_agent_case(case, config)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(result.to_dict(), file, ensure_ascii=False, indent=2)
        print(f"[DONE] {output_path}")


if __name__ == "__main__":
    main()
