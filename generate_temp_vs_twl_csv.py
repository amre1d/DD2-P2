import argparse
import csv
from pathlib import Path

import placer


DESIGN_NAMES = [
    "design_1_small",
    "design_2_medium",
    "design_3_large",
    "design_4_dense",
    "design_5_extreme",
]


def selected_designs(name: str):
    if name == "all":
        return [Path("designs") / f"{design}.txt" for design in DESIGN_NAMES]
    return [Path("designs") / f"{name}.txt"]


def selected_modes(mode: str):
    if mode == "both":
        return ["rationale", "random"]
    return [mode]


def run_case(mode: str, design_path: Path, cooling_rate: float, candidate_count: int):
    design = placer.parse_netlist(str(design_path))
    placements, _ = placer.initial_place(design, mode)
    result = placer.anneal(
        design,
        placements,
        cooling_rate=cooling_rate,
        candidate_count=candidate_count,
        collect_history=True,
    )

    rows = []
    for row in result["history"]:
        rows.append(
            {
                "placement_mode": mode,
                "design": design_path.name,
                "temperature_step": row["temperature_step"],
                "temperature": row["temperature"],
                "current_twl": row["current_twl"],
                "best_twl": row["best_twl"],
                "attempted_moves": row["attempted_moves"],
                "accepted_moves": row["accepted_moves"],
            }
        )
    return rows


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rationale", "random", "both"], default="rationale")
    parser.add_argument("--output", default="temp_vs_twl_cr_0_95.csv")
    parser.add_argument("--design", choices=DESIGN_NAMES + ["all"], default="all")
    parser.add_argument("--cooling-rate", type=float, default=0.95)
    parser.add_argument("--candidate-count", type=int, default=1)
    return parser.parse_args()


def main():
    args = parse_args()
    row_count = 0

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "placement_mode",
                "design",
                "temperature_step",
                "temperature",
                "current_twl",
                "best_twl",
                "attempted_moves",
                "accepted_moves",
            ],
        )
        writer.writeheader()

        for mode in selected_modes(args.mode):
            for design_path in selected_designs(args.design):
                rows = run_case(mode, design_path, args.cooling_rate, args.candidate_count)
                writer.writerows(rows)
                row_count += len(rows)
                print(f"finished {mode} {design_path.name}: {len(rows)} rows")

    print(f"Wrote {args.output} with {row_count} rows.")


if __name__ == "__main__":
    main()
