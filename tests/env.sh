# Source before running the tests:  source tests/env.sh
# Tests use a throwaway settings file (never ~/.config/cm1view/config.toml) and the
# settings the older tests were written for: the pressure-decomposition script and
# writes into output files (smoke8/11 write only into copies).
module load conda >/dev/null 2>&1
conda activate npl
export CM1VIEW_CONFIG="$(mktemp -d "${TMPDIR:-/tmp}/cm1view-testcfg-XXXXXX")/config.toml"
export CM1VIEW_PDECOMP_SCRIPT="${CM1VIEW_PDECOMP_SCRIPT:-/glade/work/rasaba/phd_scripts/pdecomp_new_fixed_mp.py}"
export CM1VIEW_ALLOW_WRITES_TO_OUTPUT=1
