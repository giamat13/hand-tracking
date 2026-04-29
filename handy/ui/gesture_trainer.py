"""
Gesture Trainer window (CustomTkinter).

Highlights:
  - Multiple training sessions per gesture
  - Per-session delete controls
  - Built-in gestures can be disabled/restored
  - Motion gestures support configurable duration and matching tolerance
"""

from __future__ import annotations

import tkinter as tk
import tkinter.filedialog as fd
from typing import Optional

import customtkinter as ctk

import handy.state as state
from handy.actions import reset_cooldown, validate_hotkey, validate_script
from handy.custom_gestures import (
    BUILTIN_ENTRIES,
    MIN_SAMPLES,
    MOTION_MIN_FRAMES,
    MOTION_RECORD_FRAMES,
    RECORD_SAMPLES,
    GestureSession,
    GestureTemplate,
)
from handy.settings_io import save as save_settings

_BG = "#0f0f0f"
_ACC = "#00ff96"
_FG = "#eeeeee"
_DIM = "#555555"
_ERR = "#ff5555"
_YEL = "#ffdd55"
_MOT = "#ff9944"

_IDLE = "idle"
_RECORDING = "recording"
_DONE = "done"

_ACTION_TYPES = {"none", "hotkey", "script"}
_KEYSYM_MAP: dict[str, str] = {
    "Left": "left", "Right": "right", "Up": "up", "Down": "down",
    "Home": "home", "End": "end", "Prior": "page up", "Next": "page down",
    "Insert": "insert", "Delete": "delete",
    "BackSpace": "backspace", "Tab": "tab", "Return": "enter",
    "Escape": "escape", "space": "space",
    "Shift_L": "shift", "Shift_R": "shift",
    "Control_L": "ctrl", "Control_R": "ctrl",
    "Alt_L": "alt", "Alt_R": "alt",
    "Super_L": "windows", "Super_R": "windows",
    "Caps_Lock": "caps lock", "Num_Lock": "num lock", "Scroll_Lock": "scroll lock",
    "KP_0": "num 0", "KP_1": "num 1", "KP_2": "num 2", "KP_3": "num 3",
    "KP_4": "num 4", "KP_5": "num 5", "KP_6": "num 6", "KP_7": "num 7",
    "KP_8": "num 8", "KP_9": "num 9",
    "KP_Add": "num +", "KP_Subtract": "num -",
    "KP_Multiply": "num *", "KP_Divide": "num /",
    "KP_Enter": "num enter", "KP_Decimal": "num .",
    "Print": "print screen", "Pause": "pause", "Menu": "menu",
    "XF86AudioPlay": "play/pause", "XF86AudioStop": "stop",
    "XF86AudioNext": "next track", "XF86AudioPrev": "previous track",
    "XF86AudioMute": "volume mute",
    "XF86AudioRaiseVolume": "volume up", "XF86AudioLowerVolume": "volume down",
    **{f"F{i}": f"f{i}" for i in range(1, 25)},
}
_MODIFIER_KEYSYMS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R",
    "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Caps_Lock", "Num_Lock", "Scroll_Lock",
}


def _keysym_to_keyboard(keysym: str) -> str:
    if keysym in _KEYSYM_MAP:
        return _KEYSYM_MAP[keysym]
    if len(keysym) == 1:
        return keysym.lower()
    return keysym.lower()


def _build_combo(modifiers: set[str], main_keysym: str) -> str:
    parts: list[str] = []
    if "Control_L" in modifiers or "Control_R" in modifiers:
        parts.append("ctrl")
    if "Shift_L" in modifiers or "Shift_R" in modifiers:
        parts.append("shift")
    if "Alt_L" in modifiers or "Alt_R" in modifiers:
        parts.append("alt")
    if "Super_L" in modifiers or "Super_R" in modifiers:
        parts.append("windows")
    main = _keysym_to_keyboard(main_keysym)
    if main not in parts:
        parts.append(main)
    return "+".join(parts)


def show_gesture_trainer(root: ctk.CTk) -> None:
    if state.gesture_trainer_open:
        print("[TRAINER] open request ignored (already open)")
        return
    state.gesture_trainer_open = True
    print("[TRAINER] opening gesture trainer window")
    try:
        _GestureTrainer(root)
    except Exception as exc:
        state.gesture_trainer_open = False
        print(f"[TRAINER] failed to open: {exc}")
        raise


class _GestureTrainer:

    def __init__(self, root: ctk.CTk) -> None:
        self._root = root
        self._rec_state = _IDLE
        self._sel_name: Optional[str] = None
        self._sel_is_builtin = False
        self._capturing_key = False
        self._held_modifiers: set[str] = set()

        self._win = ctk.CTkToplevel(root)
        self._win.title("Handy – Gesture Trainer")
        self._win.resizable(True, True)
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        ww, wh = 980, 700
        self._win.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//2}")
        self._win.configure(fg_color=_BG)
        self._win.lift()
        self._win.focus_force()
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_list()
        self._poll_recording()

    def _build_ui(self) -> None:
        win = self._win
        title_frame = ctk.CTkFrame(win, fg_color="#1a1a1a", corner_radius=0)
        title_frame.pack(fill="x")
        ctk.CTkLabel(
            title_frame,
            text="●  GESTURE TRAINER",
            font=ctk.CTkFont("Consolas", 14, "bold"),
            text_color=_ACC,
        ).pack(side="left", padx=18, pady=10)

        body = ctk.CTkFrame(win, fg_color=_BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, minsize=250)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_list_panel(body)
        self._build_edit_panel(body)

    def _build_list_panel(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="#161616", corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        scroll = ctk.CTkScrollableFrame(frame, fg_color="#161616")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self._list_scroll = scroll
        ctk.CTkButton(
            frame,
            text="+ Add Custom Gesture",
            command=self._add_new,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_ACC,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            border_width=1,
            border_color=_ACC,
            corner_radius=4,
            height=32,
        ).pack(fill="x", padx=8, pady=6)

    def _build_edit_panel(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color=_BG)
        frame.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        scroll = ctk.CTkScrollableFrame(frame, fg_color=_BG)
        scroll.pack(fill="both", expand=True, padx=16, pady=12)
        self._edit_scroll = scroll

        self._section("Gesture Name")
        self._name_var = tk.StringVar()
        self._name_entry = ctk.CTkEntry(
            scroll,
            textvariable=self._name_var,
            placeholder_text="e.g. My Wave",
            font=ctk.CTkFont("Consolas", 11),
            fg_color="#1a1a1a",
            text_color=_FG,
            border_color=_DIM,
        )
        self._name_entry.pack(fill="x", pady=(2, 10))
        self._sep()

        self._section("Gesture Type")
        self._gesture_kind_var = tk.StringVar(value="static")
        self._kind_buttons = []
        for val, label, colour in [
            ("static", "Static (hold pose)", _FG),
            ("motion", "Motion (move hand)", _MOT),
        ]:
            btn = ctk.CTkRadioButton(
                scroll,
                text=label,
                variable=self._gesture_kind_var,
                value=val,
                command=self._on_gesture_kind_change,
                font=ctk.CTkFont("Consolas", 10),
                text_color=colour,
                fg_color=_ACC,
                hover_color="#00cc77",
                border_color=_ACC,
            )
            btn.pack(anchor="w", pady=2)
            self._kind_buttons.append(btn)
        self._kind_hint = ctk.CTkLabel(
            scroll,
            text="",
            font=ctk.CTkFont("Consolas", 9),
            text_color=_DIM,
            anchor="w",
        )
        self._kind_hint.pack(fill="x", pady=(2, 10))
        self._sep()

        self._section("Training Setup")
        setup_row = ctk.CTkFrame(scroll, fg_color=_BG)
        setup_row.pack(fill="x", pady=(2, 4))
        ctk.CTkLabel(setup_row, text="Sessions to add", font=ctk.CTkFont("Consolas", 10), text_color=_FG).pack(side="left")
        self._session_batch_var = tk.IntVar(value=1)
        self._session_batch_entry = ctk.CTkEntry(
            setup_row,
            textvariable=self._session_batch_var,
            width=60,
            font=ctk.CTkFont("Consolas", 10),
            fg_color="#1a1a1a",
            text_color=_FG,
            border_color=_DIM,
            justify="center",
        )
        self._session_batch_entry.pack(side="left", padx=(8, 18))
        ctk.CTkLabel(setup_row, text="Motion seconds", font=ctk.CTkFont("Consolas", 10), text_color=_FG).pack(side="left")
        self._motion_seconds_var = tk.StringVar(value="1.8")
        self._motion_seconds_entry = ctk.CTkEntry(
            setup_row,
            textvariable=self._motion_seconds_var,
            width=70,
            font=ctk.CTkFont("Consolas", 10),
            fg_color="#1a1a1a",
            text_color=_FG,
            border_color=_DIM,
            justify="center",
        )
        self._motion_seconds_entry.pack(side="left", padx=(8, 0))

        tolerance_row = ctk.CTkFrame(scroll, fg_color=_BG)
        tolerance_row.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(
            tolerance_row,
            text="Motion matching",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_FG,
        ).pack(side="left")
        self._motion_tolerance_var = tk.DoubleVar(value=1.25)
        self._motion_tolerance_slider = ctk.CTkSlider(
            tolerance_row,
            from_=0.8,
            to=1.8,
            number_of_steps=20,
            variable=self._motion_tolerance_var,
            command=self._on_motion_tolerance_change,
            progress_color=_MOT,
            button_color=_MOT,
            button_hover_color="#ffbb66",
        )
        self._motion_tolerance_slider.pack(side="left", fill="x", expand=True, padx=(12, 8))
        self._motion_tolerance_label = ctk.CTkLabel(
            tolerance_row,
            text="125%",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_MOT,
            width=56,
        )
        self._motion_tolerance_label.pack(side="left")

        self._sample_label = ctk.CTkLabel(
            scroll,
            text="0 / 60 samples",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_DIM,
            anchor="w",
        )
        self._sample_label.pack(fill="x")
        self._progress = ctk.CTkProgressBar(scroll, progress_color=_ACC, fg_color="#333")
        self._progress.set(0)
        self._progress.pack(fill="x", pady=4)

        btn_row = ctk.CTkFrame(scroll, fg_color=_BG)
        btn_row.pack(fill="x", pady=(2, 4))
        self._rec_btn = ctk.CTkButton(
            btn_row,
            text="● Record",
            command=self._toggle_record,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_YEL,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            border_width=1,
            border_color=_YEL,
            corner_radius=4,
            width=120,
        )
        self._rec_btn.pack(side="left", padx=(0, 8))
        self._clear_btn = ctk.CTkButton(
            btn_row,
            text="Clear All Sessions",
            command=self._clear_sessions,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_ERR,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1,
            border_color=_ERR,
            corner_radius=4,
            width=140,
        )
        self._clear_btn.pack(side="left")

        self._status_label = ctk.CTkLabel(
            scroll,
            text="Select or create a gesture to begin",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_DIM,
            anchor="w",
        )
        self._status_label.pack(fill="x", pady=(2, 10))
        self._sep()

        self._section("Training Sessions")
        self._session_summary_label = ctk.CTkLabel(
            scroll,
            text="No sessions yet",
            font=ctk.CTkFont("Consolas", 9),
            text_color=_DIM,
            anchor="w",
        )
        self._session_summary_label.pack(fill="x")
        self._session_scroll = ctk.CTkScrollableFrame(scroll, fg_color="#141414", height=160)
        self._session_scroll.pack(fill="x", pady=(4, 10))
        self._sep()

        self._section("Action on Gesture Detected")
        self._action_var = tk.StringVar(value="none")
        for val, label, colour in [
            ("none", "None", _FG),
            ("hotkey", "Hotkey", _FG),
            ("script", "Script", _FG),
        ]:
            ctk.CTkRadioButton(
                scroll,
                text=label,
                variable=self._action_var,
                value=val,
                command=self._on_action_type_change,
                font=ctk.CTkFont("Consolas", 10),
                text_color=colour,
                fg_color=_ACC,
                hover_color="#00cc77",
                border_color=_ACC,
            ).pack(anchor="w", pady=2)

        self._hotkey_frame = ctk.CTkFrame(scroll, fg_color=_BG)
        self._hotkey_var = tk.StringVar()
        self._key_capture_btn = ctk.CTkButton(
            self._hotkey_frame,
            text="Click here then press a key…",
            command=self._start_key_capture,
            fg_color="#1a1a1a",
            hover_color="#252525",
            text_color=_DIM,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1,
            border_color=_DIM,
            corner_radius=4,
            anchor="w",
        )
        self._key_capture_btn.pack(fill="x")
        self._clear_hotkey_btn = ctk.CTkButton(
            self._hotkey_frame,
            text="Clear",
            command=self._clear_hotkey,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_ERR,
            font=ctk.CTkFont("Consolas", 9),
            border_width=1,
            border_color=_ERR,
            corner_radius=4,
            width=60,
            height=26,
        )
        self._clear_hotkey_btn.pack(anchor="e", pady=(4, 0))

        self._script_frame = ctk.CTkFrame(scroll, fg_color=_BG)
        self._action_value_var = tk.StringVar()
        self._action_entry = ctk.CTkEntry(
            self._script_frame,
            textvariable=self._action_value_var,
            placeholder_text="Path or shell command",
            font=ctk.CTkFont("Consolas", 10),
            fg_color="#1a1a1a",
            text_color=_FG,
            border_color=_DIM,
        )
        self._action_entry.pack(side="left", fill="x", expand=True)
        self._browse_btn = ctk.CTkButton(
            self._script_frame,
            text="Browse…",
            command=self._browse_script,
            fg_color="#1e1e1e",
            hover_color="#2a2a2a",
            text_color=_FG,
            font=ctk.CTkFont("Consolas", 10),
            width=80,
            corner_radius=4,
        )
        self._browse_btn.pack(side="left", padx=(6, 0))

        self._action_hint = ctk.CTkLabel(
            scroll,
            text="",
            font=ctk.CTkFont("Consolas", 9),
            text_color=_DIM,
            anchor="w",
        )
        self._action_hint.pack(fill="x", pady=(2, 10))
        self._sep()

        btn_row2 = ctk.CTkFrame(scroll, fg_color=_BG)
        btn_row2.pack(fill="x", pady=(4, 0))
        self._save_btn = ctk.CTkButton(
            btn_row2,
            text="Save",
            command=self._save,
            fg_color=_ACC,
            hover_color="#00cc77",
            text_color="#000",
            font=ctk.CTkFont("Consolas", 11, "bold"),
            corner_radius=6,
            width=110,
        )
        self._save_btn.pack(side="left", padx=(0, 10))
        self._del_btn = ctk.CTkButton(
            btn_row2,
            text="Delete Gesture",
            command=self._delete,
            fg_color="#1e1e1e",
            hover_color="#330000",
            text_color=_ERR,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1,
            border_color=_ERR,
            corner_radius=6,
            width=130,
        )
        self._del_btn.pack(side="left")

        self._on_motion_tolerance_change(self._motion_tolerance_var.get())
        self._on_gesture_kind_change()
        self._on_action_type_change()
        self._set_edit_active(False)

    def _find_template(self, name: str) -> Optional[GestureTemplate]:
        for tmpl in state.CUSTOM_GESTURE_TEMPLATES:
            if tmpl.name == name:
                return tmpl
        return None

    def _ensure_template(self, name: str, builtin: bool) -> GestureTemplate:
        tmpl = self._find_template(name)
        if tmpl is None:
            tmpl = GestureTemplate(name=name, builtin=builtin)
            state.CUSTOM_GESTURE_TEMPLATES.append(tmpl)
        tmpl.builtin = builtin
        return tmpl

    def _effective_template_kind(self, tmpl: Optional[GestureTemplate]) -> str:
        if tmpl is not None and tmpl.kind in {"static", "motion"}:
            return tmpl.kind
        return "static"

    def _selected_gesture_kind(self) -> str:
        kind = self._gesture_kind_var.get()
        return kind if kind in {"static", "motion"} else "static"

    def _selected_batch_count(self) -> int:
        try:
            value = int(str(self._session_batch_var.get()).strip())
        except Exception:
            value = 1
        return max(1, min(value, 10))

    def _selected_motion_seconds(self) -> float:
        try:
            value = float(str(self._motion_seconds_var.get()).strip())
        except Exception:
            value = 1.8
        return max(0.5, min(value, 6.0))

    def _selected_motion_frames(self) -> int:
        return max(MOTION_MIN_FRAMES, min(int(round(self._selected_motion_seconds() * 30)), 180))

    def _record_target(self, kind: str) -> int:
        return self._selected_motion_frames() if kind == "motion" else RECORD_SAMPLES

    def _record_minimum(self, kind: str) -> int:
        return MOTION_MIN_FRAMES if kind == "motion" else MIN_SAMPLES

    def _start_key_capture(self) -> None:
        if self._capturing_key:
            return
        self._capturing_key = True
        self._held_modifiers.clear()
        self._key_capture_btn.configure(
            text="⌨  Press any key (arrows, F-keys, Ctrl/Shift/Alt…)",
            text_color=_YEL,
            border_color=_YEL,
            fg_color="#1a1500",
        )
        self._win.bind("<KeyPress>", self._on_key_press, add=True)
        self._win.bind("<KeyRelease>", self._on_key_release, add=True)
        self._win.focus_force()

    def _stop_key_capture(self) -> None:
        if not self._capturing_key:
            return
        self._capturing_key = False
        try:
            self._win.unbind("<KeyPress>")
            self._win.unbind("<KeyRelease>")
        except Exception:
            pass

    def _on_key_press(self, event: tk.Event) -> None:
        if not self._capturing_key:
            return
        keysym = event.keysym
        if keysym in _MODIFIER_KEYSYMS:
            self._held_modifiers.add(keysym)
            mod_label = "+".join(k.split("_")[0].lower() for k in sorted(self._held_modifiers))
            self._key_capture_btn.configure(text=f"⌨  {mod_label}+…")
            return
        combo = _build_combo(self._held_modifiers, keysym)
        self._hotkey_var.set(combo)
        self._key_capture_btn.configure(
            text=f"  {combo}",
            text_color=_ACC,
            border_color=_ACC,
            fg_color="#001a0f",
        )
        self._stop_key_capture()
        self._action_hint.configure(text="✓ Key captured — press Save to apply", text_color=_ACC)

    def _on_key_release(self, event: tk.Event) -> None:
        self._held_modifiers.discard(event.keysym)

    def _clear_hotkey(self) -> None:
        self._stop_key_capture()
        self._hotkey_var.set("")
        self._key_capture_btn.configure(
            text="Click here then press a key…",
            text_color=_DIM,
            border_color=_DIM,
            fg_color="#1a1a1a",
        )
        self._action_hint.configure(text="", text_color=_DIM)

    def _on_motion_tolerance_change(self, _value) -> None:
        percent = int(round(self._motion_tolerance_var.get() * 100))
        self._motion_tolerance_label.configure(text=f"{percent}%")

    def _set_kind_buttons_state(self, enabled: bool) -> None:
        state_ = "normal" if enabled else "disabled"
        for btn in self._kind_buttons:
            try:
                btn.configure(state=state_)
            except Exception:
                pass

    def _on_gesture_kind_change(self) -> None:
        kind = self._selected_gesture_kind()
        if kind == "motion":
            self._kind_hint.configure(
                text="Use this for a moving gesture like waving. You can tune time and matching below.",
                text_color=_MOT,
            )
            self._motion_seconds_entry.configure(state="normal")
            self._motion_tolerance_slider.configure(state="normal")
        else:
            self._kind_hint.configure(
                text="Use this for a pose you hold steady. New training sessions add to the existing ones.",
                text_color=_DIM,
            )
            self._motion_seconds_entry.configure(state="disabled")
            self._motion_tolerance_slider.configure(state="disabled")

        if self._sel_name is not None:
            tmpl = self._find_template(self._sel_name)
            if tmpl is not None and kind == "motion":
                self._motion_tolerance_var.set(tmpl.motion_tolerance)
            self._on_motion_tolerance_change(self._motion_tolerance_var.get())
            self._update_sample_display(tmpl, kind_override=kind)
            self._refresh_sessions()

    def _refresh_list(self) -> None:
        for widget in self._list_scroll.winfo_children():
            widget.destroy()

        self._section_header("▼ Custom Gestures", self._list_scroll)
        custom = [tmpl for tmpl in state.CUSTOM_GESTURE_TEMPLATES if not tmpl.builtin]
        if custom:
            for tmpl in sorted(custom, key=lambda item: item.name.lower()):
                self._list_row(tmpl.name, is_builtin=False)
        else:
            ctk.CTkLabel(
                self._list_scroll,
                text="  (none yet)",
                font=ctk.CTkFont("Consolas", 9),
                text_color=_DIM,
                anchor="w",
            ).pack(fill="x", padx=8)

        self._section_header("▼ Built-in Gestures", self._list_scroll)
        for name in BUILTIN_ENTRIES:
            self._list_row(name, is_builtin=True)

    def _section_header(self, text: str, parent) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=_ACC,
            anchor="w",
        ).pack(fill="x", padx=8, pady=(10, 2))

    def _list_row(self, name: str, is_builtin: bool) -> None:
        tmpl = self._find_template(name)
        binding = state.GESTURE_BINDINGS.get(name, {})
        btype = binding.get("type", "none")
        bval = binding.get("value", "")

        tag = ""
        if tmpl is not None and tmpl.deleted:
            tag += "  ~ deleted"
        elif tmpl is not None and tmpl.kind == "motion":
            tag += "  ~ motion"
        if tmpl is not None and tmpl.session_count():
            tag += f"  [{tmpl.trained_session_count()}/{tmpl.session_count()} sessions]"
        if btype == "hotkey":
            tag += f"  ⌨ {bval}"
        elif btype == "script":
            tag += f"  ▶ {bval[-22:]}…" if len(bval) > 25 else f"  ▶ {bval}"

        is_sel = name == self._sel_name
        bg = "#1e3a2f" if is_sel else "#1a1a1a"
        row = ctk.CTkFrame(self._list_scroll, fg_color=bg, corner_radius=4)
        row.pack(fill="x", padx=6, pady=2)
        label = ctk.CTkLabel(
            row,
            text=f"  {'⚙' if is_builtin else '●'} {name}{tag}",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_ACC if is_sel else _FG,
            anchor="w",
        )
        label.pack(side="left", padx=4, pady=5, fill="x", expand=True)

        if not is_builtin:
            del_btn = ctk.CTkButton(
                row,
                text="✕",
                width=28,
                height=24,
                fg_color="#1a1a1a",
                hover_color="#330000",
                text_color=_ERR,
                font=ctk.CTkFont("Consolas", 10, "bold"),
                corner_radius=4,
                border_width=0,
            )
            del_btn.configure(command=lambda n=name: self._delete_by_name(n))
            del_btn.pack(side="right", padx=(0, 6))

        for widget in [row, label]:
            widget.bind("<Button-1>", lambda _e, n=name, b=is_builtin: self._select(n, b))

    def _select(self, name: str, is_builtin: bool) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()
        self._sel_name = name
        self._sel_is_builtin = is_builtin
        self._refresh_list()
        self._set_edit_active(True)

        tmpl = self._ensure_template(name, builtin=is_builtin) if is_builtin else self._find_template(name)
        self._name_var.set(name)
        self._name_entry.configure(state="disabled" if is_builtin else "normal")

        kind = self._effective_template_kind(tmpl)
        self._gesture_kind_var.set(kind)
        self._set_kind_buttons_state(not is_builtin)
        self._motion_tolerance_var.set(tmpl.motion_tolerance if tmpl is not None else 1.25)
        self._on_motion_tolerance_change(self._motion_tolerance_var.get())

        binding = state.GESTURE_BINDINGS.get(name, {"type": "none", "value": ""})
        atype = binding.get("type", "none")
        aval = binding.get("value", "")
        if atype not in _ACTION_TYPES:
            atype = "none"
            aval = ""
        self._action_var.set(atype)

        if atype == "hotkey":
            self._hotkey_var.set(aval)
            self._key_capture_btn.configure(
                text=f"  {aval}" if aval else "Click here then press a key…",
                text_color=_ACC if aval else _DIM,
                border_color=_ACC if aval else _DIM,
                fg_color="#001a0f" if aval else "#1a1a1a",
            )
        else:
            self._hotkey_var.set("")
            self._key_capture_btn.configure(
                text="Click here then press a key…",
                text_color=_DIM,
                border_color=_DIM,
                fg_color="#1a1a1a",
            )

        self._action_value_var.set(aval if atype == "script" else "")
        self._del_btn.configure(text="Restore Gesture" if tmpl and tmpl.deleted else "Delete Gesture")

        self._on_gesture_kind_change()
        self._on_action_type_change()
        self._update_sample_display(tmpl, kind_override=kind)
        self._refresh_sessions()

    def _refresh_sessions(self) -> None:
        for widget in self._session_scroll.winfo_children():
            widget.destroy()

        if self._sel_name is None:
            self._session_summary_label.configure(text="No gesture selected", text_color=_DIM)
            return

        tmpl = self._find_template(self._sel_name)
        if tmpl is None or not tmpl.sessions:
            self._session_summary_label.configure(text="No sessions yet", text_color=_DIM)
            return

        trained = tmpl.trained_session_count()
        total = tmpl.session_count()
        status = "deleted" if tmpl.deleted else "active"
        self._session_summary_label.configure(
            text=f"{trained}/{total} trained sessions  •  {status}",
            text_color=_ACC if trained else _DIM,
        )

        for index, session in enumerate(tmpl.sessions, start=1):
            row = ctk.CTkFrame(self._session_scroll, fg_color="#1b1b1b", corner_radius=4)
            row.pack(fill="x", padx=4, pady=2)
            if session.kind == "motion":
                info = (
                    f"Session {index}  •  motion  •  {session.motion_frame_count} frames"
                    f"  •  target {session.target_frames}"
                )
            else:
                info = (
                    f"Session {index}  •  static  •  {len(session.samples)} samples"
                    f"  •  target {session.target_frames}"
                )
            if not session.is_trained():
                info += "  •  weak"
            ctk.CTkLabel(
                row,
                text=info,
                font=ctk.CTkFont("Consolas", 9),
                text_color=_FG,
                anchor="w",
            ).pack(side="left", padx=8, pady=4, fill="x", expand=True)
            del_btn = ctk.CTkButton(
                row,
                text="Delete Session",
                width=104,
                height=24,
                fg_color="#1e1e1e",
                hover_color="#330000",
                text_color=_ERR,
                font=ctk.CTkFont("Consolas", 9),
                border_width=1,
                border_color=_ERR,
                corner_radius=4,
                command=lambda sid=session.id: self._delete_session(sid),
            )
            del_btn.pack(side="right", padx=6, pady=4)

    def _add_new(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        name = f"Gesture {len([t for t in state.CUSTOM_GESTURE_TEMPLATES if not t.builtin]) + 1}"
        tmpl = GestureTemplate(name=name, builtin=False)
        state.CUSTOM_GESTURE_TEMPLATES.append(tmpl)
        self._refresh_list()
        self._select(name, is_builtin=False)

    def _toggle_record(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self) -> None:
        if self._sel_name is None:
            return
        tmpl = self._ensure_template(self._sel_name, builtin=self._sel_is_builtin)
        kind = self._selected_gesture_kind()
        target = self._record_target(kind)
        tmpl.kind = kind
        tmpl.deleted = False
        tmpl.motion_tolerance = self._motion_tolerance_var.get()

        state.recording_samples = []
        state.recording_motion_points = []
        state.recording_mode = kind
        state.recording_target_frames = target
        state.recording_batch_total = self._selected_batch_count()
        state.recording_batch_remaining = state.recording_batch_total
        state.recording_gesture = True
        self._rec_state = _RECORDING
        self._rec_btn.configure(text="■ Stop", text_color=_ERR, border_color=_ERR)
        self._refresh_list()
        self._update_recording_status()
        self._update_sample_display(tmpl, kind_override=kind)

    def _finish_current_session(self, keep_recording: bool) -> None:
        if self._sel_name is None:
            return
        tmpl = self._ensure_template(self._sel_name, builtin=self._sel_is_builtin)
        kind = state.recording_mode
        added: Optional[GestureSession] = None

        if kind == "motion":
            points = list(state.recording_motion_points)
            if points:
                added = tmpl.add_motion_session(points, target_frames=state.recording_target_frames)
            state.recording_motion_points = []
        else:
            samples = list(state.recording_samples)
            if samples:
                added = tmpl.add_static_session(samples, target_frames=state.recording_target_frames)
            state.recording_samples = []

        if added is not None:
            tmpl.deleted = False

        if state.recording_batch_remaining > 0:
            state.recording_batch_remaining -= 1

        if keep_recording and state.recording_batch_remaining > 0:
            state.recording_gesture = True
            self._update_recording_status()
        else:
            state.recording_gesture = False
            state.recording_batch_total = 1
            state.recording_batch_remaining = 0
            self._rec_state = _DONE
            self._rec_btn.configure(text="● Record", text_color=_YEL, border_color=_YEL)
            if added is not None:
                self._status_label.configure(text="✓ Session saved", text_color=_ACC)
            elif kind == "motion":
                self._status_label.configure(text="Motion too weak — try a clearer movement", text_color=_YEL)
            else:
                self._status_label.configure(text="Need more samples in this session", text_color=_YEL)

        self._refresh_list()
        self._refresh_sessions()
        self._update_sample_display(tmpl, kind_override=tmpl.kind)

    def _stop_record(self) -> None:
        if self._rec_state != _RECORDING:
            return
        self._finish_current_session(keep_recording=False)
        state.recording_mode = "static"

    def _clear_sessions(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        if self._sel_name is None:
            return
        tmpl = self._find_template(self._sel_name)
        if tmpl is None:
            return
        tmpl.clear_sessions()
        tmpl.deleted = False if not self._sel_is_builtin else tmpl.deleted
        self._refresh_sessions()
        self._update_sample_display(tmpl, kind_override=self._effective_template_kind(tmpl))

    def _delete_session(self, session_id: str) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        if self._sel_name is None:
            return
        tmpl = self._find_template(self._sel_name)
        if tmpl is None:
            return
        if tmpl.delete_session(session_id):
            save_settings()
            self._refresh_list()
            self._refresh_sessions()
            self._update_sample_display(tmpl, kind_override=tmpl.kind)
            self._status_label.configure(text="Session deleted", text_color=_DIM)

    def _update_recording_status(self) -> None:
        current = max(state.recording_batch_total - state.recording_batch_remaining + 1, 1)
        total = max(state.recording_batch_total, 1)
        if state.recording_mode == "motion":
            secs = self._selected_motion_seconds()
            self._status_label.configure(
                text=f"🔴 Recording motion session {current}/{total}  •  {secs:.1f}s",
                text_color=_YEL,
            )
        else:
            self._status_label.configure(
                text=f"🔴 Hold steady for static session {current}/{total}",
                text_color=_YEL,
            )

    def _update_sample_display(self, tmpl: Optional[GestureTemplate], kind_override: Optional[str] = None) -> None:
        kind = kind_override or self._selected_gesture_kind()
        total = state.recording_target_frames if self._rec_state == _RECORDING and state.recording_mode == kind else self._record_target(kind)
        minimum = self._record_minimum(kind)
        current_count = len(state.recording_motion_points) if kind == "motion" else len(state.recording_samples)

        if self._rec_state == _RECORDING and state.recording_mode == kind:
            count = current_count
        else:
            count = 0

        self._progress.configure(progress_color=_MOT if kind == "motion" else _ACC)
        self._progress.set(min(count / max(total, 1), 1.0))

        suffix = " motion frames" if kind == "motion" else " samples"
        self._sample_label.configure(text=f"{count} / {total}{suffix}")

        if tmpl is None:
            return

        trained_sessions = tmpl.trained_session_count()
        total_sessions = tmpl.session_count()
        if self._rec_state != _RECORDING:
            if tmpl.deleted:
                self._status_label.configure(text="This built-in gesture is deleted/disabled", text_color=_ERR)
            elif trained_sessions:
                kind_text = "motion" if tmpl.kind == "motion" else "static"
                self._status_label.configure(
                    text=f"✓ {trained_sessions}/{total_sessions} trained {kind_text} sessions",
                    text_color=_ACC,
                )
            elif total_sessions:
                if kind == "motion":
                    self._status_label.configure(
                        text="Sessions exist, but movement is too short or weak",
                        text_color=_YEL,
                    )
                else:
                    self._status_label.configure(
                        text=f"Sessions exist, but each needs at least {minimum} samples",
                        text_color=_YEL,
                    )
            else:
                self._status_label.configure(
                    text="No sessions yet — record one or more training sessions",
                    text_color=_DIM,
                )

    def _poll_recording(self) -> None:
        try:
            if self._rec_state == _RECORDING and self._sel_name:
                tmpl = self._find_template(self._sel_name)
                kind = state.recording_mode
                self._update_sample_display(tmpl, kind_override=kind)
                if kind == "motion":
                    n = len(state.recording_motion_points)
                    if n >= state.recording_target_frames:
                        self._finish_current_session(keep_recording=True)
                else:
                    n = len(state.recording_samples)
                    if n >= state.recording_target_frames:
                        self._finish_current_session(keep_recording=True)
        except Exception:
            pass
        if self._win.winfo_exists():
            self._win.after(100, self._poll_recording)

    def _on_action_type_change(self) -> None:
        atype = self._action_var.get()
        self._hotkey_frame.pack_forget()
        self._script_frame.pack_forget()
        if atype == "none":
            self._action_hint.configure(text="No action will be triggered.", text_color=_DIM)
        elif atype == "hotkey":
            self._hotkey_frame.pack(fill="x", pady=(4, 0))
            self._action_hint.configure(
                text="Supports arrows, F-keys, Ctrl/Shift/Alt, media keys, and more.",
                text_color=_DIM,
            )
        elif atype == "script":
            self._script_frame.pack(fill="x", pady=(4, 0))
            self._action_hint.configure(text="Any executable, .py, .bat, .sh, …", text_color=_DIM)

    def _browse_script(self) -> None:
        path = fd.askopenfilename(
            parent=self._win,
            title="Select Script or Executable",
            filetypes=[
                ("All files", "*.*"),
                ("Python", "*.py"),
                ("Batch", "*.bat *.cmd"),
                ("Shell", "*.sh"),
                ("Executable", "*.exe"),
            ],
        )
        if path:
            self._action_value_var.set(path)

    def _save(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()

        name = self._name_var.get().strip()
        if not name:
            self._status_label.configure(text="⚠ Name cannot be empty", text_color=_ERR)
            return

        tmpl = self._find_template(self._sel_name) if self._sel_name else None
        if tmpl is None:
            tmpl = self._ensure_template(name, builtin=self._sel_is_builtin)

        if not self._sel_is_builtin and self._sel_name and name != self._sel_name:
            if self._sel_name in state.GESTURE_BINDINGS:
                state.GESTURE_BINDINGS[name] = state.GESTURE_BINDINGS.pop(self._sel_name)
            tmpl.name = name
            self._sel_name = name
            reset_cooldown(name)

        tmpl.kind = self._selected_gesture_kind()
        tmpl.deleted = False
        tmpl.motion_tolerance = self._motion_tolerance_var.get()
        tmpl.builtin = self._sel_is_builtin

        atype = self._action_var.get()
        if atype not in _ACTION_TYPES:
            atype = "none"

        if atype == "hotkey":
            aval = self._hotkey_var.get().strip()
            if aval:
                ok, err = validate_hotkey(aval)
                if not ok:
                    self._action_hint.configure(text=f"⚠ {err}", text_color=_ERR)
                    return
        elif atype == "script":
            aval = self._action_value_var.get().strip()
            if aval:
                ok, err = validate_script(aval)
                if not ok:
                    self._action_hint.configure(text=f"⚠ {err}", text_color=_ERR)
                    return
        else:
            aval = ""

        state.GESTURE_BINDINGS[name] = {"type": atype, "value": aval}
        reset_cooldown(name)
        save_settings()
        self._del_btn.configure(text="Delete Gesture")
        self._refresh_list()
        self._refresh_sessions()
        self._update_sample_display(tmpl, kind_override=tmpl.kind)
        self._status_label.configure(text="✓ Saved", text_color=_ACC)

    def _delete(self) -> None:
        if self._sel_name is None:
            return
        self._delete_by_name(self._sel_name)

    def _delete_by_name(self, name: str) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()

        tmpl = self._find_template(name)
        is_builtin = name in BUILTIN_ENTRIES

        if is_builtin:
            tmpl = self._ensure_template(name, builtin=True)
            if tmpl.deleted:
                tmpl.deleted = False
                self._status_label.configure(text=f"Restored '{name}'", text_color=_ACC)
                self._del_btn.configure(text="Delete Gesture")
            else:
                tmpl.deleted = True
                tmpl.clear_sessions()
                state.GESTURE_BINDINGS.pop(name, None)
                self._status_label.configure(text=f"Deleted '{name}'", text_color=_DIM)
                self._del_btn.configure(text="Restore Gesture")
        else:
            state.CUSTOM_GESTURE_TEMPLATES = [item for item in state.CUSTOM_GESTURE_TEMPLATES if item.name != name]
            state.GESTURE_BINDINGS.pop(name, None)
            if self._sel_name == name:
                self._sel_name = None
                self._set_edit_active(False)
            self._status_label.configure(text=f"Deleted '{name}'", text_color=_DIM)

        save_settings()
        self._refresh_list()
        self._refresh_sessions()
        if self._sel_name:
            current = self._find_template(self._sel_name)
            if current is not None:
                self._update_sample_display(current, kind_override=current.kind)

    def _section(self, text: str) -> None:
        ctk.CTkLabel(
            self._edit_scroll,
            text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            text_color=_ACC,
            anchor="w",
        ).pack(fill="x", pady=(6, 2))

    def _sep(self) -> None:
        ctk.CTkFrame(self._edit_scroll, fg_color="#2a2a2a", height=1).pack(fill="x", pady=8)

    def _set_edit_active(self, active: bool) -> None:
        state_ = "normal" if active else "disabled"
        for widget in [
            self._name_entry,
            self._rec_btn,
            self._clear_btn,
            self._action_entry,
            self._save_btn,
            self._del_btn,
            self._key_capture_btn,
            self._clear_hotkey_btn,
            self._session_batch_entry,
            self._motion_seconds_entry,
        ]:
            try:
                widget.configure(state=state_)
            except Exception:
                pass
        self._motion_tolerance_slider.configure(state=state_ if self._selected_gesture_kind() == "motion" else "disabled")
        self._set_kind_buttons_state(active and not self._sel_is_builtin)

    def _on_close(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()
        state.recording_samples = []
        state.recording_motion_points = []
        state.recording_mode = "static"
        state.recording_target_frames = RECORD_SAMPLES
        state.recording_batch_total = 1
        state.recording_batch_remaining = 0
        state.gesture_trainer_open = False
        print("[TRAINER] closed")
        self._win.destroy()
