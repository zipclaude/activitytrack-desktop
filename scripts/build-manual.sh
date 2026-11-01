#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds the user manual, it and en, as PDF (as the app's and the web's):
#
#   scripts/build-manual.sh [version]      -> build/manual/*.pdf
#
# Needs pandoc and a Chromium (Debian packages; no npm). The screenshots
# come from scripts/screenshots.py.

set -eu
cd "$(dirname "$0")/.."

VERSION=${1:-$(sed -n 's/^Versione \([^ ]*\) .*/\1/p' docs/manual/it/desktop.md | head -n 1)}
OUT=build/manual
CHROME=$(command -v chromium || command -v chromium-headless-shell || command -v google-chrome || true)
[ -n "$CHROME" ] || { echo "no Chromium for the PDF" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"
{ echo "<style>"; cat docs/manual/style.css; echo "</style>"; } > "$OUT/style.html"
cp -r docs/manual/img "$OUT/img"
for lang in it en; do
	case $lang in
		it) title="ActivityTrack Desktop — Manuale"; name=Manuale ;;
		en) title="ActivityTrack Desktop — Manual"; name=Manual ;;
	esac
	mkdir -p "$OUT/$lang"
	pandoc -f gfm+implicit_figures docs/manual/$lang/desktop.md -s --toc --toc-depth=2 -H "$OUT/style.html" \
		--metadata title="$title" --metadata subtitle="$VERSION" --metadata lang="$lang" \
		-o "$OUT/$lang/desktop.html"
	"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
		--print-to-pdf="$OUT/ActivityTrack-Desktop-$name-$VERSION.pdf" "file://$PWD/$OUT/$lang/desktop.html" 2>/dev/null
	echo "$OUT/ActivityTrack-Desktop-$name-$VERSION.pdf"
done
