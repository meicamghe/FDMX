#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$ROOT/dist}"
SIZES=(16 32 48 128)

command -v rsvg-convert >/dev/null 2>&1 || {
  echo "Missing rsvg-convert. Install librsvg2-bin." >&2
  exit 1
}
command -v zip >/dev/null 2>&1 || {
  echo "Missing zip. Install the zip package." >&2
  exit 1
}
command -v node >/dev/null 2>&1 || {
  echo "Missing Node.js. Install Node.js 18 or newer." >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "Missing Python 3." >&2
  exit 1
}

for browser in chrome firefox; do
  EXT="$ROOT/$browser"
  test -f "$EXT/manifest.json"
  test -f "$EXT/icons/gns-downloader.svg"

  # PNG icons are reproducible build outputs. The SVG is the editable source.
  for size in "${SIZES[@]}"; do
    rsvg-convert -w "$size" -h "$size" \
      "$EXT/icons/gns-downloader.svg" \
      -o "$EXT/icons/gns-downloader-$size.png"
  done

  python3 - "$EXT/manifest.json" "$browser" <<'PY'
import json, pathlib, sys
manifest_path = pathlib.Path(sys.argv[1])
browser = sys.argv[2]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest.get("name") == "GNS Downloader", "Unexpected extension name"
assert manifest.get("version") == "1.3.0", "Unexpected extension version"
for size in (16, 32, 48, 128):
    icon = manifest_path.parent / "icons" / f"gns-downloader-{size}.png"
    assert icon.is_file(), f"Missing generated icon: {icon}"
if browser == "firefox":
    assert manifest["browser_specific_settings"]["gecko"]["id"] == "fdmx-browser@gns.local"
PY

  # Syntax-check the original, readable JavaScript files; no transpilation or bundling.
  for source in github-auth.js background.js popup.js media-detect.js; do
    node --check "$EXT/$source"
  done
done

mkdir -p "$OUT"
rm -f "$OUT/GNS-Downloader-Chrome-1.3.0.zip" "$OUT/GNS-Downloader-Firefox-1.3.0.xpi"
(
  cd "$ROOT/chrome"
  zip -X -r "$OUT/GNS-Downloader-Chrome-1.3.0.zip" .
)
(
  cd "$ROOT/firefox"
  zip -X -r "$OUT/GNS-Downloader-Firefox-1.3.0.xpi" .
)

echo "Build complete:"
ls -lh "$OUT/GNS-Downloader-Chrome-1.3.0.zip" "$OUT/GNS-Downloader-Firefox-1.3.0.xpi"
