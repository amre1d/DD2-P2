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

COOLING_RATES = [0.75, 0.8, 0.85, 0.9, 0.95]


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
    )

    return {
        "placement_mode": mode,
        "design": design_path.name,
        "cooling_rate": cooling_rate,
        "initial_twl": result["initial_cost"],
        "final_current_twl": result["current_cost"],
        "final_best_twl": result["best_cost"],
        "temperature_steps": result["temperature_steps"],
        "attempted_moves": result["attempted_moves"],
        "accepted_moves": result["accepted_moves"],
        "moves_per_temperature": result["moves_per_temperature"],
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rationale", "random", "both"], default="rationale")
    parser.add_argument("--output", default="cooling_rate_vs_twl.csv")
    parser.add_argument("--design", choices=DESIGN_NAMES + ["all"], default="all")
    parser.add_argument("--candidate-count", type=int, default=1)
    return parser.parse_args()


def main():
    args = parse_args()
    rows = []

    for mode in selected_modes(args.mode):
        for design_path in selected_designs(args.design):
            for cooling_rate in COOLING_RATES:
                row = run_case(mode, design_path, cooling_rate, args.candidate_count)
                rows.append(row)
                print(
                    "finished"
                    f" {mode} {design_path.name}"
                    f" CR={cooling_rate}: best={row['final_best_twl']}"
                )

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "placement_mode",
                "design",
                "cooling_rate",
                "initial_twl",
                "final_current_twl",
                "final_best_twl",
                "temperature_steps",
                "attempted_moves",
                "accepted_moves",
                "moves_per_temperature",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {args.output} with {len(rows)} rows.")


if __name__ == "__main__":
    main()
