#!/bin/bash

# =========================
# Parameters
# =========================
node_rank=0
num_nodes=1
project="M5eq_1"
filterid_mwcs=1
components=(EE EN EZ NE NN NZ ZE ZN ZZ)

# =========================
# Run MWCS
# =========================
for component in "${components[@]}"; do

    echo "========================================"
    echo "Starting component: $component"
    echo "Project: $project"
    echo "Filter ID: $filterid_mwcs"
    echo "Time: $(date)"
    echo "========================================"

    python run_mwcs_zarr.py \
        --node_rank "$node_rank" \
        --num_nodes "$num_nodes" \
        --project "$project" \
        --filterid_mwcs "$filterid_mwcs" \
        --component "$component"

    status=$?

    if [ $status -ne 0 ]; then
        echo "ERROR: Component $component failed with exit code $status"
        exit $status
    fi

    echo "Finished component: $component"
    echo "Time: $(date)"
done

echo "========================================"
echo "All components finished successfully!"
echo "Time: $(date)"
echo "========================================"
