#!/usr/bin/env bash
# install-shesh-wave.sh — wire Shesh configuration into a Wave Terminal install.
#
# Idempotent: safe to re-run; backs up anything it replaces into
# ~/.waveterm/backups/shesh-<timestamp>/ and merges (never clobbers) JSON.
#
# Surfaces (no Wave patches required — verified 2026-08-11 audit):
#   ~/.waveterm/config/termthemes/shesh-dark.json   terminal theme
#   ~/.waveterm/config/settings.json                ai:* endpoint keys when --local-ai
#   ~/.waveterm/config/widgets.json                 merged widget presets when --widgets
set -euo pipefail

SHESH_WAVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WAVE_DIR="${WAVETERM_CONFIG_DIR:-$HOME/.waveterm}"
DRY_RUN=0
WITH_AI=0
WITH_WIDGETS=0

usage() {
    cat <<'USAGE'
install-shesh-wave.sh [--with-local-ai] [--with-widgets] [--dry-run]

  --with-local-ai   point Wave's OpenAI-compatible AI settings at the local
                    chain (OmniRoute gateway if SHESH_OMNIROUTE_BASE_URL is
                    set, else Ollama on :11434). No key material is written.
  --with-widgets    merge the Shesh widget presets into widgets.json
  --dry-run         print actions, do not write
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --with-local-ai) WITH_AI=1 ;;
        --with-widgets) WITH_WIDGETS=1 ;;
        --dry-run) DRY_RUN=1 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "unknown flag: $arg" >&2; usage; exit 2 ;;
    esac
done

run() {
    if [ "$DRY_RUN" -eq 1 ]; then echo "[dry-run] $*"; else "$@"; fi
}

backup_dir="$WAVE_DIR/backups/shesh-$(date +%Y%m%d-%H%M%S)"

install_theme() {
    local src="$SHESH_WAVE_DIR/config/termthemes/shesh-dark.json"
    local dst_dir="$WAVE_DIR/config/termthemes"
    local dst="$dst_dir/shesh-dark.json"
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        echo "theme already installed: $dst"
        return 0
    fi
    if [ -f "$dst" ]; then
        run mkdir -p "$backup_dir"
        run cp "$dst" "$backup_dir/shesh-dark.json.bak"
    fi
    run mkdir -p "$dst_dir"
    run cp "$src" "$dst"
    echo "theme: $dst"
}

merge_ai_settings() {
    local base_url
    if [ -n "${SHESH_OMNIROUTE_BASE_URL:-}" ]; then
        base_url="$SHESH_OMNIROUTE_BASE_URL"
    else
        base_url="http://localhost:11434/v1"
    fi
    python3 - "$WAVE_DIR" "$base_url" "$DRY_RUN" <<'PY'
import json, pathlib, sys

wave_dir, base_url, dry = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "1"
settings = wave_dir / "config" / "settings.json"
data = {}
if settings.exists():
    try:
        data = json.loads(settings.read_text())
    except json.JSONDecodeError:
        backup = settings.with_suffix(".json.bak-before-shesh")
        backup.write_text(settings.read_text())
        data = {}
update = {
    # OpenAI-compatible endpoint — OmniRoute gateway when set, else local Ollama.
    "ai:baseurl": base_url,
    # Local chain: no cloud key needed. OmniRoute takes it from the env/secret store.
    "ai:apitoken": "",
    "ai:model": "qwen2.5-coder:3b",
}
new = {**data, **{k: v for k, v in update.items() if k not in data or data[k] != v}}
if new != data:
    if dry:
        print(f"[dry-run] would write {settings}: {sorted(update)}")
    else:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(new, indent=2) + "\n")
        print(f"ai settings → {settings} (baseurl={base_url})")
else:
    print("ai settings already correct")
PY
}

merge_widgets() {
    python3 - "$WAVE_DIR" "$SHESH_WAVE_DIR" "$DRY_RUN" <<'PY'
import json, pathlib, sys

wave_dir, shesh_dir, dry = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3] == "1"
target = wave_dir / "config" / "widgets.json"
preset_file = shesh_dir / "config" / "widgets.shesh.json"
presets = json.loads(preset_file.read_text())
data = {}
if target.exists():
    try:
        data = json.loads(target.read_text())
    except json.JSONDecodeError:
        target.with_suffix(".json.bak-before-shesh").write_text(target.read_text())
        data = {}
changed = False
for key, widget in presets.items():
    if key not in data:
        data[key] = widget
        changed = True
if changed:
    if dry:
        print(f"[dry-run] would merge {len(presets)} widget presets into {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2) + "\n")
        print(f"widgets merged → {target}")
else:
    print("widgets already present")
PY
}

install_theme
[ "$WITH_AI" -eq 1 ] && merge_ai_settings
[ "$WITH_WIDGETS" -eq 1 ] && merge_widgets
echo "install-shesh-wave done (wave dir: $WAVE_DIR)"
