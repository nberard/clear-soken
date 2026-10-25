#!/usr/bin/env python3
"""Fenêtre sans bordure, translucide, ancrée au-dessus (ou sous) le panneau Cinnamon,
qui affiche le dashboard Grafana en mode kiosque.

Dépendances (Linux Mint 22) : sudo apt install python3-gi gir1.2-webkit2-4.1
"""
import argparse
import signal

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
try:
    gi.require_version("WebKit2", "4.1")
except ValueError:
    gi.require_version("WebKit2", "4.0")
from gi.repository import Gdk, GLib, Gtk, WebKit2  # noqa: E402

# Rend transparents les fonds de page Grafana (les panneaux sont déjà « transparent »
# dans le dashboard) pour laisser voir le fond translucide de la fenêtre.
GRAFANA_CSS = """
html, body, #reactRoot, .main-view, .page-wrapper, .scrollbar-view,
[class*="page-wrapper"], [class*="page-panes"], [class*="canvas-content"],
[class*="body-wrapper"], [class*="dashboard-content"], [class*="page-container"],
[class*="react-grid-layout"] {
    background: transparent !important;
    background-color: transparent !important;
}
::-webkit-scrollbar { width: 6px; background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,.25); border-radius: 3px; }
"""

MARGIN = 8


class Dock(Gtk.Window):
    def __init__(self, args):
        super().__init__(type=Gtk.WindowType.TOPLEVEL, title="Google Health")
        self.args = args
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.stick()  # visible sur tous les espaces de travail
        self.set_default_size(args.width, args.height)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.connect("draw", self._draw_background)

        manager = WebKit2.UserContentManager()
        manager.add_style_sheet(
            WebKit2.UserStyleSheet(
                GRAFANA_CSS,
                WebKit2.UserContentInjectedFrames.ALL_FRAMES,
                WebKit2.UserStyleLevel.USER,
                None,
                None,
            )
        )
        self.web = WebKit2.WebView.new_with_user_content_manager(manager)
        transparent = Gdk.RGBA()
        transparent.parse("rgba(0,0,0,0)")
        self.web.set_background_color(transparent)
        self.web.load_uri(args.url)
        # Liens externes -> navigateur par défaut
        self.web.connect("decide-policy", self._on_policy)
        self.add(self.web)

        self.connect("key-press-event", self._on_key)
        if args.autoclose:
            self.connect("focus-out-event", lambda *_: (Gtk.main_quit(), False)[1])
        self.connect("destroy", Gtk.main_quit)
        self.connect("realize", lambda *_: self._place())

    def _place(self):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        _, px, py = seat.get_pointer().get_position()
        monitor = display.get_monitor_at_point(px, py) or display.get_primary_monitor()
        wa = monitor.get_workarea()  # zone sans le panneau
        w = min(self.args.width, wa.width - 2 * MARGIN)
        h = min(self.args.height, wa.height - 2 * MARGIN)
        x = wa.x + wa.width - w - MARGIN
        y = wa.y + MARGIN if self.args.anchor == "top" else wa.y + wa.height - h - MARGIN
        self.resize(w, h)
        self.move(x, y)

    def _draw_background(self, _widget, cr):
        cr.set_source_rgba(0.07, 0.08, 0.10, self.args.opacity)
        cr.set_operator(1)  # cairo.OPERATOR_SOURCE
        cr.paint()
        cr.set_operator(2)  # cairo.OPERATOR_OVER
        return False

    def _on_key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
        elif event.keyval == Gdk.KEY_F5:
            self.web.reload()
        return False

    def _on_policy(self, _web, decision, kind):
        if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            Gtk.show_uri_on_window(self, uri, Gdk.CURRENT_TIME)
            decision.ignore()
            return True
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--anchor", choices=["top", "bottom"], default="bottom")
    p.add_argument("--width", type=int, default=900)
    p.add_argument("--height", type=int, default=620)
    p.add_argument("--opacity", type=float, default=0.82)
    p.add_argument("--autoclose", action="store_true")
    args = p.parse_args()

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, Gtk.main_quit)
    win = Dock(args)
    win.show_all()
    win.present()
    Gtk.main()


if __name__ == "__main__":
    main()
