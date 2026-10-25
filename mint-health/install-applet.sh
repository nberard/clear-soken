#!/bin/bash
# Installe l'applet Cinnamon pour l'utilisateur courant.
set -euo pipefail
UUID="google-health@mint-health"
SRC="$(cd "$(dirname "$0")" && pwd)/applet/$UUID"
DEST="$HOME/.local/share/cinnamon/applets/$UUID"

missing=()
command -v curl >/dev/null || missing+=(curl)
python3 -c 'import gi; gi.require_version("WebKit2","4.1")' 2>/dev/null \
  || python3 -c 'import gi; gi.require_version("WebKit2","4.0")' 2>/dev/null \
  || missing+=(gir1.2-webkit2-4.1)
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installation des dépendances : ${missing[*]}"
  sudo apt-get install -y "${missing[@]}" python3-gi
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -r "$SRC" "$DEST"
chmod +x "$DEST/dock.py"
echo "Applet installé dans $DEST"
echo "Ajoute-le : clic droit sur la barre des tâches → Applets → « Google Health » → +"
echo "(Si l'applet était déjà actif : Alt+F2, tape r, Entrée pour recharger Cinnamon.)"
