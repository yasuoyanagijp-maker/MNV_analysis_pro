#!/usr/bin/env bash
# Make a PyInstaller .app signable, then ad-hoc sign it (no Hardened Runtime).
#
# codesign treats a real directory under Contents/Frameworks or Contents/MacOS
# whose name contains "." as a nested bundle. delocate's shapely/.dylibs,
# cv2/.dylibs, PIL/.dylibs and *.dist-info hit that rule and fail with:
#   bundle format unrecognized, invalid, or unsuitable
# PyInstaller renames the directory (dot -> __dot__) and leaves a symlink at
# the original name. Mach-O load commands such as @loader_path/.dylibs/...
# keep working through the symlink. A symlink is not signed as a bundle.
#
# Usage:
#   mac_adhoc_codesign.sh prepare /Applications/ARIAKE_OCTA.app
#   mac_adhoc_codesign.sh sign    /Applications/ARIAKE_OCTA.app
#
# Safe to source. The CLI at the bottom runs only when executed.

_mac_adhoc_should_rename() {
  local dir="$1"
  local name
  name="$(basename "$dir")"
  case "$name" in
    *.framework) return 1 ;;
  esac
  case "$dir" in
    *.framework/*) return 1 ;;
  esac
  case "$name" in
    *.*) return 0 ;;
  esac
  return 1
}

_mac_adhoc_dir_nonempty() {
  local dir="$1"
  local listed
  listed="$(ls -A "$dir" 2>/dev/null || true)"
  [[ -n "$listed" ]]
}

# Rename one real dotted directory and put the original name back as a
# relative symlink. If PyInstaller already created __dot__ name, drop the
# real dotted duplicate and point the symlink at the existing directory.
_mac_adhoc_rename_one() {
  local dir="$1"
  local name parent new_name dest
  name="$(basename "$dir")"
  parent="$(dirname "$dir")"
  new_name="${name//./__dot__}"
  dest="${parent}/${new_name}"
  if [[ -L "$dir" ]]; then
    return 0
  fi
  if [[ ! -d "$dir" ]]; then
    return 0
  fi
  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ -L "$dest" || ! -d "$dest" ]]; then
      echo "[mac_adhoc_codesign] ERROR: ${dest} exists and is not a directory" >&2
      return 1
    fi
    if _mac_adhoc_dir_nonempty "$dir" && ! _mac_adhoc_dir_nonempty "$dest"; then
      rm -rf "$dest" || return 1
      mv "$dir" "$dest" || return 1
    else
      rm -rf "$dir" || return 1
    fi
  else
    mv "$dir" "$dest" || return 1
  fi
  ln -s "$new_name" "$dir" || return 1
  echo "[mac_adhoc_codesign] ${dir} -> ${new_name}"
}

prepare_mac_codesign() {
  local app="${1%/}"
  local renamed=0
  local sub root dir name
  if [[ ! -d "$app" ]]; then
    echo "[mac_adhoc_codesign] ERROR: not a directory: ${app}" >&2
    return 1
  fi

  # AppleDouble and Finder metadata break signatures and are not app content.
  while IFS= read -r -d '' dir; do
    rm -rf "$dir"
  done < <(find "$app" \( -name '._*' -o -name '.DS_Store' \) -print0 2>/dev/null || true)

  local -a roots=()
  for sub in Contents/Frameworks Contents/MacOS; do
    root="${app}/${sub}"
    if [[ -d "$root" ]]; then
      roots+=("$root")
    fi
  done

  local -a dirs=()
  local scan
  for scan in "${roots[@]+"${roots[@]}"}"; do
    while IFS= read -r -d '' dir; do
      dirs+=("$dir")
    done < <(find "$scan" -depth -type d -name '*.*' -print0 2>/dev/null || true)
  done

  for dir in "${dirs[@]+"${dirs[@]}"}"; do
    # A parent rename in this same pass may already have moved this path.
    [[ -d "$dir" && ! -L "$dir" ]] || continue
    if _mac_adhoc_should_rename "$dir"; then
      _mac_adhoc_rename_one "$dir" || return 1
      renamed=$((renamed + 1))
    fi
  done

  if [[ "$renamed" -eq 0 ]]; then
    echo "[mac_adhoc_codesign] no dotted Frameworks/MacOS directories to rename"
  elif [[ "$renamed" -eq 1 ]]; then
    echo "[mac_adhoc_codesign] renamed 1 dotted directory"
  else
    echo "[mac_adhoc_codesign] renamed ${renamed} dotted directories"
  fi
}

_mac_adhoc_is_macho() {
  local mag
  mag="$(od -An -t x1 -N 4 "$1" 2>/dev/null | tr -d ' \n' || true)"
  case "$mag" in
    cafebabe|bebafeca|feedface|cefaedfe|feedfacf|cffaedfe) return 0 ;;
  esac
  return 1
}

_mac_adhoc_sign_macho_inside_out() {
  local app="$1"
  local f
  while IFS= read -r -d '' f; do
    if _mac_adhoc_is_macho "$f"; then
      chmod u+w "$f" 2>/dev/null || true
      codesign --force --sign - "$f" || true
    fi
  done < <(find "$app" -depth -type f -print0)
}

sign_mac_adhoc() {
  local app="${1%/}"
  prepare_mac_codesign "$app" || return 1
  if [[ "$(uname)" != "Darwin" ]]; then
    echo "[mac_adhoc_codesign] codesign skipped (not macOS)"
    return 0
  fi
  if ! command -v codesign >/dev/null 2>&1; then
    echo "[mac_adhoc_codesign] ERROR: codesign not found" >&2
    return 1
  fi
  if command -v xattr >/dev/null 2>&1; then
    xattr -cr "$app" || return 1
  fi
  if codesign --force --deep --sign - "$app"; then
    codesign --verify --deep --strict "$app"
    return $?
  fi
  echo "[mac_adhoc_codesign] codesign --deep failed; signing Mach-O files, then the app without --deep" >&2
  _mac_adhoc_sign_macho_inside_out "$app"
  codesign --force --sign - "$app" || return 1
  codesign --verify --strict "$app"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  cmd="${1:-}"
  target="${2:-}"
  case "$cmd" in
    prepare)
      [[ -n "$target" ]] || { echo "usage: $0 prepare APP" >&2; exit 1; }
      prepare_mac_codesign "$target"
      ;;
    sign)
      [[ -n "$target" ]] || { echo "usage: $0 sign APP" >&2; exit 1; }
      sign_mac_adhoc "$target"
      ;;
    *)
      echo "usage: $0 prepare|sign APP" >&2
      exit 1
      ;;
  esac
fi
