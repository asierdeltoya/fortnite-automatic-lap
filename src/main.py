import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import keyboard
from PIL import Image, ImageTk

def _enable_dpi_awareness():
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

_enable_dpi_awareness()

import config
import window
from anti_afk import AntiAfk
from config import Settings
from controller import Controller
from mode_b import ModeB
from state_machine import State, StateMachine
from vision import capture_screen, find_template, list_monitors, load_template_auto

TITLE = "twitter:4z5pk"
LOG_MAX_LINES = 500
PAUSED = "PAUSED"

STATE_NAMES = {
    State.IDLE.value: "Parado",
    State.SEARCHING_PLAY.value: "Buscando «Jugar»",
    State.IN_MATCH.value: "En partida",
    State.SKIPPING_RESULT.value: "Saltando resultados",
    State.RETURNING_LOBBY.value: "Volviendo al lobby",
    State.B_LOBBY.value: "B: en el lobby",
    State.B_WAIT_MATCH.value: "B: cargando isla",
    State.B_COUNTDOWN.value: "B: esperando en la isla",
    State.B_MENU.value: "B: saliendo por el menú",
    PAUSED: "En pausa (Fortnite no está delante)",
}

def load_templates(lang):
    return {
        k: (load_template_auto(config.template_path(k, lang), config.PLATES.get(k)) if config.uses_template(k, lang) else None)
        for k in config.TEMPLATE_NAMES
    }

def _fmt_duration(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"

class Worker(threading.Thread):
    def __init__(self, settings, log_q, status):
        super().__init__(daemon=True)
        self.s = settings
        self.log_q = log_q
        self.status = status
        self.stop_event = threading.Event()

    def _load_templates(self, lang):
        templates = load_templates(lang)
        for k, v in templates.items():
            if v is None and k not in config.OPTIONAL_TEMPLATES and config.uses_template(k, lang):
                self.log_q.put(f"falta la imagen: {config.template_filename(k, lang)}")
        return templates

    def _game_ok(self):
        return not self.s.only_foreground or window.game_in_foreground()

    def run(self):
        lang = self.s.lang
        templates = self._load_templates(lang)
        ctrl = Controller(self.s)
        machines = {"A": StateMachine(self.s, templates, ctrl), "B": ModeB(self.s, templates, ctrl)}
        mode = self.s.mode if self.s.mode in machines else "A"
        sm = machines[mode]
        sm.start()

        def total_loops():
            return sum(m.loops for m in machines.values())

        afk = AntiAfk(self.s, active=lambda: sm.state is State.IN_MATCH and self._game_ok())
        afk_thread = threading.Thread(target=afk.run, args=(self.stop_event, self.log_q.put), daemon=True)
        afk_thread.start()
        last_note, last_score = "", -1.0
        paused = False
        while not self.stop_event.is_set():
            try:
                if not self._game_ok():
                    if not paused:
                        self.log_q.put("en pausa: Fortnite no está en primer plano")
                        paused = True
                    self.status.update(state=PAUSED, score=0.0, loops=total_loops())
                    self.stop_event.wait(0.5)
                    continue
                if paused:
                    self.log_q.put("reanudado")
                    paused = False
                if self.s.lang != lang:
                    lang = self.s.lang
                    templates = self._load_templates(lang)
                    for m in machines.values():
                        m.templates = templates
                    self.log_q.put(f"idioma: {config.LANGS.get(lang, lang)}")
                if self.s.mode != mode and self.s.mode in machines:
                    sm.stop()
                    mode = self.s.mode
                    sm = machines[mode]
                    sm.start()
                    self.log_q.put(f"modo: {config.MODES[mode]}")
                frame, ox, oy = capture_screen(self.s.monitor_index)
                r = sm.step(frame, ox, oy)
                self.status.update(state=r.state.value, score=r.score, loops=total_loops())
                if r.note != last_note or r.clicked or abs(r.score - last_score) > 0.1:
                    self.log_q.put(f"[{r.state.value}] {r.note} ({r.score:.2f}/{self.s.threshold:.2f})")
                    last_note, last_score = r.note, r.score
            except Exception as e:
                self.log_q.put(f"error: {e}")
            self.stop_event.wait(self.s.poll_interval)
        afk_thread.join(timeout=2)
        self.status.update(state=State.IDLE.value, score=0.0)

class SnipOverlay:

    def __init__(self, root, key, on_done, lang="es", monitor_index=1):
        self.key, self.on_done, self.lang = key, on_done, lang
        frame, ox, oy = capture_screen(monitor_index)
        self.img = Image.fromarray(frame[:, :, ::-1])
        w, h = self.img.size
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.geometry(f"{w}x{h}+{ox}+{oy}")
        self.top.attributes("-topmost", True)
        self.photo = ImageTk.PhotoImage(self.img)
        self.cv = tk.Canvas(self.top, cursor="cross", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.create_image(0, 0, image=self.photo, anchor="nw")
        self.start = None
        self.rect = None
        self.cv.bind("<ButtonPress-1>", self._down)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._up)
        self.cv.bind("<ButtonPress-3>", lambda e: self._close(None))
        self.top.bind("<Escape>", lambda e: self._close(None))
        self.top.focus_force()

    def _down(self, e):
        self.start = (e.x, e.y)
        self.rect = self.cv.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def _drag(self, e):
        if self.rect:
            self.cv.coords(self.rect, self.start[0], self.start[1], e.x, e.y)

    def _up(self, e):
        if not self.start:
            return
        x0, x1 = sorted((self.start[0], e.x))
        y0, y1 = sorted((self.start[1], e.y))
        if x1 - x0 < 5 or y1 - y0 < 5:
            return self._close(None)
        os.makedirs(config.assets_dir(), exist_ok=True)
        path = config.external_template_path(self.key, self.lang)
        w, h = self.img.size
        if (x1 - x0) * (y1 - y0) > 0.15 * w * h:
            self._close(None, "selección demasiado grande: rodea solo el botón")
            return
        self.img.crop((x0, y0, x1, y1)).save(path)
        self._close(path)

    def _close(self, path, error=None):
        self.top.destroy()
        self.on_done(path, error)

class App:
    def __init__(self):
        self.s = config.load_settings()
        self.log_q = queue.Queue()
        self.status = {"state": State.IDLE.value, "score": 0.0, "loops": 0}
        self.worker = None
        self.t_start = None
        self.t_end = None
        self._save_job = None

        self.root = tk.Tk()
        self.root.title("pk-auto")
        r = self.root
        k = r.winfo_fpixels("1i") / 96.0
        r.geometry(f"{int(430 * k)}x{int(720 * k)}")

        ttk.Label(r, text=TITLE, font=("Segoe UI", 16, "bold")).pack(pady=(8, 0))
        self.info_var = tk.StringVar()
        self.stats_var = tk.StringVar()
        ttk.Label(r, textvariable=self.info_var).pack()
        ttk.Label(r, textvariable=self.stats_var).pack()
        self._show(State.IDLE.value, 0.0, 0)

        row = ttk.Frame(r)
        row.pack(pady=6)
        self.btn = ttk.Button(row, text="Iniciar", command=self.toggle)
        self.btn.pack(side="left", padx=4)
        self.top_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Siempre visible", variable=self.top_var, command=lambda: r.attributes("-topmost", self.top_var.get())).pack(side="left")
        ttk.Label(r, text="F8: iniciar / detener", foreground="gray").pack()

        lang_row = ttk.Frame(r)
        lang_row.pack(pady=(4, 4))
        ttk.Label(lang_row, text="Idioma del juego").pack(side="left", padx=4)
        self.lang_var = tk.StringVar(value=config.LANGS[self.s.lang])
        lang_box = ttk.Combobox(lang_row, textvariable=self.lang_var, values=list(config.LANGS.values()), width=16, state="readonly")
        lang_box.pack(side="left")
        lang_box.bind("<<ComboboxSelected>>", self._on_lang)

        mon_row = ttk.Frame(r)
        mon_row.pack(pady=(0, 4))
        ttk.Label(mon_row, text="Pantalla").pack(side="left", padx=4)
        try:
            monitors = list_monitors()
        except Exception:
            monitors = []
        self.mon_labels = [f"{i}: {w}x{h}" for i, (w, h) in enumerate(monitors, start=1)] or ["1"]
        if self.s.monitor_index > len(self.mon_labels):
            self.s.monitor_index = 1
        self.mon_var = tk.StringVar(value=self.mon_labels[self.s.monitor_index - 1])
        mon_box = ttk.Combobox(mon_row, textvariable=self.mon_var, values=self.mon_labels, width=16, state="readonly")
        mon_box.pack(side="left")
        mon_box.bind("<<ComboboxSelected>>", self._on_monitor)

        self.fg_var = tk.BooleanVar(value=self.s.only_foreground)
        ttk.Checkbutton(
            r,
            text="Pausar si Fortnite no está en primer plano",
            variable=self.fg_var,
            command=lambda: self._set("only_foreground", self.fg_var.get()),
        ).pack()

        self.mode_var = tk.StringVar(value=self.s.mode)
        for code, label in config.MODES.items():
            ttk.Radiobutton(r, text=label, value=code, variable=self.mode_var, command=self._on_mode).pack(anchor="w", padx=16)
        wait_row = ttk.Frame(r)
        wait_row.pack(pady=2)
        self.wait_b_var = tk.StringVar(value=f"{self.s.wait_b:g}")
        ttk.Label(wait_row, text="B: en la isla de espera, esperar").pack(side="left")
        ttk.Spinbox(wait_row, from_=10, to=600, increment=5, width=5, textvariable=self.wait_b_var).pack(side="left", padx=2)
        ttk.Label(wait_row, text="s y pulsar Esc").pack(side="left")
        self.wait_b_var.trace_add("write", lambda *_: self._on_afk_num("wait_b", self.wait_b_var, 10.0, 600.0))

        self.afk_var = tk.BooleanVar(value=self.s.afk_enabled)
        ttk.Checkbutton(
            r,
            text="Pulsar WASD al azar durante la partida",
            variable=self.afk_var,
            command=lambda: self._set("afk_enabled", self.afk_var.get()),
        ).pack()

        afk_row = ttk.Frame(r)
        afk_row.pack(pady=2)
        self.afk_int_var = tk.StringVar(value=f"{self.s.afk_interval:g}")
        self.afk_hold_var = tk.StringVar(value=f"{self.s.afk_hold:g}")
        ttk.Label(afk_row, text="Cada").pack(side="left")
        ttk.Spinbox(afk_row, from_=1, to=600, increment=1, width=5, textvariable=self.afk_int_var).pack(side="left", padx=2)
        ttk.Label(afk_row, text="s / mantener").pack(side="left")
        ttk.Spinbox(afk_row, from_=0.5, to=30, increment=0.5, width=5, textvariable=self.afk_hold_var).pack(side="left", padx=2)
        ttk.Label(afk_row, text="s").pack(side="left")
        self.afk_int_var.trace_add("write", lambda *_: self._on_afk_num("afk_interval", self.afk_int_var, 1.0, 600.0))
        self.afk_hold_var.trace_add("write", lambda *_: self._on_afk_num("afk_hold", self.afk_hold_var, 0.5, 30.0))

        self.th_var = tk.DoubleVar(value=self.s.threshold)
        ttk.Label(r, text="Umbral de detección (algunos botones usan uno fijo)").pack(pady=(6, 0))
        ttk.Scale(r, from_=0.5, to=0.95, variable=self.th_var, command=self._on_th).pack(fill="x", padx=12)
        self.th_lbl = ttk.Label(r, text=f"{self.s.threshold:.2f}")
        self.th_lbl.pack()

        cap = ttk.Frame(r)
        cap.pack(pady=4)
        self.cap_key = tk.StringVar(value="play")
        ttk.Combobox(cap, textvariable=self.cap_key, values=list(config.TEMPLATE_NAMES), width=14, state="readonly").pack(side="left", padx=4)
        ttk.Button(cap, text="Recortar imagen", command=self.capture_template).pack(side="left")

        self.log = tk.Text(r, height=9, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=8, pady=6)

        self._start_hotkey()
        self.root.after(200, self._tick)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # --- settings -------------------------------------------------------

    def _set(self, attr, value):
        setattr(self.s, attr, value)
        self._save_soon()

    def _save_soon(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(800, self._save_now)

    def _save_now(self):
        self._save_job = None
        try:
            config.save_settings(self.s)
        except Exception as e:
            self._log(f"no se pudo guardar la configuración: {e}")

    def _on_th(self, _v):
        self._set("threshold", round(self.th_var.get(), 2))
        self.th_lbl.config(text=f"{self.s.threshold:.2f}")

    def _on_lang(self, _event=None):
        for code, name in config.LANGS.items():
            if name == self.lang_var.get():
                self._set("lang", code)
                self._log(f"idioma: {name}")

    def _on_monitor(self, _event=None):
        label = self.mon_var.get()
        if label in self.mon_labels:
            self._set("monitor_index", self.mon_labels.index(label) + 1)
            self._log(f"pantalla: {label}")

    def _on_mode(self):
        self._set("mode", self.mode_var.get())
        self._log(f"modo: {config.MODES[self.s.mode]}")

    def _on_afk_num(self, attr, var, lo, hi):
        try:
            v = float(var.get())
        except ValueError:
            return
        if lo <= v <= hi:
            self._set(attr, v)

    # --- status ---------------------------------------------------------

    def _show(self, state, score, loops):
        self.info_var.set(f"{STATE_NAMES.get(state, state)}   ·   coincidencia {score:.2f}")
        if self.t_start is None:
            self.stats_var.set(f"Partidas: {loops}")
            return
        elapsed = (self.t_end or time.monotonic()) - self.t_start
        rate = f"   ({loops / (elapsed / 3600):.1f}/h)" if elapsed >= 300 else ""
        self.stats_var.set(f"Partidas: {loops}   Tiempo: {_fmt_duration(elapsed)}{rate}")

    def _running(self):
        return bool(self.worker and self.worker.is_alive() and not self.worker.stop_event.is_set())

    def _stopping(self):
        return bool(self.worker and self.worker.is_alive() and self.worker.stop_event.is_set())

    def toggle(self):
        if self._running():
            self.stop()
        elif not self._stopping():
            self.start()

    def start(self):
        self.status.update(state=State.IDLE.value, score=0.0, loops=0)
        self.worker = Worker(self.s, self.log_q, self.status)
        self.worker.start()
        self.t_start, self.t_end = time.monotonic(), None
        self.btn.config(text="Detener", state="normal")
        self._log("iniciado")

    def stop(self):
        if not self._running():
            return
        self.worker.stop_event.set()
        self.t_end = time.monotonic()
        self.btn.config(text="Deteniendo…", state="disabled")
        self._show(State.IDLE.value, 0.0, self.status.get("loops", 0))
        self._log("detenido")

    def capture_template(self):
        key = self.cap_key.get()
        self.root.withdraw()

        def go():
            def done(path, error=None):
                self.root.deiconify()
                self._log(f"guardado {path}" if path else (error or "recorte cancelado"))

            try:
                SnipOverlay(self.root, key, done, self.s.lang, self.s.monitor_index)
            except Exception as e:
                self.root.deiconify()
                self._log(f"error al recortar: {e}")

        self.root.after(300, go)

    def _start_hotkey(self):
        def listen():
            try:
                keyboard.add_hotkey("f8", lambda: self.root.after(0, self.toggle))
                keyboard.wait()
            except Exception as e:
                self.log_q.put(f"error con la tecla F8: {e}")

        threading.Thread(target=listen, daemon=True).start()

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')} {msg}\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > LOG_MAX_LINES:
            self.log.delete("1.0", f"{lines - LOG_MAX_LINES + 1}.0")
        self.log.see("end")
        self.log.config(state="disabled")

    def _tick(self):
        while True:
            try:
                self._log(self.log_q.get_nowait())
            except queue.Empty:
                break
        if self._running():
            self._show(self.status["state"], self.status["score"], self.status["loops"])
        elif self.worker and not self.worker.is_alive() and str(self.btn.cget("state")) == "disabled":
            self.btn.config(text="Iniciar", state="normal")
            self._show(State.IDLE.value, 0.0, self.status.get("loops", 0))
        self.root.after(200, self._tick)

    def _quit(self):
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
        self._save_now()
        if self.worker:
            self.worker.stop_event.set()
            self.worker.join(timeout=3)
        self.root.destroy()

    def run(self):
        self.root.mainloop()

def selftest(out_path):
    lines = []
    for lang in config.LANGS:
        for k in config.TEMPLATE_NAMES:
            path = config.template_path(k, lang)
            if config.uses_template(k, lang):
                lines.append(f"template {lang}:{k}: loaded={load_template_auto(path, config.PLATES.get(k)) is not None} {path}")
    for mod in ("cv2", "numpy", "mss", "pydirectinput", "keyboard", "PIL.Image", "PIL.ImageTk", "tkinter.ttk"):
        try:
            __import__(mod)
            lines.append(f"import {mod}: ok")
        except Exception as e:
            lines.append(f"import {mod}: FAIL {e}")
    try:
        frame, _, _ = capture_screen(1)
        lines.append(f"capture: ok {frame.shape}")
        tpl = load_template_auto(config.template_path("play"))
        m, score = find_template(frame, tpl, 0.99, config.Settings().scales)
        lines.append(f"match: ok score={score:.2f}")
    except Exception as e:
        lines.append(f"capture/match: FAIL {e}")
    try:
        lines.append(f"foreground: {window.foreground_info()}")
    except Exception as e:
        lines.append(f"foreground: FAIL {e}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        App().run()
