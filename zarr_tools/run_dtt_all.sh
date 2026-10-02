#!/bin/bash

# =========================
# Parameters
# =========================
project="M5eq_1"
filterid_dtt=1
components=(EE EN EZ NE NN NZ ZE ZN ZZ)

# =========================
# Run DTT
# =========================
for component in "${components[@]}"; do

    echo "========================================"
    echo "Starting component: $component"
    echo "Project: $project"
    echo "Filter ID: $filterid_dtt"
    echo "Time: $(date)"
    echo "========================================"

    python run_dtt_zarr_v2.py \
        --project "$project" \
        --filterid_dtt "$filterid_dtt" \
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
