# Source before running the tests:  source tests/env.sh
# Tests use a throwaway settings file (never ~/.config/cm1view/config.toml) and the
# settings the older tests were written for: the pressure-decomposition script and
# writes into output files (smoke8/11 write only into copies).
# Activate the cm1view environment first (conda activate cm1view).
python -c "import panel, cm1view" 2>/dev/null || echo "tests/env.sh: activate the cm1view environment first" >&2
export CM1VIEW_CONFIG="$(mktemp -d "${TMPDIR:-/tmp}/cm1view-testcfg-XXXXXX")/config.toml"
export CM1VIEW_PDECOMP_SCRIPT="${CM1VIEW_PDECOMP_SCRIPT:-/glade/work/rasaba/phd_scripts/pdecomp_new_fixed_mp.py}"
export CM1VIEW_ALLOW_WRITES_TO_OUTPUT=1
