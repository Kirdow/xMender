#!/usr/bin/env bash
# Regenerate the PWA / home-screen PNG icons from xmender/web/static/icon.svg.
# Needs rsvg-convert (librsvg). Run after changing icon.svg.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=xmender/web/static/icons
BG="#111111"
mkdir -p "$OUT"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Inner markup of icon.svg (32x32 viewBox), minus the outer <svg> tag.
inner=$(sed -e 's/^<svg[^>]*>//' -e 's#</svg>\s*$##' xmender/web/static/icon.svg)

# $1 = output file, $2 = size px, $3 = icon share of the canvas (0..1).
render() {
  local scale offset
  scale=$(awk -v s="$3" 'BEGIN { printf "%.4f", s * 100 / 32 }')
  offset=$(awk -v s="$3" 'BEGIN { printf "%.4f", (100 - s * 100) / 2 }')
  cat > "$tmp/i.svg" <<EOF
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="$BG"/><g transform="translate($offset $offset) scale($scale)">$inner</g></svg>
EOF
  rsvg-convert -w "$2" -h "$2" -o "$OUT/$1" "$tmp/i.svg"
}

render icon-192.png 192 0.8
render icon-512.png 512 0.8
# Maskable: keep the artwork inside the 80% safe-zone circle.
render icon-maskable-512.png 512 0.6
# iOS rounds the corners itself and needs an opaque image.
render apple-touch-icon.png 180 0.72
render favicon-32.png 32 1.0
