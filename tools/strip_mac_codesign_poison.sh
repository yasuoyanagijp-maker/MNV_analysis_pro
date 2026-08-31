#!/usr/bin/env bash
# Remove *.dist-info / *.egg-info (and AppleDouble) that break codesign --deep.
set -euo pipefail

APP_PATH="${1:?Usage: strip_mac_codesign_poison.sh ARIAKE_OCTA.app}"

if [[ ! -d "$APP_PATH" ]]; then
    echo "[strip_mac_codesign_poison] ERROR: not a directory: ${APP_PATH}" >&2
    exit 1
fi

removed=0
for sub in Contents/Frameworks Contents/Resources; do
    root="${APP_PATH}/${sub}"
    [[ -d "$root" ]] || continue
    while IFS= read -r -d '' path; do
        rm -rf "$path"
        removed=$((removed + 1))
        echo "[strip_mac_codesign_poison] removed ${path#${APP_PATH}/}"
    done < <(find "$root" -maxdepth 1 \( -name '*.dist-info' -o -name '*.egg-info' -o -name '._*.dist-info' -o -name '._*.egg-info' \) -print0 2>/dev/null)
done

while IFS= read -r -d '' link; do
    rm -f "$link"
    removed=$((removed + 1))
    echo "[strip_mac_codesign_poison] removed symlink ${link#${APP_PATH}/}"
done < <(find "${APP_PATH}/Contents/Frameworks" -maxdepth 1 -type l \( -name '*.dist-info' -o -name '*.egg-info' \) -print0 2>/dev/null)

while IFS= read -r -d '' dot; do
    rm -f "$dot"
    removed=$((removed + 1))
done < <(find "$APP_PATH" -name '._*' -print0 2>/dev/null)

if command -v dot_clean >/dev/null 2>&1; then
    dot_clean -m "$APP_PATH" 2>/dev/null || true
fi

left="$(find "$APP_PATH/Contents/Frameworks" "$APP_PATH/Contents/Resources" -maxdepth 1 \( -name '*.dist-info' -o -name '*.egg-info' \) 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$left" != "0" ]]; then
    echo "[strip_mac_codesign_poison] ERROR: ${left} metadata dir(s) still under Frameworks/Resources" >&2
    find "$APP_PATH/Contents/Frameworks" "$APP_PATH/Contents/Resources" -maxdepth 1 \( -name '*.dist-info' -o -name '*.egg-info' \) 2>/dev/null >&2
    exit 1
fi

echo "[strip_mac_codesign_poison] OK (${removed} paths cleaned, 0 metadata dirs left)"
