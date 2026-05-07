# OpenLimno calibration workflow. SPEC §3.5.
#
# Drives `openlimno calibrate` for one or more case YAMLs against observed
# rating curves. Designed for local + Slurm execution (snakemake --profile).
#
# Usage:
#   snakemake -s src/openlimno/workflows/snakefiles/calibrate.smk \
#             --config case=examples/lemhi/case.yaml \
#                       observed=data/lemhi/rating_curve.parquet \
#             --cores 1

CASE = config.get("case")
OBSERVED = config.get("observed")
ALGO = config.get("algo", "scipy")

if not CASE or not OBSERVED:
    raise ValueError(
        "Provide --config case=<yaml> observed=<parquet|csv> "
        "(see Snakefile docstring)"
    )

OUT_DIR = config.get("out", "calibration_out/")
LOG = f"{OUT_DIR}/calibrate.log"

rule all:
    input:
        f"{OUT_DIR}/calibration.json",

rule calibrate:
    input:
        case=CASE,
        observed=OBSERVED,
    output:
        json=f"{OUT_DIR}/calibration.json",
    log:
        LOG,
    params:
        algo=ALGO,
    shell:
        """
        mkdir -p $(dirname {output.json})
        openlimno calibrate {input.case} \\
            --observed {input.observed} \\
            --algo {params.algo} 2>&1 | tee {log} \\
            | tail -1 > {output.json}.txt
        # Convert plain text result to JSON for downstream consumption
        python -c "import json, re, sys; \\
text = open('{output.json}.txt').read(); \\
m = re.search(r'(\\d+\\.\\d+) → (\\d+\\.\\d+)', text); \\
json.dump({{'initial_n': float(m.group(1)) if m else None, \\
           'calibrated_n': float(m.group(2)) if m else None, \\
           'raw_output': text.strip()}}, \\
           open('{output.json}', 'w'), indent=2)"
        """
