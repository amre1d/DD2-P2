# Structured ASIC Placer

This project reads a structured ASIC netlist, places the cells on a `52 x 52`
grid, and improves the placement with simulated annealing.

The output is printed in the terminal as numbers:

- `-1` means an empty site
- `9` means a fixed pin
- `0` means an occupied `T0` site
- `1` means an occupied `T1` site
- `2` means an occupied `T2` site
- `3` means an occupied `T3` site

## Run one design

From the project folder:

```bash
python3 placer.py designs/design_1_small.txt --mode random --cooling-rate 0.95
```

For the rationale initial placement:

```bash
python3 placer.py designs/design_1_small.txt --mode rationale --cooling-rate 0.95
```

## Run the extreme design

```bash
python3 placer.py designs/design_5_extreme.txt --mode random --candidate-count 1 --cooling-rate 0.95
```

To save the output to a text file:

```bash
python3 placer.py designs/design_5_extreme.txt --mode random --candidate-count 1 --cooling-rate 0.95 > extreme_output.txt
```

## Optimized runners

These scripts use the same core logic, but try more candidate moves at each
annealing step:

```bash
python3 optimized.py designs/design_1_small.txt
python3 optimized_rationale.py designs/design_1_small.txt
```

## CSV results

Temperature vs. TWL:

```bash
python3 generate_temp_vs_twl_csv.py --mode both --design all --output temp_vs_twl.csv
```

Cooling rate comparison:

```bash
python3 generate_cooling_rate_vs_twl_csv.py --mode both --design all --output cooling_rate_vs_twl.csv
```

## Files

- `placer.py` has the parser, placement logic, annealing, and terminal grid output.
- `optimized.py` runs random initial placement with the optimized candidate search.
- `optimized_rationale.py` runs rationale initial placement with the optimized candidate search.
- `designs/` contains the benchmark input files.
