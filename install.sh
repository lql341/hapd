#!/usr/bin/env bash
# Install hapd as an Environment Modules package.
#
#   ./install.sh                      # -> $MODULEFILES_DIR (or ~/opt/modulefiles)
#   ./install.sh --module-dir DIR     # -> DIR/hapd/<version>
#   ./install.sh --no-link            # do not symlink into ~/.local/bin
#
# The generated modulefile sets PATH and HAPD_HOME, and sources an optional
# machine-local `hapd.local.tcl` next to this script for secrets (git ignored).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(tr -d '\n\r ' < "$ROOT/VERSION")"
[[ -n $VERSION ]] || { echo "missing $ROOT/VERSION" >&2; exit 1; }

MODULE_DIR="${MODULEFILES_DIR:-$HOME/opt/modulefiles}"
LINK=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --module-dir) MODULE_DIR="$2"; shift 2 ;;
        --no-link) LINK=0; shift ;;
        -h|--help) sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

TEMPLATE="$ROOT/modulefiles/hapd/$VERSION.in"
[[ -f $TEMPLATE ]] || { echo "missing template: $TEMPLATE" >&2; exit 1; }

DEST="$MODULE_DIR/hapd"
mkdir -p "$DEST"
sed -e "s|@ROOT@|$ROOT|g" -e "s|@VERSION@|$VERSION|g" "$TEMPLATE" > "$DEST/$VERSION"
echo "modulefile : $DEST/$VERSION"

if [[ ! -f $ROOT/hapd.local.tcl ]]; then
    cat > "$ROOT/hapd.local.tcl" <<'EOF'
# Machine-local hapd settings. Not tracked by git.
# Uncomment and edit to point hapd at your signing material:

# setenv HAPD_P12      /path/to/my-key.p12
# setenv HAPD_CERT     /path/to/my-debug.cer
# setenv HAPD_PROFILE  /path/to/my-debug.p7b
# setenv HAPD_P12_PWD  change-me
# setenv HAPD_ALIAS    my-key
EOF
    echo "overlay    : $ROOT/hapd.local.tcl (edit it to add signing material)"
fi

if [[ $LINK == 1 ]]; then
    mkdir -p "$HOME/.local/bin"
    ln -sf "$ROOT/hapd" "$HOME/.local/bin/hapd"
    echo "symlink    : $HOME/.local/bin/hapd"
fi

chmod +x "$ROOT/hapd"
echo
echo "Load it:"
echo "  module load hapd/$VERSION"
echo
echo "If '$MODULE_DIR' is not in MODULEPATH yet, add it once (e.g. in module-init.sh):"
echo "  module use $MODULE_DIR"
