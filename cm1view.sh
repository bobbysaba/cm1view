#!/bin/bash
# Launch the CM1 viewer:  ./cm1view.sh /path/to/cm1/run [--port 5006] [--cache-gb 16]
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! python -c "import panel, netCDF4, metpy, numba" >/dev/null 2>&1; then
    module load conda >/dev/null 2>&1
    conda activate npl
fi
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
exec python -m cm1view "$@"
