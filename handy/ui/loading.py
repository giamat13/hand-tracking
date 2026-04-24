"""Loading splash window (CustomTkinter).

Uses a raw tk.Canvas for the spinner animation since CTk has no canvas widget.
The CTk root window acts as the splash; it is withdrawn once loading completes.
"""

import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import handy.state as state

_ACCENT = "#00ff96"
_BG = "#0a0a0a"


def show_loading_window(root: ctk.CTk) -> None:
    """Configure *root* as a borderless splash screen and begin animating."""
    root.title("Handy - Loading")
    root.resizable(False, False)
    w, h = 420, 280
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    root.overrideredirect(True)
    root.configure(fg_color=_BG)

    # Raw tk.Canvas for animation (CTk provides no canvas widget)
    canvas = tk.Canvas(root, width=w, height=h, bg=_BG, highlightthickness=0)
    canvas.pack()

    canvas.create_rectangle(2, 2, w - 2, h - 2, outline=_ACCENT, width=1)
    canvas.create_text(w // 2, 50, text="HANDY",
                       font=("Consolas", 22, "bold"), fill=_ACCENT)

    cx, cy, r = w // 2, 145, 35
    arcs = []
    for i in range(12):
        arc = canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=i * 30, extent=20,
            outline=_ACCENT, width=3, style="arc",
        )
        arcs.append(arc)

    status_id = canvas.create_text(w // 2, 205, text="Starting...",
                                   font=("Consolas", 10), fill=_ACCENT)
    dots_id = canvas.create_text(w // 2, 235, text="",
                                 font=("Consolas", 9), fill="#555555")

    angle_offset = [0]
    dot_count = [0]
    dot_timer = [time.time()]

    def animate():
        ready = (state.model_ready or state.model_error) and (
            state.camera_ready or state.camera_error
        )
        if ready:
            root.overrideredirect(False)
            if state.camera_error and not state.camera_ready:
                root.after(
                    0,
                    lambda: messagebox.showerror("Handy - Camera Error", state.camera_error),
                )
                root.after(0, root.destroy)
            else:
                root.withdraw()
            return

        angle_offset[0] = (angle_offset[0] + 6) % 360
        for i, arc in enumerate(arcs):
            start = (i * 30 + angle_offset[0]) % 360
            brightness = int(60 + 195 * (i / 12))
            canvas.itemconfig(arc, start=start,
                              outline=f"#00{brightness:02x}{brightness // 2:02x}")

        canvas.itemconfig(status_id, text=state.loading_status)
        if time.time() - dot_timer[0] > 0.5:
            dot_count[0] = (dot_count[0] + 1) % 4
            canvas.itemconfig(dots_id, text="● " * dot_count[0])
            dot_timer[0] = time.time()

        root.after(40, animate)

    animate()
