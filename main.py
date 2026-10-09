"""Auto Clicker - main window (CustomTkinter)."""
from __future__ import annotations

import ctypes
import datetime as dt
import os
import queue
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox


def _enable_dpi_awareness() -> None:
    """Make Windows report real pixel coordinates on scaled (125 % / 150 %) displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


_enable_dpi_awareness()

import customtkinter as ctk  # noqa: E402
import pyautogui  # noqa: E402
from pynput import keyboard  # noqa: E402

import acpfile  # noqa: E402
import i18n  # noqa: E402
import storage  # noqa: E402
from clicker import ClickEngine, EngineError, RunConfig  # noqa: E402
from common import (  # noqa: E402
    APP_NAME,
    DEFAULT_DELAY_MS,
    MAX_POINTS,
    PROFILE_EXT,
    in_reserved_corner,
    parse_cycles,
    parse_ms,
)
from hotkeys import HotkeyListener  # noqa: E402
from i18n import LANGUAGES, t  # noqa: E402

HOTKEY_TOGGLE = keyboard.Key.f8
HOTKEY_RECORD = keyboard.Key.f9

GREEN, GREEN_HOVER = "#2e9e57", "#26834a"
RED, RED_HOVER = "#c0392b", "#a93226"
GREY, GREY_HOVER = "#3b3b3b", "#4a4a4a"
TEXT_OK, TEXT_ERR = "#4cd964", "#ff6b6b"
TEXT_INFO = ("gray10", "gray90")
APP_VERSION = "1.0"
CREDIT = "- made by sanz -"
LINKS = [  # (label, handle shown on the button, url)
    ("GitHub", "@sanzwcyd", "https://github.com/sanzwcyd"),
    ("Instagram", "@sanz.arw", "https://www.instagram.com/sanz.arw"),
    ("X", "@LineBezier", "https://x.com/LineBezier"),
    ("Saweria", "sanzwcyd", "https://saweria.co/sanzwcyd"),
]
START_DELAY_MS = 3000  # grace period when Start is pressed with the on-screen button


def resource_path(relative: str) -> str:
    """Path of a bundled file, both when run from source and from the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


class Tooltip:
    """Small hover tooltip for any widget."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip, text=self.text, justify="left", background="#2b2b2b",
            foreground="#f0f0f0", relief="solid", borderwidth=1, wraplength=260,
            padx=8, pady=6, font=("Segoe UI", 9),
        ).pack()

    def _hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("470x760")
        self.resizable(False, False)
        self._set_window_icon()
        self._load_logo()

        self.events: queue.Queue = queue.Queue()
        self.engine = ClickEngine(on_finish=lambda reason: self.events.put(("finished", reason)))
        self.mode = "single"
        self.points: list[dict] = []          # {"x": int, "y": int, "delay": tk.StringVar}
        self._row_widgets: list[list] = []
        self.qwin = None
        self._about = None
        self._busy = False
        self._run_kind = "run"
        self._pending = None                  # after() id of a delayed start
        self._timer_target: dt.datetime | None = None
        self._recent_paths: list[str] = []
        self._override_shown = False
        self._cycles_text = ""
        self._timer_text = ""
        self._status_fn = lambda: t("st_idle")
        self._status_kind = "info"

        self._vcmd_num = self.register(self._valid_number)
        self._vcmd_2 = self.register(self._valid_two_digits)

        self._build_ui()
        self._build_queue_window()
        self._refresh_recent_menu()
        self._render_status()
        self._apply_states()

        self.hotkeys = HotkeyListener({
            HOTKEY_TOGGLE: lambda: self.events.put(("toggle",)),
            HOTKEY_RECORD: lambda: self.events.put(("record",)),
        })
        self.hotkeys.start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._poll)

    # ------------------------------------------------------------ icon / logo
    def _set_window_icon(self) -> None:
        icon = resource_path(os.path.join("assets", "icon.ico"))
        try:
            self.iconbitmap(icon)
            self.after(300, lambda: self.iconbitmap(icon))  # CTk re-applies its own icon at ~200 ms
        except Exception:
            pass  # .ico window icons are Windows-only

    def _load_logo(self) -> None:
        self.logo_small = self.logo_big = None
        try:
            from PIL import Image

            img = Image.open(resource_path(os.path.join("assets", "logo.png"))).convert("RGBA")
            self.logo_small = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
            self.logo_big = ctk.CTkImage(light_image=img, dark_image=img, size=(96, 96))
        except Exception:
            pass  # a missing logo must never stop the app

    # ------------------------------------------------------------- validation
    @staticmethod
    def _valid_number(proposed: str) -> bool:
        return proposed == "" or (proposed.isascii() and proposed.isdigit() and len(proposed) <= 9)

    @staticmethod
    def _valid_two_digits(proposed: str) -> bool:
        return proposed == "" or (proposed.isascii() and proposed.isdigit() and len(proposed) <= 2)

    def _number_entry(self, parent, value: str, width: int = 90) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(parent, width=width, justify="center", validate="key",
                             validatecommand=(self._vcmd_num, "%P"))
        entry.insert(0, value)
        return entry

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        bold = ctk.CTkFont(size=13, weight="bold")
        self.grid_columnconfigure(0, weight=1)

        # --- header: language (left), title (centre), logo = About button (right)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, padx=12, pady=(10, 0), sticky="ew")
        head.grid_columnconfigure(1, weight=1)
        self.lang_menu = ctk.CTkOptionMenu(head, values=list(LANGUAGES.values()), width=140,
                                           dynamic_resizing=False, command=self._on_language_selected)
        self.lang_menu.set(LANGUAGES[i18n.get_language()])
        self.lang_menu.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text=APP_NAME, font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=1)
        self.about_btn = ctk.CTkButton(
            head, text="" if self.logo_small else "AC", image=self.logo_small, width=46, height=46,
            corner_radius=10, fg_color="transparent", hover_color=GREY, command=self._show_about)
        self.about_btn.grid(row=0, column=2, sticky="e")
        Tooltip(self.about_btn, t("about_title"))

        self.mode_buttons = ctk.CTkSegmentedButton(
            self, values=[t("mode_single"), t("mode_multi")], command=self._on_mode_change)
        self.mode_buttons.set(t("mode_single") if self.mode == "single" else t("mode_multi"))
        self.mode_buttons.grid(row=1, column=0, padx=14, pady=(10, 0), sticky="ew")

        # --- settings
        card = ctk.CTkFrame(self)
        card.grid(row=2, column=0, padx=14, pady=(10, 0), sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=t("interval"), anchor="w", justify="left", wraplength=260).grid(
            row=0, column=0, padx=12, pady=(12, 4), sticky="w")
        self.interval_entry = self._number_entry(card, str(DEFAULT_DELAY_MS))
        self.interval_entry.grid(row=0, column=1, padx=12, pady=(12, 4))
        ctk.CTkLabel(card, text=t("cycle_limit"), anchor="w", justify="left", wraplength=260).grid(
            row=1, column=0, padx=12, pady=4, sticky="w")
        self.cycle_entry = self._number_entry(card, "0")
        self.cycle_entry.grid(row=1, column=1, padx=12, pady=4)

        human_row = ctk.CTkFrame(card, fg_color="transparent")
        human_row.grid(row=2, column=0, columnspan=2, padx=12, pady=(4, 12), sticky="w")
        if not hasattr(self, "human_var"):
            self.human_var = tk.BooleanVar(value=False)
        self.human_check = ctk.CTkCheckBox(human_row, text=t("human_mode"), variable=self.human_var)
        self.human_check.pack(side="left")
        help_icon = ctk.CTkLabel(human_row, text="?", width=20, height=20, corner_radius=10,
                                 fg_color=GREY, font=ctk.CTkFont(size=12, weight="bold"))
        help_icon.pack(side="left", padx=(8, 0))
        Tooltip(help_icon, t("human_tip"))

        # --- multi click summary (only visible in Multi mode)
        self.multi_row = ctk.CTkFrame(self)
        self.multi_row.grid(row=3, column=0, padx=14, pady=(10, 0), sticky="ew")
        self.points_label = ctk.CTkLabel(self.multi_row, text=t("points_count", n=len(self.points)))
        self.points_label.pack(side="left", padx=12, pady=10)
        ctk.CTkButton(self.multi_row, text=t("show_queue"), width=150,
                      command=self._show_queue).pack(side="right", padx=12, pady=10)
        self.multi_row.grid_remove()

        # --- start / preview
        run_row = ctk.CTkFrame(self, fg_color="transparent")
        run_row.grid(row=4, column=0, padx=14, pady=(12, 0), sticky="ew")
        run_row.grid_columnconfigure((0, 1), weight=1)
        self.start_btn = ctk.CTkButton(run_row, text=t("start"), height=42, font=bold,
                                       fg_color=GREEN, hover_color=GREEN_HOVER,
                                       command=self._on_start_button)
        self.start_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.preview_btn = ctk.CTkButton(run_row, text=t("preview"), height=42,
                                         fg_color=GREY, hover_color=GREY_HOVER,
                                         command=lambda: self._start_run("preview"))
        self.preview_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # --- status
        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.grid(row=5, column=0, padx=16, pady=(8, 0), sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(status_row, text="", anchor="w", justify="left",
                                         wraplength=320)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.cycles_label = ctk.CTkLabel(status_row, text=t("cycles_count", n=self.engine.cycles),
                                         anchor="e")
        self.cycles_label.grid(row=0, column=1, sticky="e")

        # --- profiles
        prof = ctk.CTkFrame(self)
        prof.grid(row=6, column=0, padx=14, pady=(12, 0), sticky="ew")
        prof.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(prof, text=t("profiles"), font=bold).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(10, 4), sticky="w")
        self.recent_menu = ctk.CTkOptionMenu(prof, values=[t("no_recent")],
                                             command=self._on_recent_selected,
                                             dynamic_resizing=False)
        self.recent_menu.grid(row=1, column=0, columnspan=2, padx=12, pady=4, sticky="ew")
        self.import_btn = ctk.CTkButton(prof, text=t("import"), command=self._import_profile)
        self.import_btn.grid(row=2, column=0, padx=(12, 4), pady=(4, 12), sticky="ew")
        self.export_btn = ctk.CTkButton(prof, text=t("export"), command=self._export_profile)
        self.export_btn.grid(row=2, column=1, padx=(4, 12), pady=(4, 12), sticky="ew")

        # --- timer
        tim = ctk.CTkFrame(self)
        tim.grid(row=7, column=0, padx=14, pady=(12, 0), sticky="ew")
        tim.grid_columnconfigure(5, weight=1)
        ctk.CTkLabel(tim, text=t("timer_title"), font=bold, anchor="w", justify="left",
                     wraplength=420).grid(row=0, column=0, columnspan=6, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(tim, text=t("timer_start_at")).grid(row=1, column=0, padx=(12, 6), pady=4)
        self.hour_entry = ctk.CTkEntry(tim, width=48, justify="center", placeholder_text="HH",
                                       validate="key", validatecommand=(self._vcmd_2, "%P"))
        self.hour_entry.grid(row=1, column=1, pady=4)
        ctk.CTkLabel(tim, text=":").grid(row=1, column=2, padx=3)
        self.min_entry = ctk.CTkEntry(tim, width=48, justify="center", placeholder_text="MM",
                                      validate="key", validatecommand=(self._vcmd_2, "%P"))
        self.min_entry.grid(row=1, column=3, pady=4)
        self.timer_btn = ctk.CTkButton(tim, text=t("timer_arm"), width=150, command=self._toggle_timer)
        self.timer_btn.grid(row=1, column=4, padx=12, pady=4, sticky="w")
        self.timer_label = ctk.CTkLabel(tim, text=t("timer_off"), anchor="w", text_color="gray70")
        self.timer_label.grid(row=2, column=0, columnspan=6, padx=12, pady=(0, 2), sticky="w")
        ctk.CTkLabel(tim, text=t("timer_note"), anchor="w", justify="left", wraplength=420,
                     text_color="gray55", font=ctk.CTkFont(size=11)).grid(
            row=3, column=0, columnspan=6, padx=12, pady=(0, 10), sticky="w")

        # --- footer: hotkeys + kill-switch hint, then the credit line (centred, last)
        ctk.CTkLabel(
            self, text=t("footer_hint"), justify="left", anchor="w", text_color="gray55",
            font=ctk.CTkFont(size=11), wraplength=430,
        ).grid(row=8, column=0, padx=16, pady=(12, 0), sticky="w")
        ctk.CTkLabel(self, text=CREDIT, text_color="gray55", font=ctk.CTkFont(size=12)).grid(
            row=9, column=0, padx=16, pady=(8, 12))

    def _build_queue_window(self) -> None:
        bold = ctk.CTkFont(size=13, weight="bold")
        win = ctk.CTkToplevel(self)
        win.title(t("q_title"))
        win.geometry("400x520")
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(win, text=t("q_title"), font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 0), sticky="w")
        ctk.CTkLabel(win, text=t("q_hint"), justify="left", anchor="w", wraplength=370,
                     text_color="gray70").grid(row=1, column=0, padx=12, pady=(2, 0), sticky="w")

        self.rows_frame = ctk.CTkScrollableFrame(win)
        self.rows_frame.grid(row=2, column=0, padx=10, pady=8, sticky="nsew")
        self.rows_frame.grid_columnconfigure(1, weight=1)
        for col, text in enumerate(["#", t("q_pos"), t("q_delay"), ""]):
            ctk.CTkLabel(self.rows_frame, text=text, font=bold, anchor="w").grid(
                row=0, column=col, padx=4, pady=(0, 4), sticky="w")

        ctk.CTkButton(win, text=t("q_clear"), fg_color=RED, hover_color=RED_HOVER,
                      command=self._clear_points).grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        win.withdraw()
        self.qwin = win

    def _show_queue(self) -> None:
        x = self.winfo_x() + self.winfo_width() + 10
        y = self.winfo_y()
        self.qwin.geometry(f"400x520+{x}+{y}")
        self.qwin.deiconify()
        self.qwin.lift()

    # ------------------------------------------------------------------ About
    def _show_about(self) -> None:
        if self._about is not None and self._about.winfo_exists():
            self._about.deiconify()
            self._about.lift()
            return
        win = ctk.CTkToplevel(self)
        win.title(t("about_title"))
        win.geometry(f"340x500+{self.winfo_x() + 60}+{self.winfo_y() + 60}")
        win.resizable(False, False)
        win.transient(self)
        win.grid_columnconfigure(0, weight=1)
        self._about = win

        if self.logo_big:
            ctk.CTkLabel(win, text="", image=self.logo_big).grid(row=0, column=0, pady=(22, 6))
        ctk.CTkLabel(win, text=APP_NAME, font=ctk.CTkFont(size=22, weight="bold")).grid(row=1, column=0)
        ctk.CTkLabel(win, text=f"v{APP_VERSION}", text_color="gray60").grid(row=2, column=0)
        ctk.CTkLabel(win, text=t("about_tagline"), wraplength=290, justify="center").grid(
            row=3, column=0, padx=20, pady=(8, 14))
        ctk.CTkLabel(win, text=t("about_follow"), font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=4, column=0, pady=(0, 8))
        for index, (name, handle, url) in enumerate(LINKS):
            accent = name == "Saweria"
            ctk.CTkButton(
                win, text=f"{name}   {handle}", width=240, height=34,
                fg_color="#d35400" if accent else GREY,
                hover_color="#b34700" if accent else GREY_HOVER,
                command=lambda u=url: webbrowser.open(u),
            ).grid(row=5 + index, column=0, pady=4)
        ctk.CTkLabel(win, text=CREDIT, text_color="gray55", font=ctk.CTkFont(size=12)).grid(
            row=5 + len(LINKS), column=0, pady=(18, 12))
        win.after(100, win.lift)

    # --------------------------------------------------------------- language
    def _on_language_selected(self, name: str) -> None:
        code = next((c for c, n in LANGUAGES.items() if n == name), None)
        if code is None or code == i18n.get_language():
            return
        i18n.set_language(code)
        storage.save_language(code)
        # rebuild outside the dropdown's own callback
        self.after(30, self._rebuild_ui)

    def _rebuild_ui(self) -> None:
        """Re-create every widget so all texts use the new language; keep all state."""
        saved = (self.interval_entry.get(), self.cycle_entry.get(),
                 self.hour_entry.get(), self.min_entry.get())
        queue_visible = self.qwin is not None and self.qwin.winfo_exists() and self.qwin.state() == "normal"
        about_open = self._about is not None and self._about.winfo_exists()
        if self.qwin is not None:
            self.qwin.destroy()
        if about_open:
            self._about.destroy()
        self._about = None
        for child in list(self.winfo_children()):
            child.destroy()

        self._row_widgets = []
        self._cycles_text = self._timer_text = ""
        self._build_ui()
        self._build_queue_window()

        for entry, value in zip((self.interval_entry, self.cycle_entry, self.hour_entry, self.min_entry), saved):
            entry.delete(0, "end")
            entry.insert(0, value)
        if self.mode == "multi":
            self.multi_row.grid()
        if self._timer_target is not None:
            self.timer_btn.configure(text=t("timer_cancel"))
            self.hour_entry.configure(state="disabled")
            self.min_entry.configure(state="disabled")
        self._rebuild_rows()          # also applies the enabled/disabled states
        self._refresh_recent_menu()
        self._render_status()
        if self.mode == "multi" and queue_visible:
            self._show_queue()
        if about_open:
            self._show_about()

    # -------------------------------------------------------------- mode/state
    def _on_mode_change(self, value: str) -> None:
        self.mode = "single" if value == t("mode_single") else "multi"
        if self.mode == "multi":
            self.multi_row.grid()
            self._show_queue()
        else:
            self.multi_row.grid_remove()
            self.qwin.withdraw()
        self._apply_states()

    def _apply_states(self) -> None:
        busy, multi = self._busy, self.mode == "multi"
        idle = "disabled" if busy else "normal"
        self.mode_buttons.configure(state=idle)
        self.interval_entry.configure(state="disabled" if (busy or multi) else "normal")
        self.cycle_entry.configure(state=idle)
        self.human_check.configure(state=idle)
        self.import_btn.configure(state=idle)
        self.export_btn.configure(state=idle)
        self.recent_menu.configure(state=idle)
        self.preview_btn.configure(state="normal" if (multi and self.points and not busy) else "disabled")
        if busy:
            self.start_btn.configure(text=t("stop"), fg_color=RED, hover_color=RED_HOVER)
        else:
            self.start_btn.configure(text=t("start"), fg_color=GREEN, hover_color=GREEN_HOVER)
        self.points_label.configure(text=t("points_count", n=len(self.points)))

    # ------------------------------------------------------------------ status
    def _set_status(self, source, kind: str = "info") -> None:
        """`source` may be a plain string, an exception or a callable returning text.
        Callables / exceptions are re-evaluated when the language changes."""
        if isinstance(source, str):
            fn = lambda text=source: text  # noqa: E731
        elif isinstance(source, BaseException):
            fn = lambda err=source: str(err)  # noqa: E731
        else:
            fn = source
        self._status_fn, self._status_kind = fn, kind
        self._render_status()

    def _say(self, key: str, kind: str = "info", **params) -> None:
        self._set_status(lambda: t(key, **params), kind)

    def _render_status(self) -> None:
        color = {"ok": TEXT_OK, "error": TEXT_ERR}.get(self._status_kind, TEXT_INFO)
        self.status_label.configure(text=self._status_fn(), text_color=color)

    # ------------------------------------------------------------ run control
    def _build_config(self, kind: str) -> RunConfig:
        """Read the UI into a RunConfig. Raises InputError / EngineError (localized)."""
        if kind == "preview" or self.mode == "multi":
            pts = [(p["x"], p["y"], parse_ms(p["delay"].get(), t("lbl_point_delay", n=i)))
                   for i, p in enumerate(self.points, start=1)]
            if not pts:
                raise EngineError("no_points")
            if kind == "preview":
                return RunConfig("preview", points=pts)
            return RunConfig("multi", points=pts, cycle_limit=parse_cycles(self.cycle_entry.get()),
                             human_mode=bool(self.human_var.get()))
        return RunConfig("single",
                         interval_ms=parse_ms(self.interval_entry.get(), t("lbl_interval")),
                         cycle_limit=parse_cycles(self.cycle_entry.get()),
                         human_mode=bool(self.human_var.get()))

    def _start_run(self, kind: str) -> None:
        if self._busy:
            return
        try:
            cfg = self._build_config(kind)
            self.engine.start(cfg)
        except (ValueError, EngineError) as exc:
            self._set_status(exc, "error")
            return
        self._busy, self._run_kind, self._override_shown = True, kind, False
        self._say("st_previewing" if kind == "preview" else "st_running", "ok")
        self._apply_states()

    def _cancel_pending(self) -> bool:
        if self._pending is None:
            return False
        self.after_cancel(self._pending)
        self._pending = None
        return True

    def _fire_pending(self) -> None:
        self._pending = None
        self._start_run("run")

    def _on_start_button(self) -> None:
        if self._busy:
            self.engine.stop()
            self._say("st_stopping")
            return
        if self._cancel_pending():
            self._say("st_start_cancel")
            return
        if self.mode == "single":
            # The cursor is on this window's Start button right now - give the
            # user a moment to move it to the real target.
            try:
                self._build_config("run")  # report bad input immediately
            except (ValueError, EngineError) as exc:
                self._set_status(exc, "error")
                return
            self._say("st_start_in", s=START_DELAY_MS // 1000)
            self._pending = self.after(START_DELAY_MS, self._fire_pending)
        else:
            self._start_run("run")

    # --------------------------------------------------------------- recording
    def _record_point(self) -> None:
        if self.mode != "multi" or self._busy:
            return
        x, y = pyautogui.position()
        x, y = int(x), int(y)
        if in_reserved_corner(x, y):
            self._say("st_corner_zone", "error")
            return
        if len(self.points) >= MAX_POINTS:
            self._say("st_queue_full", "error", n=MAX_POINTS)
            return
        point = {"x": x, "y": y, "delay": tk.StringVar(value=str(DEFAULT_DELAY_MS))}
        self.points.append(point)
        self._add_row(len(self.points) - 1, point)
        self._apply_states()
        self._say("st_recorded", "ok", n=len(self.points), x=x, y=y)

    def _add_row(self, index: int, point: dict) -> None:
        row = index + 1
        widgets = [
            ctk.CTkLabel(self.rows_frame, text=str(index + 1), width=28),
            ctk.CTkLabel(self.rows_frame, text=f"X {point['x']}   Y {point['y']}", anchor="w"),
            ctk.CTkEntry(self.rows_frame, width=90, justify="center", textvariable=point["delay"],
                         validate="key", validatecommand=(self._vcmd_num, "%P")),
            ctk.CTkButton(self.rows_frame, text="X", width=28, height=26, fg_color=RED,
                          hover_color=RED_HOVER, command=lambda p=point: self._delete_point(p)),
        ]
        for col, widget in enumerate(widgets):
            widget.grid(row=row, column=col, padx=4, pady=3, sticky="w" if col == 1 else "")
        self._row_widgets.append(widgets)

    def _rebuild_rows(self) -> None:
        for widgets in self._row_widgets:
            for widget in widgets:
                widget.destroy()
        self._row_widgets = []
        for index, point in enumerate(self.points):
            self._add_row(index, point)
        self._apply_states()

    def _delete_point(self, point: dict) -> None:
        if point in self.points:
            self.points.remove(point)
            self._rebuild_rows()

    def _clear_points(self) -> None:
        if self.points and messagebox.askyesno(t("q_clear"), t("q_clear_ask"), parent=self.qwin):
            self.points.clear()
            self._rebuild_rows()

    # ---------------------------------------------------------------- profiles
    def _refresh_recent_menu(self) -> None:
        self._recent_paths = storage.load_recent()
        if self._recent_paths:
            values = [f"{i}. {os.path.basename(p)}" for i, p in enumerate(self._recent_paths, start=1)]
        else:
            values = [t("no_recent")]
        self.recent_menu.configure(values=values)
        self.recent_menu.set(t("recent_ph"))

    def _on_recent_selected(self, choice: str) -> None:
        self.recent_menu.set(t("recent_ph"))
        try:
            path = self._recent_paths[int(choice.split(".", 1)[0]) - 1]
        except (ValueError, IndexError):
            return
        self._import_profile(path)

    def _import_profile(self, path: str | None = None) -> None:
        if self._busy:
            return
        if not path:
            path = filedialog.askopenfilename(
                parent=self, title=t("dlg_import"),
                filetypes=[("Auto Clicker Profile", f"*{PROFILE_EXT}"), ("All files", "*.*")])
            if not path:
                return
        try:
            points, settings = acpfile.load_profile(path)
        except acpfile.ProfileError as exc:
            messagebox.showerror(t("dlg_import_fail"), str(exc), parent=self)
            return

        self.points = [{"x": x, "y": y, "delay": tk.StringVar(value=str(d))} for x, y, d in points]
        self.cycle_entry.delete(0, "end")
        self.cycle_entry.insert(0, str(settings["cycle_limit"]))
        self.human_var.set(settings["human_mode"])
        self.mode_buttons.set(t("mode_multi"))
        self._on_mode_change(t("mode_multi"))
        self._rebuild_rows()
        storage.add_recent(path)
        self._refresh_recent_menu()
        self._say("st_loaded", "ok", name=os.path.basename(path), n=len(points))

    def _export_profile(self) -> None:
        if self._busy:
            return
        if not self.points:
            messagebox.showinfo(t("dlg_export"), t("dlg_nothing"), parent=self)
            return
        try:
            pts = [(p["x"], p["y"], parse_ms(p["delay"].get(), t("lbl_point_delay", n=i)))
                   for i, p in enumerate(self.points, start=1)]
            cycles = parse_cycles(self.cycle_entry.get())
        except ValueError as exc:
            messagebox.showerror(t("dlg_export_fail"), str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title=t("dlg_export"), defaultextension=PROFILE_EXT,
            initialfile=f"my_profile{PROFILE_EXT}",
            filetypes=[("Auto Clicker Profile", f"*{PROFILE_EXT}")])
        if not path:
            return
        try:
            saved = acpfile.save_profile(path, pts, human_mode=bool(self.human_var.get()),
                                         cycle_limit=cycles)
        except acpfile.ProfileError as exc:
            messagebox.showerror(t("dlg_export_fail"), str(exc), parent=self)
            return
        storage.add_recent(saved)
        self._refresh_recent_menu()
        self._say("st_saved", "ok", name=os.path.basename(saved))

    # ------------------------------------------------------------------- timer
    def _toggle_timer(self) -> None:
        if self._timer_target is not None:
            self._disarm_timer()
            return
        try:
            hour, minute = int(self.hour_entry.get()), int(self.min_entry.get())
        except ValueError:
            self._say("st_timer_enter", "error")
            return
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            self._say("st_timer_range", "error")
            return
        now = dt.datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        self._timer_target = target
        self.timer_btn.configure(text=t("timer_cancel"))
        self.hour_entry.configure(state="disabled")
        self.min_entry.configure(state="disabled")

    def _disarm_timer(self) -> None:
        self._timer_target = None
        self.timer_btn.configure(text=t("timer_arm"))
        self.hour_entry.configure(state="normal")
        self.min_entry.configure(state="normal")
        self._set_timer_text(t("timer_off"))

    def _set_timer_text(self, text: str) -> None:
        if text != self._timer_text:
            self._timer_text = text
            self.timer_label.configure(text=text)

    def _tick_timer(self) -> None:
        target = self._timer_target
        if target is None:
            return
        now = dt.datetime.now()
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            if remaining >= -120:
                self._disarm_timer()
                if not self._busy:
                    self._cancel_pending()
                    self._start_run("run")
                return
            # Woke up long after the target (PC asleep?): wait for the next day.
            target += dt.timedelta(days=1)
            self._timer_target = target
            remaining = (target - now).total_seconds()
        secs = int(remaining)
        left = f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
        self._set_timer_text(t("timer_running", time=f"{target:%H:%M}", left=left))

    # -------------------------------------------------------------- event loop
    def _poll(self) -> None:
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self._tick_ui()
        self._tick_timer()
        self.after(50, self._poll)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "toggle":
            if self._busy:
                self.engine.stop()
                self._say("st_stopping")
            else:
                self._cancel_pending()
                self._start_run("run")
        elif kind == "record":
            self._record_point()
        elif kind == "finished":
            reason = event[1]
            was_preview = self._run_kind == "preview"
            cycles = self.engine.cycles
            self._busy = False
            if reason == "completed":
                if was_preview:
                    self._say("st_preview_done")
                else:
                    self._say("st_finished", n=cycles)
            elif reason == "stopped":
                self._say("st_stopped")
            else:
                self._set_status(reason, "error")
            self._apply_states()

    def _tick_ui(self) -> None:
        text = t("cycles_count", n=self.engine.cycles)
        if text != self._cycles_text:
            self._cycles_text = text
            self.cycles_label.configure(text=text)
        if self._busy:
            override = self.engine.user_override
            if override and not self._override_shown:
                self._override_shown = True
                self._say("st_paused", "error")
            elif not override and self._override_shown:
                self._override_shown = False
                self._say("st_running", "ok")

    # ------------------------------------------------------------------- close
    def _on_close(self) -> None:
        self._cancel_pending()
        self.engine.stop()
        self.hotkeys.stop()
        self.destroy()


def main() -> None:
    i18n.set_language(storage.load_language())
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
