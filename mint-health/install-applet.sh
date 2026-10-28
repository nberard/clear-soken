#!/bin/bash
# Installe les applets Cinnamon pour l'utilisateur courant.
#   ./install-applet.sh                 → les deux applets
#   ./install-applet.sh google-health   → seulement « Google Health »
#   ./install-applet.sh journal-vocal   → seulement « Journal vocal »
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)/applet"
WANT="${1:-all}"

install_one() {
  local uuid="$1" src="$ROOT/$1" dest="$HOME/.local/share/cinnamon/applets/$1"
  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -r "$src" "$dest"
  [ -f "$dest/dock.py" ] && chmod +x "$dest/dock.py"
  echo "Applet installé : $dest"
}

missing=()
command -v curl >/dev/null || missing+=(curl)
if [[ "$WANT" == all || "$WANT" == google-health ]]; then
  python3 -c 'import gi; gi.require_version("WebKit2","4.1")' 2>/dev/null \
    || python3 -c 'import gi; gi.require_version("WebKit2","4.0")' 2>/dev/null \
    || missing+=(gir1.2-webkit2-4.1 python3-gi)
fi
if [[ "$WANT" == all || "$WANT" == journal-vocal ]]; then
  command -v gst-launch-1.0 >/dev/null || missing+=(gstreamer1.0-tools)
  gst-inspect-1.0 opusenc >/dev/null 2>&1 || missing+=(gstreamer1.0-plugins-base)
  gst-inspect-1.0 pulsesrc >/dev/null 2>&1 || missing+=(gstreamer1.0-pulseaudio)
fi
if [ ${#missing[@]} -gt 0 ]; then
  echo "Installation des dépendances : ${missing[*]}"
  sudo apt-get install -y "${missing[@]}"
fi

case "$WANT" in
  all) install_one "google-health@mint-health"; install_one "journal-vocal@mint-health" ;;
  google-health) install_one "google-health@mint-health" ;;
  journal-vocal) install_one "journal-vocal@mint-health" ;;
  *) echo "Applet inconnu : $WANT (google-health ou journal-vocal)"; exit 1 ;;
esac

echo "Ajoute-les : clic droit sur la barre des tâches → Applets → « Google Health » / « Journal vocal » → +"
echo "(Si un applet était déjà actif : Alt+F2, tape r, Entrée pour recharger Cinnamon.)"
