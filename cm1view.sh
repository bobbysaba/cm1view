#!/bin/bash
# Launch the CM1 viewer:  ./cm1view.sh [/path/to/cm1/run] [--port 5006] [--cache-gb 16]
# Uses the active Python; create it once with:  conda env create -f environment.yml
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! python -c "import panel, netCDF4, metpy, numba, plotly" >/dev/null 2>&1; then
    echo "cm1view: this Python lacks cm1view's packages. Create the environment once," >&2
    echo "  conda env create -f $HERE/environment.yml" >&2
    echo "then run:  conda activate cm1view" >&2
    exit 1
fi
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
exec python -m cm1view "$@"
