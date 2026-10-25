/*
 * Applet Cinnamon « Google Health »
 * - affiche le nombre de pas (ou le sommeil) dans la barre des tâches
 * - menu : résumé du jour + mini-graphique Grafana (rendu PNG)
 * - ouvre le dashboard Grafana complet dans une fenêtre transparente ancrée au panneau
 */
const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const Mainloop = imports.mainloop;
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;

const CACHE_DIR = GLib.build_filenamev([GLib.get_user_cache_dir(), "google-health-applet"]);

function fmtInt(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function fmtMinutes(min) {
    if (min === null || min === undefined) return "—";
    const h = Math.floor(min / 60);
    const m = Math.round(min % 60);
    return `${h} h ${m.toString().padStart(2, "0")}`;
}

function firstMetric(today, prefix) {
    for (const key in today) {
        if (key.indexOf(prefix + ".") === 0) return today[key];
    }
    return null;
}

class GoogleHealthApplet extends Applet.TextIconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this.metadata = metadata;
        this.orientation = orientation;
        this._dock = null;
        this._timer = 0;
        this._chartFile = null;
        this._status = null;

        GLib.mkdir_with_parents(CACHE_DIR, 0o700);

        this.settings = new Settings.AppletSettings(this, metadata.uuid, instanceId);
        const keys = [
            ["api-url", "apiUrl"], ["grafana-url", "grafanaUrl"], ["dashboard-uid", "dashboardUid"],
            ["panel-metric", "panelMetric"], ["mini-panel-id", "miniPanelId"], ["mini-range", "miniRange"],
            ["refresh-min", "refreshMin"], ["dock-width", "dockWidth"], ["dock-height", "dockHeight"],
            ["dock-opacity", "dockOpacity"], ["dock-autoclose", "dockAutoclose"],
        ];
        for (const [key, prop] of keys) {
            this.settings.bind(key, prop, () => this._onSettingsChanged());
        }

        this.set_applet_icon_symbolic_name("emblem-favorite-symbolic");
        this.set_applet_tooltip("Google Health");
        this.set_applet_label("");

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);
        this._buildMenu();
        this.menu.connect("open-state-changed", (m, open) => {
            if (open) {
                this._refreshStatus();
                this._refreshChart();
            }
        });

        this._refreshStatus();
        this._schedule();
    }

    /* ---------- menu ---------- */

    _buildMenu() {
        this._stateItem = new PopupMenu.PopupMenuItem("Chargement…", { reactive: false });
        this.menu.addMenuItem(this._stateItem);

        this._stepsItem = new PopupMenu.PopupMenuItem("Pas : —", { reactive: false });
        this._sleepItem = new PopupMenu.PopupMenuItem("Sommeil : —", { reactive: false });
        this._heartItem = new PopupMenu.PopupMenuItem("FC au repos : —", { reactive: false });
        this.menu.addMenuItem(this._stepsItem);
        this.menu.addMenuItem(this._sleepItem);
        this.menu.addMenuItem(this._heartItem);

        // Mini-graphique Grafana rendu en PNG
        this._chartItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        this._chartBin = new St.Bin({
            style: "width: 400px; height: 180px; border-radius: 8px;",
        });
        this._chartItem.addActor(this._chartBin, { expand: true });
        this.menu.addMenuItem(this._chartItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._dockItem = this.menu.addAction("Tableau de bord (fenêtre transparente)", () => this._toggleDock());
        this.menu.addAction("Ouvrir Grafana dans le navigateur", () =>
            this._openUri(`${this.grafanaUrl}/d/${this.dashboardUid}/`));
        this.menu.addAction("Synchroniser maintenant", () => this._post("/sync", () => {
            Mainloop.timeout_add_seconds(5, () => { this._refreshStatus(); this._refreshChart(); return false; });
        }));

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._connectItem = this.menu.addAction("Connecter mon compte Google Health…", () => this._toggleConnection());
    }

    _toggleConnection() {
        if (this._status && this._status.connected) {
            this._post("/auth/logout", () => this._refreshStatus());
        } else {
            this._openUri(`${this.apiUrl}/auth/start`);
        }
    }

    /* ---------- données ---------- */

    _refreshStatus() {
        this._curl(["-f", `${this.apiUrl}/status`], (ok, out) => {
            if (!ok) {
                this._status = null;
                this._stateItem.label.set_text("⚠ Service de synchro injoignable (docker compose up -d ?)");
                this.set_applet_label(this.panelMetric === "none" ? "" : "!");
                this._connectItem.label.set_text("Connecter mon compte Google Health…");
                return;
            }
            let s;
            try { s = JSON.parse(out); } catch (e) { return; }
            this._status = s;
            const today = s.today || {};
            const steps = today["steps.countSum"];
            const resting = firstMetric(today, "daily-resting-heart-rate");

            if (!s.connected) {
                this._stateItem.label.set_text("Compte Google non connecté");
            } else if (s.last_sync) {
                const t = GLib.DateTime.new_from_iso8601(s.last_sync, null);
                const when = t ? t.to_local().format("%H:%M") : "?";
                this._stateItem.label.set_text(`${s.last_sync_ok ? "✓" : "⚠"} Synchro à ${when}`);
            } else {
                this._stateItem.label.set_text("Première synchro en cours…");
            }
            this._connectItem.label.set_text(s.connected ? "Déconnecter le compte Google" : "Connecter mon compte Google Health…");
            this._stepsItem.label.set_text(`Pas aujourd'hui : ${fmtInt(steps)}`);
            this._sleepItem.label.set_text(`Sommeil (dernière nuit) : ${fmtMinutes(s.last_sleep_minutes)}`);
            this._heartItem.label.set_text(`FC au repos : ${resting === null ? "—" : Math.round(resting) + " bpm"}`);

            if (this.panelMetric === "steps") this.set_applet_label(steps !== undefined ? fmtInt(steps) : "—");
            else if (this.panelMetric === "sleep") this.set_applet_label(fmtMinutes(s.last_sleep_minutes));
            else this.set_applet_label("");
            this.set_applet_tooltip(`Google Health — ${fmtInt(steps)} pas aujourd'hui`);
        });
    }

    _refreshChart() {
        // Nom unique à chaque rendu pour contourner le cache de textures de St
        const file = GLib.build_filenamev([CACHE_DIR, `chart-${Date.now()}.png`]);
        const url = `${this.grafanaUrl}/render/d-solo/${this.dashboardUid}/_?orgId=1` +
            `&panelId=${this.miniPanelId}&width=800&height=360&scale=1` +
            `&from=${encodeURIComponent(this.miniRange)}&to=now&theme=dark` +
            `&tz=${encodeURIComponent(GLib.TimeZone.new_local().get_identifier() || "Europe/Paris")}`;
        this._curl(["-f", "--max-time", "30", "-o", file, url], (ok) => {
            if (!ok) {
                this._chartBin.set_style("width: 400px; height: 40px;");
                this._chartBin.set_child(new St.Label({ text: "Graphique indisponible (Grafana / renderer)" }));
                return;
            }
            const old = this._chartFile;
            this._chartFile = file;
            this._chartBin.set_child(null);
            this._chartBin.set_style(
                `width: 400px; height: 180px; border-radius: 8px;` +
                `background-image: url("file://${file}"); background-size: contain;`);
            if (old) GLib.unlink(old);
        });
    }

    /* ---------- fenêtre dashboard ---------- */

    _toggleDock() {
        if (this._dock) {
            this._dock.force_exit();
            this._dock = null;
            return;
        }
        this.menu.close();
        const script = GLib.build_filenamev([this.metadata.path, "dock.py"]);
        const url = `${this.grafanaUrl}/d/${this.dashboardUid}/?orgId=1&kiosk&theme=dark`;
        const anchor = this.orientation === St.Side.TOP ? "top" : "bottom";
        const argv = ["python3", script, "--url", url, "--anchor", anchor,
            "--width", String(this.dockWidth), "--height", String(this.dockHeight),
            "--opacity", String(this.dockOpacity)];
        if (this.dockAutoclose) argv.push("--autoclose");
        try {
            const proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
            this._dock = proc;
            proc.wait_async(null, () => { if (this._dock === proc) this._dock = null; });
        } catch (e) {
            global.logError(`google-health: impossible de lancer dock.py : ${e}`);
        }
    }

    /* ---------- utilitaires ---------- */

    _curl(args, cb) {
        try {
            const proc = Gio.Subprocess.new(
                ["curl", "-s", "--max-time", "10"].concat(args),
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
            proc.communicate_utf8_async(null, null, (p, res) => {
                let out = "", ok = false;
                try {
                    [, out] = p.communicate_utf8_finish(res);
                    ok = p.get_successful();
                } catch (e) { ok = false; }
                cb(ok, out || "");
            });
        } catch (e) {
            cb(false, "");
        }
    }

    _post(path, cb) {
        this._curl(["-f", "-X", "POST", `${this.apiUrl}${path}`], () => { if (cb) cb(); });
    }

    _openUri(uri) {
        try { Gio.AppInfo.launch_default_for_uri(uri, null); }
        catch (e) { global.logError(`google-health: ${e}`); }
    }

    _schedule() {
        if (this._timer) Mainloop.source_remove(this._timer);
        this._timer = Mainloop.timeout_add_seconds(Math.max(1, this.refreshMin) * 60, () => {
            this._refreshStatus();
            return true;
        });
    }

    _onSettingsChanged() {
        this._schedule();
        this._refreshStatus();
    }

    on_applet_clicked() {
        this.menu.toggle();
    }

    on_applet_removed_from_panel() {
        if (this._timer) Mainloop.source_remove(this._timer);
        this._timer = 0;
        if (this._dock) this._dock.force_exit();
        if (this._chartFile) GLib.unlink(this._chartFile);
        this.settings.finalize();
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new GoogleHealthApplet(metadata, orientation, panelHeight, instanceId);
}
