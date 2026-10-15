#!/usr/bin/env bash
# Build "Cozy Roads.app" on a Mac. Usage: ./build_mac.sh
# Result: dist/Cozy Roads.app  (drag it into /Applications)
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

# App icon (.icns) made from a generated PNG
mkdir -p build/icon.iconset
python tools/make_icon.py build/icon.png
for s in 16 32 128 256 512; do
  sips -z $s $s build/icon.png --out "build/icon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) build/icon.png --out "build/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns build/icon.iconset -o build/CozyRoads.icns

pyinstaller --noconfirm --clean --windowed \
  --name "Cozy Roads" \
  --icon build/CozyRoads.icns \
  --osx-bundle-identifier com.cozyroads.game \
  run_game.py

echo
echo "Done! Your app is at: dist/Cozy Roads.app"
echo "First launch: right-click the app -> Open (it isn't notarized by Apple)."
