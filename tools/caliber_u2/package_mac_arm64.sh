#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_BIN="$ROOT/dist/caliber_u2_tool/compute_caliber_u2_from_csv"
OUT_DIR="$ROOT/dist/release_caliber_csv_tool"
STAGE="$OUT_DIR/stage_mac_arm64"
ZIP_NAME="ARIAKE_caliber_uniformity_csv_tool_mac_arm64.zip"

mkdir -p "$OUT_DIR"
rm -rf "$STAGE"
mkdir -p "$STAGE"

if [[ ! -x "$DIST_BIN" ]]; then
  echo "Missing Mac binary: $DIST_BIN" >&2
  echo "Build first with tools/caliber_u2/build_standalone.sh" >&2
  exit 1
fi

cp -f "$DIST_BIN" "$STAGE/compute_caliber_u2_from_csv"
chmod +x "$STAGE/compute_caliber_u2_from_csv"
cp -f "$ROOT/tools/caliber_u2/README_USER_JA.md" "$STAGE/README.md"
# Optional loose copy of ref (frozen already embeds it)
mkdir -p "$STAGE/resources/reference_metrics"
cp -f "$ROOT/resources/reference_metrics/caliber_u2_device_ref.json" \
  "$STAGE/resources/reference_metrics/"

(
  cd "$STAGE"
  # Avoid AppleDouble clutter
  export COPYFILE_DISABLE=1
  rm -f "$OUT_DIR/$ZIP_NAME"
  zip -r "$OUT_DIR/$ZIP_NAME" .
)
echo "Wrote $OUT_DIR/$ZIP_NAME"
unzip -l "$OUT_DIR/$ZIP_NAME"
