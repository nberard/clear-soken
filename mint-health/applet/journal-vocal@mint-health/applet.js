/*
 * Applet Cinnamon « Journal vocal »
 * - clic gauche (ou Super+Alt+R) : démarrer / arrêter un mémo vocal
 * - pendant l'enregistrement : point rouge et minuteur dans la barre des tâches
 * - chaque mémo est gardé dans un dossier local (Musique/Journal vocal) puis envoyé au
 *   journal vocal de mint-health (Grafana, page téléphone). En cas d'échec, il est renvoyé plus tard.
 * - clic droit : derniers mémos, dossier, journal complet
 *
 * Enregistrement : GStreamer (pulsesrc → Opus/Ogg), présent par défaut sur Linux Mint.
 */
const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const Main = imports.ui.main;
const Mainloop = imports.mainloop;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;

const UUID = "journal-vocal@mint-health";
const CACHE_DIR = GLib.build_filenamev([GLib.get_user_cache_dir(), "journal-vocal-applet"]);
const PENDING_FILE = GLib.build_filenamev([CACHE_DIR, "a-envoyer.json"]);
const REC_COLOR = "#e0685a";

function fmt(sec) {
    const s = Math.max(0, Math.round(sec));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function readText(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? new TextDecoder().decode(bytes) : null;
    } catch (e) {
        return null;
    }
}

class JournalVocalApplet extends Applet.TextIconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this.metadata = metadata;
        this._hotkeyId = `${UUID}-${instanceId}`;
        this._proc = null;
        this._file = null;
        this._startedAt = 0;
        this._startIso = "";
        this._ticker = 0;
        this._stopping = false;

        GLib.mkdir_with_parents(CACHE_DIR, 0o700);

        this.settings = new Settings.AppletSettings(this, metadata.uuid, instanceId);
        for (const [key, prop] of [["save-dir", "saveDir"], ["max-min", "maxMin"], ["upload", "upload"],
            ["api-url", "apiUrl"], ["auth-user", "authUser"], ["auth-password", "authPassword"]]) {
            this.settings.bind(key, prop, () => this._writeCurlAuth());
        }
        this.settings.bind("hotkey", "hotkey", () => this._bindHotkey());
        this._writeCurlAuth();
        this._bindHotkey();

        this._idle();
        this._buildContextMenu();

        // Renvoie les mémos restés en attente (serveur injoignable, PC hors ligne…)
        this._retryTimer = Mainloop.timeout_add_seconds(600, () => { this._flushPending(); return true; });
        Mainloop.timeout_add_seconds(20, () => { this._flushPending(); return false; });
    }

    /* ---------- affichage ---------- */

    _idle() {
        this.set_applet_icon_symbolic_name("audio-input-microphone-symbolic");
        if (this._applet_icon) this._applet_icon.set_style("");
        if (this._applet_label) this._applet_label.set_style("");
        this.set_applet_label("");
        this.set_applet_tooltip("Journal vocal — clic pour enregistrer (" + this._hotkeyLabel() + ")");
    }

    _recordingUi() {
        this.set_applet_icon_symbolic_name("media-record-symbolic");
        if (this._applet_icon) this._applet_icon.set_style(`color: ${REC_COLOR};`);
        if (this._applet_label) this._applet_label.set_style(`color: ${REC_COLOR}; font-weight: bold;`);
        this.set_applet_tooltip("Enregistrement… clic pour arrêter");
        this._tick();
    }

    _tick() {
        const sec = (Date.now() - this._startedAt) / 1000;
        this.set_applet_label(fmt(sec));
        if (sec >= this.maxMin * 60) this._stop();
    }

    _hotkeyLabel() {
        return (this.hotkey || "").split("::")[0].replace(/</g, "").replace(/>/g, "+") || "pas de raccourci";
    }

    _buildContextMenu() {
        this._recentMenu = new PopupMenu.PopupSubMenuMenuItem("Derniers mémos");
        this._applet_context_menu.addMenuItem(this._recentMenu, 0);
        this._applet_context_menu.addAction("Ouvrir le dossier des mémos", () => this._openUri(Gio.File.new_for_path(this._dir()).get_uri()));
        this._journalItem = this._applet_context_menu.addAction("Journal complet (téléphone compris)…", () => this._openUri(`${this.apiUrl}/memos/app`));
        this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._applet_context_menu.connect("open-state-changed", (m, open) => { if (open) this._fillRecent(); });
    }

    _fillRecent() {
        this._recentMenu.menu.removeAll();
        this._journalItem.actor.visible = this.upload;
        const files = [];
        try {
            const en = Gio.File.new_for_path(this._dir()).enumerate_children("standard::name,time::modified", Gio.FileQueryInfoFlags.NONE, null);
            let info;
            while ((info = en.next_file(null))) {
                const name = info.get_name();
                if (/\.(ogg|opus|webm|m4a|wav)$/i.test(name)) files.push([name, info.get_attribute_uint64("time::modified")]);
            }
            en.close(null);
        } catch (e) { /* dossier pas encore créé */ }
        files.sort((a, b) => b[1] - a[1]);
        const pending = this._readPending().map((p) => GLib.path_get_basename(p.file));
        if (!files.length) {
            this._recentMenu.menu.addMenuItem(new PopupMenu.PopupMenuItem("Aucun mémo pour l'instant", { reactive: false }));
            return;
        }
        for (const [name] of files.slice(0, 8)) {
            const label = name.replace(/\.[^.]+$/, "") + (pending.includes(name) ? "  ⏳" : "");
            this._recentMenu.menu.addAction("▶  " + label, () => this._openUri(Gio.File.new_for_path(GLib.build_filenamev([this._dir(), name])).get_uri()));
        }
    }

    /* ---------- enregistrement ---------- */

    on_applet_clicked() {
        if (this._proc) this._stop();
        else this._start();
    }

    _dir() {
        if (this.saveDir) {
            const p = this.saveDir.startsWith("file://") ? Gio.File.new_for_uri(this.saveDir).get_path() : this.saveDir;
            if (p) return p;
        }
        const music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) || GLib.get_home_dir();
        return GLib.build_filenamev([music, "Journal vocal"]);
    }

    _start() {
        if (!GLib.find_program_in_path("gst-launch-1.0")) {
            this._notify("Journal vocal", "GStreamer manquant : sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-pulseaudio");
            return;
        }
        const dir = this._dir();
        GLib.mkdir_with_parents(dir, 0o755);
        const now = GLib.DateTime.new_now_local();
        this._startIso = now.format("%Y-%m-%dT%H:%M:%S%:z"); // ex. 2026-10-27T10:21:36+01:00
        this._file = GLib.build_filenamev([dir, now.format("%Y-%m-%d %H-%M-%S") + ".ogg"]);
        const argv = ["gst-launch-1.0", "-q", "-e",
            "pulsesrc", "!", "audioconvert", "!", "audioresample", "!",
            "opusenc", "bitrate=48000", "!", "oggmux", "!", "filesink", `location=${this._file}`];
        try {
            this._proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (e) {
            this._notify("Journal vocal", `Impossible de démarrer l'enregistrement : ${e}`);
            this._proc = null;
            return;
        }
        this._stopping = false;
        this._startedAt = Date.now();
        const proc = this._proc;
        proc.wait_async(null, () => this._onProcessEnd(proc));
        this._recordingUi();
        this._ticker = Mainloop.timeout_add(500, () => { this._tick(); return true; });
    }

    _stop() {
        if (!this._proc || this._stopping) return;
        this._stopping = true;
        this._stopTicker();
        this.set_applet_tooltip("Finalisation du mémo…");
        // SIGINT + option -e : GStreamer termine proprement le fichier Ogg
        this._proc.send_signal(2);
        const proc = this._proc;
        Mainloop.timeout_add_seconds(5, () => { if (this._proc === proc) proc.force_exit(); return false; });
    }

    _stopTicker() {
        if (this._ticker) Mainloop.source_remove(this._ticker);
        this._ticker = 0;
    }

    _onProcessEnd(proc) {
        if (proc !== this._proc) return;
        const expected = this._stopping;
        const duration = (Date.now() - this._startedAt) / 1000;
        const file = this._file;
        this._proc = null;
        this._stopTicker();
        this._idle();

        const f = Gio.File.new_for_path(file);
        const size = f.query_exists(null) ? f.query_info("standard::size", Gio.FileQueryInfoFlags.NONE, null).get_size() : 0;
        if (!expected) {
            this._notify("Journal vocal", "L'enregistrement s'est arrêté tout seul (micro indisponible ?).");
            if (size === 0 && f.query_exists(null)) f.delete(null);
            return;
        }
        if (duration < 0.8 || size < 200) {
            if (f.query_exists(null)) f.delete(null);
            return; // clic trop bref
        }
        const item = { file, duration: Math.round(duration * 10) / 10, at: this._startIso };
        if (!this.upload) {
            this._notify("Mémo enregistré", `${fmt(duration)} · ${GLib.path_get_basename(file)}`);
            return;
        }
        this._send(item, (ok) => {
            if (!ok) this._addPending(item);
            this._notify("Mémo enregistré", `${fmt(duration)} · ${ok ? "envoyé au journal ✓" : "gardé ici, envoi plus tard"}`);
        });
    }

    /* ---------- envoi ---------- */

    _send(item, cb) {
        const q = `device=mint&duration=${item.duration}&recorded_at=${encodeURIComponent(item.at)}`;
        const args = ["-s", "-f", "--max-time", "120"].concat(this._authArgs(), [
            "-X", "POST", "-H", "Content-Type: audio/ogg", "--data-binary", `@${item.file}`,
            `${this.apiUrl}/memos?${q}`]);
        try {
            const proc = Gio.Subprocess.new(["curl"].concat(args), Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
            proc.wait_async(null, (p, res) => {
                let ok = false;
                try { p.wait_finish(res); ok = p.get_successful(); } catch (e) { ok = false; }
                cb(ok);
            });
        } catch (e) {
            cb(false);
        }
    }

    _readPending() {
        try { return JSON.parse(readText(PENDING_FILE) || "[]"); } catch (e) { return []; }
    }

    _writePending(list) {
        try { GLib.file_set_contents(PENDING_FILE, JSON.stringify(list)); } catch (e) { /* rien */ }
    }

    _addPending(item) {
        const list = this._readPending();
        list.push(item);
        this._writePending(list);
    }

    _flushPending() {
        if (!this.upload || this._flushing) return;
        const list = this._readPending().filter((p) => GLib.file_test(p.file, GLib.FileTest.EXISTS));
        if (!list.length) { this._writePending([]); return; }
        this._flushing = true;
        const remaining = [];
        const next = (i) => {
            if (i >= list.length) {
                this._writePending(remaining);
                this._flushing = false;
                const sent = list.length - remaining.length;
                if (sent) this._notify("Journal vocal", `${sent} mémo${sent > 1 ? "s" : ""} en attente envoyé${sent > 1 ? "s" : ""} ✓`);
                return;
            }
            this._send(list[i], (ok) => { if (!ok) remaining.push(list[i]); next(i + 1); });
        };
        next(0);
    }

    /* ---------- utilitaires ---------- */

    /* Identifiants dans un fichier de config curl en 0600 : jamais visibles dans ps. */
    _writeCurlAuth() {
        this._curlAuthFile = GLib.build_filenamev([CACHE_DIR, "curl-auth.conf"]);
        if (!this.authUser) {
            GLib.unlink(this._curlAuthFile);
            return;
        }
        const esc = (s) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
        const content = `user = "${esc(this.authUser)}:${esc(this.authPassword || "")}"\n`;
        try {
            const file = Gio.File.new_for_path(this._curlAuthFile);
            const stream = file.replace(null, false, Gio.FileCreateFlags.PRIVATE, null);
            stream.write_all(new TextEncoder().encode(content), null);
            stream.close(null);
        } catch (e) {
            global.logError(`journal-vocal: écriture des identifiants impossible : ${e}`);
        }
    }

    _authArgs() {
        return this.authUser ? ["-K", this._curlAuthFile] : [];
    }

    _bindHotkey() {
        Main.keybindingManager.removeHotKey(this._hotkeyId);
        if (this.hotkey) Main.keybindingManager.addHotKey(this._hotkeyId, this.hotkey, () => this.on_applet_clicked());
        if (!this._proc) this._idle();
    }

    _notify(title, body) {
        try { Main.notify(title, body); } catch (e) { global.log(`journal-vocal: ${title} — ${body}`); }
    }

    _openUri(uri) {
        try { Gio.AppInfo.launch_default_for_uri(uri, null); }
        catch (e) { global.logError(`journal-vocal: ${e}`); }
    }

    on_applet_removed_from_panel() {
        if (this._proc) this._stop();
        this._stopTicker();
        if (this._retryTimer) Mainloop.source_remove(this._retryTimer);
        Main.keybindingManager.removeHotKey(this._hotkeyId);
        if (this._curlAuthFile) GLib.unlink(this._curlAuthFile);
        this.settings.finalize();
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new JournalVocalApplet(metadata, orientation, panelHeight, instanceId);
}
