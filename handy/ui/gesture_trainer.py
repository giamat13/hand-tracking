"""
Gesture Trainer window (CustomTkinter).

Changes vs original:
  - Hotkey field replaced by a "click to record" key-capture button
    (supports arrows, modifiers, F-keys, media keys, everything)
  - Delete (✕) button inline next to each custom gesture row
  - New action type "movement" — gesture enables mouse movement mode
"""

from __future__ import annotations

import threading
import tkinter as tk
import tkinter.filedialog as fd
from typing import Optional

import customtkinter as ctk

import handy.state as state
from handy.actions import execute_action, reset_cooldown, validate_hotkey, validate_script
from handy.custom_gestures import BUILTIN_ENTRIES, RECORD_SAMPLES, GestureTemplate
from handy.settings_io import save as save_settings

# ── Palette ────────────────────────────────────────────────────────────────
_BG  = "#0f0f0f"
_ACC = "#00ff96"
_FG  = "#eeeeee"
_DIM = "#555555"
_ERR = "#ff5555"
_YEL = "#ffdd55"
_MOV = "#55aaff"

# ── Recording state machine ────────────────────────────────────────────────
_IDLE      = "idle"
_RECORDING = "recording"
_DONE      = "done"

# ── Key-name normalisation ─────────────────────────────────────────────────
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


# ── Public entry point ─────────────────────────────────────────────────────

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


# ── Main window class ──────────────────────────────────────────────────────

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
        ww, wh = 860, 600
        self._win.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//2}")
        self._win.configure(fg_color=_BG)
        self._win.lift()
        self._win.focus_force()
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_list()
        self._poll_recording()

    # ── UI Construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        win = self._win
        title_frame = ctk.CTkFrame(win, fg_color="#1a1a1a", corner_radius=0)
        title_frame.pack(fill="x")
        ctk.CTkLabel(
            title_frame, text="●  GESTURE TRAINER",
            font=ctk.CTkFont("Consolas", 14, "bold"), text_color=_ACC,
        ).pack(side="left", padx=18, pady=10)

        body = ctk.CTkFrame(win, fg_color=_BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, minsize=240)
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
            frame, text="+ Add Custom Gesture", command=self._add_new,
            fg_color="#1e1e1e", hover_color="#2a2a2a", text_color=_ACC,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            border_width=1, border_color=_ACC, corner_radius=4, height=32,
        ).pack(fill="x", padx=8, pady=6)

    def _build_edit_panel(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color=_BG)
        frame.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        scroll = ctk.CTkScrollableFrame(frame, fg_color=_BG)
        scroll.pack(fill="both", expand=True, padx=16, pady=12)
        self._edit_scroll = scroll

        # Name
        self._section("Gesture Name")
        self._name_var = tk.StringVar()
        self._name_entry = ctk.CTkEntry(
            scroll, textvariable=self._name_var, placeholder_text="e.g.  My Wave",
            font=ctk.CTkFont("Consolas", 11), fg_color="#1a1a1a",
            text_color=_FG, border_color=_DIM,
        )
        self._name_entry.pack(fill="x", pady=(2, 10))
        self._sep()

        # Recording
        self._section("Training Samples")
        self._sample_label = ctk.CTkLabel(
            scroll, text="0 / 30 samples", font=ctk.CTkFont("Consolas", 10),
            text_color=_DIM, anchor="w",
        )
        self._sample_label.pack(fill="x")
        self._progress = ctk.CTkProgressBar(scroll, progress_color=_ACC, fg_color="#333")
        self._progress.set(0)
        self._progress.pack(fill="x", pady=4)

        btn_row = ctk.CTkFrame(scroll, fg_color=_BG)
        btn_row.pack(fill="x", pady=(2, 4))
        self._rec_btn = ctk.CTkButton(
            btn_row, text="● Record", command=self._toggle_record,
            fg_color="#1e1e1e", hover_color="#2a2a2a", text_color=_YEL,
            font=ctk.CTkFont("Consolas", 10, "bold"),
            border_width=1, border_color=_YEL, corner_radius=4, width=120,
        )
        self._rec_btn.pack(side="left", padx=(0, 8))
        self._clear_btn = ctk.CTkButton(
            btn_row, text="✕ Clear", command=self._clear_samples,
            fg_color="#1e1e1e", hover_color="#2a2a2a", text_color=_ERR,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1, border_color=_ERR, corner_radius=4, width=80,
        )
        self._clear_btn.pack(side="left")

        self._status_label = ctk.CTkLabel(
            scroll, text="Select or create a gesture to begin",
            font=ctk.CTkFont("Consolas", 10), text_color=_DIM, anchor="w",
        )
        self._status_label.pack(fill="x", pady=(2, 10))
        self._sep()

        # Action
        self._section("Action on Gesture Detected")
        self._action_var = tk.StringVar(value="none")
        for val, label, colour in [
            ("none",     "None",                   _FG),
            ("hotkey",   "Hotkey",                 _FG),
            ("script",   "Script",                 _FG),
            ("movement", "Movement (move mouse)",  _MOV),
        ]:
            ctk.CTkRadioButton(
                scroll, text=label, variable=self._action_var, value=val,
                command=self._on_action_type_change,
                font=ctk.CTkFont("Consolas", 10), text_color=colour,
                fg_color=_ACC, hover_color="#00cc77", border_color=_ACC,
            ).pack(anchor="w", pady=2)

        # Hotkey capture panel
        self._hotkey_frame = ctk.CTkFrame(scroll, fg_color=_BG)
        self._hotkey_var = tk.StringVar()
        self._key_capture_btn = ctk.CTkButton(
            self._hotkey_frame,
            text="Click here then press a key…",
            command=self._start_key_capture,
            fg_color="#1a1a1a", hover_color="#252525", text_color=_DIM,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1, border_color=_DIM, corner_radius=4, anchor="w",
        )
        self._key_capture_btn.pack(fill="x")
        self._clear_hotkey_btn = ctk.CTkButton(
            self._hotkey_frame, text="Clear", command=self._clear_hotkey,
            fg_color="#1e1e1e", hover_color="#2a2a2a", text_color=_ERR,
            font=ctk.CTkFont("Consolas", 9),
            border_width=1, border_color=_ERR, corner_radius=4, width=60, height=26,
        )
        self._clear_hotkey_btn.pack(anchor="e", pady=(4, 0))

        # Script panel
        self._script_frame = ctk.CTkFrame(scroll, fg_color=_BG)
        self._action_value_var = tk.StringVar()
        self._action_entry = ctk.CTkEntry(
            self._script_frame, textvariable=self._action_value_var,
            placeholder_text="Path or shell command",
            font=ctk.CTkFont("Consolas", 10), fg_color="#1a1a1a",
            text_color=_FG, border_color=_DIM,
        )
        self._action_entry.pack(side="left", fill="x", expand=True)
        self._browse_btn = ctk.CTkButton(
            self._script_frame, text="Browse…", command=self._browse_script,
            fg_color="#1e1e1e", hover_color="#2a2a2a", text_color=_FG,
            font=ctk.CTkFont("Consolas", 10), width=80, corner_radius=4,
        )
        self._browse_btn.pack(side="left", padx=(6, 0))

        # Movement info panel
        self._movement_frame = ctk.CTkFrame(scroll, fg_color="#0a1a2a", corner_radius=6)
        ctk.CTkLabel(
            self._movement_frame,
            text="🖱  When this gesture is detected, the hand position\n"
                 "    will control the mouse cursor directly.\n"
                 "    Enable Mouse Control in Settings to activate.",
            font=ctk.CTkFont("Consolas", 9), text_color=_MOV,
            justify="left", anchor="w",
        ).pack(padx=10, pady=8, fill="x")

        self._action_hint = ctk.CTkLabel(
            scroll, text="", font=ctk.CTkFont("Consolas", 9),
            text_color=_DIM, anchor="w",
        )
        self._action_hint.pack(fill="x", pady=(2, 10))
        self._sep()

        # Save / Delete
        btn_row2 = ctk.CTkFrame(scroll, fg_color=_BG)
        btn_row2.pack(fill="x", pady=(4, 0))
        self._save_btn = ctk.CTkButton(
            btn_row2, text="Save", command=self._save,
            fg_color=_ACC, hover_color="#00cc77", text_color="#000",
            font=ctk.CTkFont("Consolas", 11, "bold"), corner_radius=6, width=110,
        )
        self._save_btn.pack(side="left", padx=(0, 10))
        self._del_btn = ctk.CTkButton(
            btn_row2, text="Delete Gesture", command=self._delete,
            fg_color="#1e1e1e", hover_color="#330000", text_color=_ERR,
            font=ctk.CTkFont("Consolas", 10),
            border_width=1, border_color=_ERR, corner_radius=6, width=110,
        )
        self._del_btn.pack(side="left")

        self._on_action_type_change()
        self._set_edit_active(False)

    # ── Key capture ────────────────────────────────────────────────────────

    def _start_key_capture(self) -> None:
        if self._capturing_key:
            return
        self._capturing_key = True
        self._held_modifiers.clear()
        self._key_capture_btn.configure(
            text="⌨  Press any key (arrows, F-keys, Ctrl/Shift/Alt…)",
            text_color=_YEL, border_color=_YEL, fg_color="#1a1500",
        )
        self._win.bind("<KeyPress>",   self._on_key_press,   add=True)
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
            mod_label = "+".join(
                k.split("_")[0].lower() for k in sorted(self._held_modifiers)
            )
            self._key_capture_btn.configure(text=f"⌨  {mod_label}+…")
            return
        combo = _build_combo(self._held_modifiers, keysym)
        self._hotkey_var.set(combo)
        self._key_capture_btn.configure(
            text=f"  {combo}", text_color=_ACC, border_color=_ACC, fg_color="#001a0f",
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
            text_color=_DIM, border_color=_DIM, fg_color="#1a1a1a",
        )
        self._action_hint.configure(text="", text_color=_DIM)

    # ── List helpers ───────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        for w in self._list_scroll.winfo_children():
            w.destroy()

        self._section_header("▼ Custom Gestures", self._list_scroll)
        custom = state.CUSTOM_GESTURE_TEMPLATES
        if custom:
            for tmpl in custom:
                self._list_row(tmpl.name, is_builtin=False)
        else:
            ctk.CTkLabel(
                self._list_scroll, text="  (none yet)",
                font=ctk.CTkFont("Consolas", 9), text_color=_DIM, anchor="w",
            ).pack(fill="x", padx=8)

        self._section_header("▼ Built-in Gestures", self._list_scroll)
        for name in BUILTIN_ENTRIES:
            self._list_row(name, is_builtin=True)

    def _section_header(self, text: str, parent) -> None:
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"), text_color=_ACC, anchor="w",
        ).pack(fill="x", padx=8, pady=(10, 2))

    def _list_row(self, name: str, is_builtin: bool) -> None:
        binding = state.GESTURE_BINDINGS.get(name, {})
        btype   = binding.get("type", "none")
        bval    = binding.get("value", "")

        tag = ""
        if btype == "hotkey":
            tag = f"  ⌨ {bval}"
        elif btype == "script":
            tag = f"  ▶ {bval[-22:]}…" if len(bval) > 25 else f"  ▶ {bval}"
        elif btype == "movement":
            tag = "  🖱"

        is_sel = (name == self._sel_name)
        bg     = "#1e3a2f" if is_sel else "#1a1a1a"

        row = ctk.CTkFrame(self._list_scroll, fg_color=bg, corner_radius=4)
        row.pack(fill="x", padx=6, pady=2)

        name_lbl = ctk.CTkLabel(
            row, text=f"  {'⚙' if is_builtin else '●'} {name}{tag}",
            font=ctk.CTkFont("Consolas", 10),
            text_color=_ACC if is_sel else _FG, anchor="w",
        )
        name_lbl.pack(side="left", padx=4, pady=5, fill="x", expand=True)

        # Inline ✕ delete button for custom gestures
        if not is_builtin:
            del_btn = ctk.CTkButton(
                row, text="✕", width=28, height=24,
                fg_color="#1a1a1a", hover_color="#330000", text_color=_ERR,
                font=ctk.CTkFont("Consolas", 10, "bold"),
                corner_radius=4, border_width=0,
            )
            del_btn.configure(command=lambda n=name: self._delete_by_name(n))
            del_btn.pack(side="right", padx=(0, 6))

        for widget in [row, name_lbl]:
            widget.bind("<Button-1>", lambda _e, n=name, b=is_builtin: self._select(n, b))

    # ── Selection ─────────────────────────────────────────────────────────

    def _select(self, name: str, is_builtin: bool) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()
        self._sel_name       = name
        self._sel_is_builtin = is_builtin
        self._refresh_list()
        self._set_edit_active(True)

        self._name_var.set(name)
        self._name_entry.configure(state="disabled" if is_builtin else "normal")

        tmpl = self._find_template(name)   # works for both custom and built-in
        self._update_sample_display(tmpl)

        # Recording is allowed for built-ins too (they get an override template)
        self._rec_btn.configure(state="normal")
        self._clear_btn.configure(state="normal")

        binding = state.GESTURE_BINDINGS.get(name, {"type": "none", "value": ""})
        atype   = binding.get("type", "none")
        aval    = binding.get("value", "")
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
                text_color=_DIM, border_color=_DIM, fg_color="#1a1a1a",
            )

        self._action_value_var.set(aval if atype == "script" else "")
        self._on_action_type_change()
        self._del_btn.configure(state="normal" if not is_builtin else "disabled")

    def _add_new(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        name = f"Gesture {len(state.CUSTOM_GESTURE_TEMPLATES) + 1}"
        tmpl = GestureTemplate(name=name)
        state.CUSTOM_GESTURE_TEMPLATES.append(tmpl)
        self._refresh_list()
        self._select(name, is_builtin=False)

    def _find_template(self, name: str) -> Optional[GestureTemplate]:
        for t in state.CUSTOM_GESTURE_TEMPLATES:
            if t.name == name:
                return t
        return None

    # ── Recording ─────────────────────────────────────────────────────────

    def _toggle_record(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        else:
            self._start_record()

    def _start_record(self) -> None:
        if self._sel_name is None:
            return
        # For built-in gestures, create an override template if needed
        tmpl = self._find_template(self._sel_name)
        if tmpl is None:
            tmpl = GestureTemplate(name=self._sel_name)
            state.CUSTOM_GESTURE_TEMPLATES.append(tmpl)
        tmpl.clear_samples()
        state.recording_samples = []
        state.recording_gesture = True
        self._rec_state = _RECORDING
        self._rec_btn.configure(text="■ Stop", text_color=_ERR, border_color=_ERR)
        self._status_label.configure(text="🔴 Hold your gesture steady…", text_color=_YEL)

    def _stop_record(self) -> None:
        state.recording_gesture = False
        self._rec_state = _DONE
        self._rec_btn.configure(text="● Record", text_color=_YEL, border_color=_YEL)
        if self._sel_name:
            tmpl = self._find_template(self._sel_name)
            if tmpl is not None and state.recording_samples:
                tmpl.samples = list(state.recording_samples)
                state.recording_samples = []
                self._update_sample_display(tmpl)

    def _clear_samples(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        if self._sel_name:
            tmpl = self._find_template(self._sel_name)
            if tmpl:
                tmpl.clear_samples()
                state.recording_samples = []
                self._update_sample_display(tmpl)

    def _update_sample_display(self, tmpl) -> None:
        is_builtin_override = (tmpl is not None and self._sel_is_builtin)
        if tmpl is None:
            count, total, trained = 0, RECORD_SAMPLES, False
        else:
            count   = min(tmpl.sample_count(), RECORD_SAMPLES)
            total   = RECORD_SAMPLES
            trained = tmpl.is_trained()

        self._progress.set(count / total if total else 0)
        self._sample_label.configure(
            text=f"{count} / {total} samples" + ("  (override)" if is_builtin_override and count > 0 else "")
        )

        if trained:
            self._status_label.configure(
                text="✓ Trained" + (" — overrides built-in" if is_builtin_override else ""),
                text_color=_ACC,
            )
        elif count > 0:
            self._status_label.configure(
                text=f"Need {total - count} more samples", text_color=_YEL)
        else:
            self._status_label.configure(text="No samples — click Record", text_color=_DIM)

    def _poll_recording(self) -> None:
        try:
            if self._rec_state == _RECORDING and self._sel_name:
                tmpl = self._find_template(self._sel_name)
                n    = len(state.recording_samples)
                if tmpl is not None:
                    tmpl.samples = list(state.recording_samples[:n])
                    self._update_sample_display(tmpl)
                if n >= RECORD_SAMPLES:
                    self._stop_record()
        except Exception:
            pass
        if self._win.winfo_exists():
            self._win.after(100, self._poll_recording)

    # ── Action type UI ─────────────────────────────────────────────────────

    def _on_action_type_change(self) -> None:
        atype = self._action_var.get()
        self._hotkey_frame.pack_forget()
        self._script_frame.pack_forget()
        self._movement_frame.pack_forget()

        if atype == "none":
            self._action_hint.configure(text="No action will be triggered.", text_color=_DIM)
        elif atype == "hotkey":
            self._hotkey_frame.pack(fill="x", pady=(4, 0))
            self._action_hint.configure(
                text="Supports all keys: arrows ◄►▲▼, F1–F24, Ctrl/Shift/Alt, media keys…",
                text_color=_DIM,
            )
        elif atype == "script":
            self._script_frame.pack(fill="x", pady=(4, 0))
            self._action_hint.configure(text="Any executable, .py, .bat, .sh, …", text_color=_DIM)
        elif atype == "movement":
            self._movement_frame.pack(fill="x", pady=(4, 0))
            self._action_hint.configure(
                text="Enable Mouse Control in Settings to use movement mode.",
                text_color=_MOV,
            )

    def _browse_script(self) -> None:
        path = fd.askopenfilename(
            parent=self._win, title="Select Script or Executable",
            filetypes=[("All files", "*.*"), ("Python", "*.py"),
                       ("Batch", "*.bat *.cmd"), ("Shell", "*.sh"), ("Executable", "*.exe")],
        )
        if path:
            self._action_value_var.set(path)

    # ── Save / Delete ─────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()

        name = self._name_var.get().strip()
        if not name:
            self._status_label.configure(text="⚠ Name cannot be empty", text_color=_ERR)
            return

        if not self._sel_is_builtin and self._sel_name and name != self._sel_name:
            tmpl = self._find_template(self._sel_name)
            if tmpl:
                if self._sel_name in state.GESTURE_BINDINGS:
                    state.GESTURE_BINDINGS[name] = state.GESTURE_BINDINGS.pop(self._sel_name)
                tmpl.name = name
                reset_cooldown(name)
            self._sel_name = name

        atype = self._action_var.get()

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
        elif atype == "movement":
            aval = "movement"
            if not state.MOUSE_ENABLED:
                state.MOUSE_ENABLED = True
        else:
            aval = ""

        state.GESTURE_BINDINGS[name] = {"type": atype, "value": aval}
        reset_cooldown(name)
        save_settings()
        self._status_label.configure(text="✓ Saved", text_color=_ACC)
        self._refresh_list()
        print(f"[TRAINER] saved gesture '{name}', action={atype}:{aval}")

    def _delete(self) -> None:
        if self._sel_is_builtin or self._sel_name is None:
            return
        self._delete_by_name(self._sel_name)

    def _delete_by_name(self, name: str) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()

        state.CUSTOM_GESTURE_TEMPLATES = [
            t for t in state.CUSTOM_GESTURE_TEMPLATES if t.name != name
        ]
        state.GESTURE_BINDINGS.pop(name, None)

        if self._sel_name == name:
            self._sel_name = None
            self._set_edit_active(False)

        save_settings()
        self._refresh_list()
        self._status_label.configure(text=f"Deleted '{name}'", text_color=_DIM)
        print(f"[TRAINER] deleted gesture '{name}'")

    # ── Utility ───────────────────────────────────────────────────────────

    def _section(self, text: str) -> None:
        ctk.CTkLabel(
            self._edit_scroll, text=text,
            font=ctk.CTkFont("Consolas", 10, "bold"), text_color=_ACC, anchor="w",
        ).pack(fill="x", pady=(6, 2))

    def _sep(self) -> None:
        ctk.CTkFrame(self._edit_scroll, fg_color="#2a2a2a", height=1).pack(fill="x", pady=8)

    def _set_edit_active(self, active: bool) -> None:
        state_ = "normal" if active else "disabled"
        for w in [self._name_entry, self._rec_btn, self._clear_btn,
                  self._action_entry, self._save_btn, self._del_btn,
                  self._key_capture_btn, self._clear_hotkey_btn]:
            try:
                w.configure(state=state_)
            except Exception:
                pass

    def _on_close(self) -> None:
        if self._rec_state == _RECORDING:
            self._stop_record()
        self._stop_key_capture()
        state.gesture_trainer_open = False
        print("[TRAINER] closed")
        self._win.destroy()