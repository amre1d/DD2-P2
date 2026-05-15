import argparse
import glob
import math
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CELL_TYPES = ("T0", "T1", "T2", "T3")
TYPE_NUMBERS = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
EMPTY_NUMBER = -1
PIN_NUMBER = 9

MASTER_TILE = [
    ["T0", "T1", "T0", "T2", "T0"],
    ["T1", "T0", "T1", "T0", "T1"],
    ["T0", "T2", "T3", "T0", "T2"],
    ["T1", "T0", "T1", "T0", "T0"],
    ["T0", "T0", "T0", "T0", "T0"],
]


@dataclass
class Component:
    cid: int
    kind: str
    cell_type: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None


@dataclass
class Design:
    path: str
    num_components: int
    num_nets: int
    ny: int
    nx: int
    num_fixed_pins: int
    components: Dict[int, Component]
    nets: List[List[int]]
    warnings: List[str]


@dataclass
class PlacementRecord:
    cid: int
    cell_type: str
    x: int
    y: int
    estimate_x: float
    estimate_y: float
    order: int
    anchor_count: int
    pin_anchor_count: int
    used_fallback: bool


def parse_netlist(path: str) -> Design:
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError("Input file is empty.")

    header = lines[0].split()
    if len(header) != 5:
        raise ValueError("Header must be: NumCells NumNets ny nx NumFixedPins")

    num_components = int(header[0])
    num_nets = int(header[1])
    ny = int(header[2])
    nx = int(header[3])
    num_fixed_pins = int(header[4])

    components: Dict[int, Component] = {}
    warnings: List[str] = []
    index = 1

    for _ in range(num_components):
        parts = lines[index].split()
        index += 1

        if len(parts) == 4 and parts[3] == "P":
            cid = int(parts[0])
            x = int(parts[1])
            y = int(parts[2])
            components[cid] = Component(cid=cid, kind="pin", x=x, y=y)
            if not is_perimeter(x, y, nx, ny):
                warnings.append(f"Pin {cid} is not on perimeter: ({x}, {y})")
        elif len(parts) == 2 and parts[1] in CELL_TYPES:
            cid = int(parts[0])
            components[cid] = Component(cid=cid, kind="cell", cell_type=parts[1])
        else:
            raise ValueError(f"Invalid component line: {' '.join(parts)}")

    nets: List[List[int]] = []
    for net_index in range(num_nets):
        parts = lines[index].split()
        index += 1
        declared_count = int(parts[0])
        net_ids = [int(x) for x in parts[1:]]

        if declared_count != len(net_ids):
            warnings.append(
                f"Net {net_index} says {declared_count} connections, "
                f"but has {len(net_ids)} IDs."
            )

        for cid in net_ids:
            if cid not in components:
                warnings.append(f"Net {net_index} references missing component ID {cid}")

        nets.append(net_ids)

    actual_pins = sum(1 for c in components.values() if c.kind == "pin")
    if actual_pins != num_fixed_pins:
        warnings.append(
            f"Header says {num_fixed_pins} fixed pins, but parsed {actual_pins}."
        )

    return Design(
        path=path,
        num_components=num_components,
        num_nets=num_nets,
        ny=ny,
        nx=nx,
        num_fixed_pins=num_fixed_pins,
        components=components,
        nets=nets,
        warnings=warnings,
    )


def is_perimeter(x: int, y: int, nx: int, ny: int) -> bool:
    return x == 0 or y == 0 or x == nx - 1 or y == ny - 1


def site_type_at(x: int, y: int, nx: int, ny: int) -> str:
    if is_perimeter(x, y, nx, ny):
        return "P"
    return MASTER_TILE[(y - 1) % 5][(x - 1) % 5]


def legal_sites_by_type(nx: int, ny: int) -> Dict[str, List[Tuple[int, int]]]:
    sites = {cell_type: [] for cell_type in CELL_TYPES}
    for y in range(ny):
        for x in range(nx):
            cell_type = site_type_at(x, y, nx, ny)
            if cell_type in sites:
                sites[cell_type].append((x, y))
    return sites


def build_net_membership(design: Design) -> Dict[int, List[List[int]]]:
    memberships: Dict[int, List[List[int]]] = defaultdict(list)
    for net in design.nets:
        for cid in net:
            memberships[cid].append(net)
    return memberships


def nearest_legal_site(
    available_sites: List[Tuple[int, int]],
    estimate_x: float,
    estimate_y: float,
) -> Tuple[int, int]:
    best_site = available_sites[0]
    best_key = None

    for x, y in available_sites:
        distance2 = (x - estimate_x) ** 2 + (y - estimate_y) ** 2
        manhattan = abs(x - estimate_x) + abs(y - estimate_y)
        key = (distance2, manhattan, y, x)
        if best_key is None or key < best_key:
            best_key = key
            best_site = (x, y)

    return best_site


def random_initial_place(
    design: Design,
) -> Tuple[Dict[int, PlacementRecord], Dict[str, int]]:
    available_sites = legal_sites_by_type(design.nx, design.ny)
    unplaced = [c.cid for c in design.components.values() if c.kind == "cell"]

    rng = random.Random()
    rng.shuffle(unplaced)
    for cell_type in CELL_TYPES:
        rng.shuffle(available_sites[cell_type])

    placements: Dict[int, PlacementRecord] = {}
    for order, cid in enumerate(unplaced):
        comp = design.components[cid]
        site = available_sites[comp.cell_type].pop()
        placements[cid] = PlacementRecord(
            cid=cid,
            cell_type=comp.cell_type,
            x=site[0],
            y=site[1],
            estimate_x=float(site[0]),
            estimate_y=float(site[1]),
            order=order,
            anchor_count=0,
            pin_anchor_count=0,
            used_fallback=False,
        )

    return placements, {"placed_cells": len(placements), "fallback_cells": 0}


def rationale_initial_place(
    design: Design,
) -> Tuple[Dict[int, PlacementRecord], Dict[str, int]]:
    available_sites = legal_sites_by_type(design.nx, design.ny)
    net_membership = build_net_membership(design)
    known_positions: Dict[int, Tuple[float, float]] = {}

    for comp in design.components.values():
        if comp.kind == "pin":
            known_positions[comp.cid] = (float(comp.x), float(comp.y))

    unplaced = {c.cid for c in design.components.values() if c.kind == "cell"}
    placements: Dict[int, PlacementRecord] = {}
    fallback_count = 0
    center_x = (design.nx - 1) / 2.0
    center_y = (design.ny - 1) / 2.0

    while unplaced:
        choice = choose_rationale_cell(design, net_membership, known_positions, unplaced)

        if choice is None:
            cid = min(unplaced)
            estimate_x = center_x
            estimate_y = center_y
            anchor_count = 0
            pin_anchor_count = 0
            used_fallback = True
            fallback_count += 1
        else:
            cid, estimate_x, estimate_y, anchor_count, pin_anchor_count = choice
            used_fallback = False

        comp = design.components[cid]
        site = nearest_legal_site(available_sites[comp.cell_type], estimate_x, estimate_y)
        available_sites[comp.cell_type].remove(site)
        known_positions[cid] = (float(site[0]), float(site[1]))

        placements[cid] = PlacementRecord(
            cid=cid,
            cell_type=comp.cell_type,
            x=site[0],
            y=site[1],
            estimate_x=estimate_x,
            estimate_y=estimate_y,
            order=len(placements),
            anchor_count=anchor_count,
            pin_anchor_count=pin_anchor_count,
            used_fallback=used_fallback,
        )
        unplaced.remove(cid)

    return placements, {"placed_cells": len(placements), "fallback_cells": fallback_count}


def choose_rationale_cell(
    design: Design,
    net_membership: Dict[int, List[List[int]]],
    known_positions: Dict[int, Tuple[float, float]],
    unplaced: set,
):
    best = None

    for cid in sorted(unplaced):
        anchors: List[Tuple[float, float]] = []
        pin_anchor_count = 0

        for net in net_membership.get(cid, []):
            for other_cid in net:
                if other_cid == cid or other_cid not in known_positions:
                    continue
                anchors.append(known_positions[other_cid])
                if design.components[other_cid].kind == "pin":
                    pin_anchor_count += 1

        if not anchors:
            continue

        estimate_x = sum(x for x, _ in anchors) / len(anchors)
        estimate_y = sum(y for _, y in anchors) / len(anchors)
        candidate = (cid, estimate_x, estimate_y, len(anchors), pin_anchor_count)

        if best is None:
            best = candidate
            continue

        _, _, _, best_anchor_count, best_pin_anchor_count = best
        if len(anchors) > best_anchor_count:
            best = candidate
        elif len(anchors) == best_anchor_count and pin_anchor_count > best_pin_anchor_count:
            best = candidate

    return best


def initial_place(
    design: Design,
    mode: str,
) -> Tuple[Dict[int, PlacementRecord], Dict[str, int]]:
    if mode == "random":
        return random_initial_place(design)
    if mode == "rationale":
        return rationale_initial_place(design)
    raise ValueError("mode must be random or rationale")


def build_position_map(
    design: Design,
    placements: Dict[int, PlacementRecord],
) -> Dict[int, Tuple[int, int]]:
    positions: Dict[int, Tuple[int, int]] = {}

    for comp in design.components.values():
        if comp.kind == "pin":
            positions[comp.cid] = (comp.x, comp.y)

    for cid, record in placements.items():
        positions[cid] = (record.x, record.y)

    return positions


def net_hpwl(net: List[int], positions: Dict[int, Tuple[int, int]]) -> int:
    xs = [positions[cid][0] for cid in net]
    ys = [positions[cid][1] for cid in net]
    return max(xs) - min(xs) + max(ys) - min(ys)


def total_hpwl(design: Design, positions: Dict[int, Tuple[int, int]]) -> int:
    return sum(net_hpwl(net, positions) for net in design.nets)


def placement_to_cell_map(placements: Dict[int, PlacementRecord]) -> Dict[str, object]:
    cells = {}
    for record in placements.values():
        cells[f"{record.x},{record.y}"] = {
            "cid": record.cid,
            "type": record.cell_type,
            "order": record.order,
            "estimate": [round(record.estimate_x, 3), round(record.estimate_y, 3)],
            "anchors": record.anchor_count,
            "pin_anchors": record.pin_anchor_count,
            "fallback": record.used_fallback,
        }
    return cells


def affected_nets_for_cells(
    net_membership: Dict[int, List[List[int]]],
    cid_a: int,
    cid_b: Optional[int] = None,
) -> List[List[int]]:
    affected_nets = []
    seen_nets = set()

    for cid in (cid_a, cid_b):
        if cid is None:
            continue
        for net in net_membership[cid]:
            net_id = id(net)
            if net_id not in seen_nets:
                seen_nets.add(net_id)
                affected_nets.append(net)

    return affected_nets


def evaluate_candidate(
    positions: Dict[int, Tuple[int, int]],
    net_membership: Dict[int, List[List[int]]],
    cid_a: int,
    new_pos_a: Tuple[int, int],
    cid_b: Optional[int] = None,
    new_pos_b: Optional[Tuple[int, int]] = None,
) -> int:
    affected_nets = affected_nets_for_cells(net_membership, cid_a, cid_b)
    old_cost = sum(net_hpwl(net, positions) for net in affected_nets)

    old_pos_a = positions[cid_a]
    positions[cid_a] = new_pos_a

    old_pos_b = None
    if cid_b is not None and new_pos_b is not None:
        old_pos_b = positions[cid_b]
        positions[cid_b] = new_pos_b

    new_cost = sum(net_hpwl(net, positions) for net in affected_nets)

    positions[cid_a] = old_pos_a
    if cid_b is not None and old_pos_b is not None:
        positions[cid_b] = old_pos_b

    return new_cost - old_cost


def build_move_state(
    design: Design,
    placements: Dict[int, PlacementRecord],
):
    type_cells = {cell_type: [] for cell_type in CELL_TYPES}
    occupied_by_type = {cell_type: set() for cell_type in CELL_TYPES}

    for cid, record in placements.items():
        type_cells[record.cell_type].append(cid)
        occupied_by_type[record.cell_type].add((record.x, record.y))

    legal_sites = legal_sites_by_type(design.nx, design.ny)
    empty_sites = {cell_type: [] for cell_type in CELL_TYPES}
    for cell_type in CELL_TYPES:
        for site in legal_sites[cell_type]:
            if site not in occupied_by_type[cell_type]:
                empty_sites[cell_type].append(site)

    movable_types = []
    for cell_type in CELL_TYPES:
        has_swap = len(type_cells[cell_type]) >= 2
        has_move = len(type_cells[cell_type]) >= 1 and len(empty_sites[cell_type]) >= 1
        if has_swap or has_move:
            movable_types.append(cell_type)

    return type_cells, empty_sites, movable_types


def sample_candidate(rng, positions, movable_types, type_cells, empty_sites):
    cell_type = rng.choice(movable_types)
    cells = type_cells[cell_type]
    can_swap = len(cells) >= 2
    can_move = len(empty_sites[cell_type]) >= 1
    do_move = can_move and (not can_swap or rng.random() < 0.5)

    if do_move:
        cid_a = cells[rng.randrange(len(cells))]
        return {
            "kind": "move",
            "cell_type": cell_type,
            "cid_a": cid_a,
            "cid_b": None,
            "new_pos_a": empty_sites[cell_type][rng.randrange(len(empty_sites[cell_type]))],
            "new_pos_b": None,
        }

    first_index = rng.randrange(len(cells))
    second_index = rng.randrange(len(cells))
    while second_index == first_index:
        second_index = rng.randrange(len(cells))

    cid_a = cells[first_index]
    cid_b = cells[second_index]
    return {
        "kind": "swap",
        "cell_type": cell_type,
        "cid_a": cid_a,
        "cid_b": cid_b,
        "new_pos_a": positions[cid_b],
        "new_pos_b": positions[cid_a],
    }


def anneal(
    design: Design,
    placements: Dict[int, PlacementRecord],
    cooling_rate: float = 0.95,
    candidate_count: int = 1,
    collect_history: bool = False,
):
    start = time.perf_counter()
    type_cells, empty_sites, movable_types = build_move_state(design, placements)
    positions = build_position_map(design, placements)
    current_cost = total_hpwl(design, positions)
    initial_cost = current_cost

    history = []
    best_cost = current_cost
    current_cell_positions = {cid: (r.x, r.y) for cid, r in placements.items()}
    best_cell_positions = dict(current_cell_positions)
    attempted_moves = 0
    accepted_moves = 0
    temperature_step = 0

    if not movable_types or current_cost == 0 or design.num_nets == 0:
        return build_anneal_result(
            design,
            placements,
            best_cell_positions,
            history,
            initial_cost,
            current_cost,
            best_cost,
            cooling_rate,
            0.0,
            0.0,
            0,
            temperature_step,
            attempted_moves,
            accepted_moves,
            candidate_count,
            start,
        )

    initial_temperature = 500.0 * initial_cost
    final_temperature = (5.0e-5 * initial_cost) / design.num_nets
    moves_per_temperature = 20 * len(placements)
    net_membership = build_net_membership(design)
    rng = random.Random(0)
    temperature = initial_temperature

    if collect_history:
        history.append(history_row(temperature_step, temperature, current_cost, best_cost, 0, 0))

    while temperature > final_temperature:
        for _ in range(moves_per_temperature):
            candidate = choose_candidate(
                rng,
                positions,
                net_membership,
                movable_types,
                type_cells,
                empty_sites,
                candidate_count,
            )
            if candidate is None:
                continue

            attempted_moves += 1
            delta = candidate["delta"]
            if delta > 0 and rng.random() >= math.exp(-float(delta) / temperature):
                continue

            accepted_moves += 1
            cid_a = candidate["cid_a"]
            cid_b = candidate["cid_b"]
            old_pos_a = positions[cid_a]
            positions[cid_a] = candidate["new_pos_a"]
            current_cell_positions[cid_a] = candidate["new_pos_a"]
            current_cost += delta

            if candidate["kind"] == "move":
                cell_type = candidate["cell_type"]
                empty_sites[cell_type].append(old_pos_a)
                empty_sites[cell_type].remove(candidate["new_pos_a"])
            else:
                positions[cid_b] = candidate["new_pos_b"]
                current_cell_positions[cid_b] = candidate["new_pos_b"]

            if current_cost < best_cost:
                best_cost = current_cost
                best_cell_positions = dict(current_cell_positions)

        temperature_step += 1
        if collect_history:
            history.append(
                history_row(
                    temperature_step,
                    temperature,
                    current_cost,
                    best_cost,
                    attempted_moves,
                    accepted_moves,
                )
            )
        temperature *= cooling_rate

    return build_anneal_result(
        design,
        placements,
        best_cell_positions,
        history,
        initial_cost,
        current_cost,
        best_cost,
        cooling_rate,
        initial_temperature,
        final_temperature,
        moves_per_temperature,
        temperature_step,
        attempted_moves,
        accepted_moves,
        candidate_count,
        start,
    )


def choose_candidate(
    rng,
    positions,
    net_membership,
    movable_types,
    type_cells,
    empty_sites,
    candidate_count,
):
    best_candidate = None
    best_delta = None

    for _ in range(candidate_count):
        candidate = sample_candidate(rng, positions, movable_types, type_cells, empty_sites)
        delta = evaluate_candidate(
            positions,
            net_membership,
            candidate["cid_a"],
            candidate["new_pos_a"],
            candidate["cid_b"],
            candidate["new_pos_b"],
        )
        candidate["delta"] = delta
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_candidate = candidate

    return best_candidate


def history_row(step, temperature, current_cost, best_cost, attempted, accepted):
    return {
        "temperature_step": step,
        "temperature": temperature,
        "current_twl": current_cost,
        "best_twl": best_cost,
        "attempted_moves": attempted,
        "accepted_moves": accepted,
    }


def build_anneal_result(
    design,
    original_placements,
    best_cell_positions,
    history,
    initial_cost,
    current_cost,
    best_cost,
    cooling_rate,
    initial_temperature,
    final_temperature,
    moves_per_temperature,
    temperature_steps,
    attempted_moves,
    accepted_moves,
    candidate_count,
    start,
):
    final_placements = {}
    for cid, record in original_placements.items():
        x, y = best_cell_positions[cid]
        final_placements[cid] = PlacementRecord(
            cid=record.cid,
            cell_type=record.cell_type,
            x=x,
            y=y,
            estimate_x=record.estimate_x,
            estimate_y=record.estimate_y,
            order=record.order,
            anchor_count=record.anchor_count,
            pin_anchor_count=record.pin_anchor_count,
            used_fallback=record.used_fallback,
        )

    return {
        "initial_cost": initial_cost,
        "current_cost": current_cost,
        "best_cost": best_cost,
        "cooling_rate": cooling_rate,
        "initial_temperature": initial_temperature,
        "final_temperature": final_temperature,
        "moves_per_temperature": moves_per_temperature,
        "temperature_steps": temperature_steps,
        "attempted_moves": attempted_moves,
        "accepted_moves": accepted_moves,
        "candidate_count": candidate_count,
        "elapsed_seconds": time.perf_counter() - start,
        "placements": final_placements,
        "history": history,
    }


def design_summary(design: Design, mode: str) -> Dict[str, object]:
    pins = [c for c in design.components.values() if c.kind == "pin"]
    cells = [c for c in design.components.values() if c.kind == "cell"]
    cell_counts = Counter(c.cell_type for c in cells)
    site_counts = Counter(
        site_type_at(x, y, design.nx, design.ny)
        for y in range(design.ny)
        for x in range(design.nx)
        if site_type_at(x, y, design.nx, design.ny) != "P"
    )
    placements, placement_meta = initial_place(design, mode)
    initial_cost = total_hpwl(design, build_position_map(design, placements))

    return {
        "path": design.path,
        "basename": Path(design.path).name,
        "grid": {"nx": design.nx, "ny": design.ny},
        "num_components": design.num_components,
        "num_nets": design.num_nets,
        "num_fixed_pins": len(pins),
        "num_movable_cells": len(cells),
        "cell_counts": {cell_type: cell_counts[cell_type] for cell_type in CELL_TYPES},
        "site_counts": {cell_type: site_counts[cell_type] for cell_type in CELL_TYPES},
        "placement": placement_meta,
        "initial_cost": initial_cost,
        "warnings": design.warnings,
    }


def placement_grid(
    design: Design,
    placements: Dict[int, PlacementRecord],
    empty_number: int = EMPTY_NUMBER,
    pin_number: int = PIN_NUMBER,
) -> List[List[int]]:
    grid = [[empty_number for _ in range(design.nx)] for _ in range(design.ny)]

    for comp in design.components.values():
        if comp.kind == "pin":
            grid[comp.y][comp.x] = pin_number

    for record in placements.values():
        grid[record.y][record.x] = TYPE_NUMBERS[record.cell_type]

    return grid


def render_grid(grid: List[List[int]]) -> str:
    return "\n".join(" ".join(f"{value:2d}" for value in row) for row in grid)


def print_grid(
    design: Design,
    placements: Dict[int, PlacementRecord],
    empty_number: int = EMPTY_NUMBER,
    pin_number: int = PIN_NUMBER,
) -> None:
    print(render_grid(placement_grid(design, placements, empty_number, pin_number)))


def design_files_from_args(args) -> List[str]:
    if args.all:
        return sorted(glob.glob("designs/*.txt"))
    return [args.design]


def run_terminal(args) -> None:
    design_files = design_files_from_args(args)
    if not design_files:
        raise SystemExit("No design files found.")

    for index, design_path in enumerate(design_files):
        design = parse_netlist(design_path)
        placements, metadata = initial_place(design, args.mode)
        result = anneal(
            design,
            placements,
            cooling_rate=args.cooling_rate,
            candidate_count=args.candidate_count,
        )

        if index:
            print()

        print(f"design: {design_path}")
        print(f"mode: {args.mode}")
        print(f"grid: {design.nx}x{design.ny}")
        print(f"placed cells: {metadata['placed_cells']}")
        print(f"fallback cells: {metadata['fallback_cells']}")
        print(f"initial TWL: {result['initial_cost']}")
        print(f"best TWL: {result['best_cost']}")
        print(f"accepted moves: {result['accepted_moves']}/{result['attempted_moves']}")
        print(f"legend: empty={args.empty_number}, pin={args.pin_number}, T0=0, T1=1, T2=2, T3=3")
        print_grid(design, result["placements"], args.empty_number, args.pin_number)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("design", nargs="?", default="designs/design_1_small.txt")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--mode", choices=["random", "rationale"], default="random")
    parser.add_argument("--cooling-rate", type=float, default=0.95)
    parser.add_argument("--candidate-count", type=int, default=1)
    parser.add_argument("--empty-number", type=int, default=EMPTY_NUMBER)
    parser.add_argument("--pin-number", type=int, default=PIN_NUMBER)
    return parser.parse_args()


def main() -> None:
    run_terminal(parse_args())


if __name__ == "__main__":
    main()
