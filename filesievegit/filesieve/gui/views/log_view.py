"""Activity log view."""
from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.widgets import SecondaryButton


class LogView(ctk.CTkFrame):
    """Displays activity log entries in real time."""

    MAX_LINES = 500

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._queue: queue.Queue[str] = queue.Queue()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_log()

        self.after(150, self._drain_queue)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["lg"], pady=(PADDING["lg"], PADDING["md"]))
        header.grid_columnconfigure(0, weight=1)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_frame,
            text="Activity Log",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_frame,
            text="Live stream of files routed and errors encountered.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w")

        SecondaryButton(header, text="Clear", width=90, command=self.clear).grid(row=0, column=1, sticky="e")

    def _build_log(self) -> None:
        container = ctk.CTkFrame(
            self,
            fg_color=COLORS["surface"],
            corner_radius=10,
            border_width=1,
            border_color=COLORS["border"],
        )
        container.grid(row=1, column=0, sticky="nsew", padx=PADDING["lg"], pady=(0, PADDING["lg"]))
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self._text = tk.Text(
            container,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            font=FONTS["mono"],
            borderwidth=0,
            highlightthickness=0,
            wrap="word",
            state="disabled",
        )
        self._text.grid(row=0, column=0, sticky="nsew", padx=PADDING["md"], pady=PADDING["md"])

        scrollbar = ctk.CTkScrollbar(container, command=self._text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=PADDING["md"], padx=(0, PADDING["sm"]))
        self._text.configure(yscrollcommand=scrollbar.set)

        self._text.tag_configure("timestamp", foreground=COLORS["text_muted"])
        self._text.tag_configure("info", foreground=COLORS["text"])
        self._text.tag_configure("success", foreground=COLORS["success"])
        self._text.tag_configure("warning", foreground=COLORS["warning"])
        self._text.tag_configure("error", foreground=COLORS["danger"])

    # ------------------------------------------------------------------ #
    def log(self, message: str, level: str = "info") -> None:
        """Thread-safe log entry."""
        self._queue.put((level, message))  # type: ignore[arg-type]

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.configure(state="disabled")

    # ------------------------------------------------------------------ #
    def _drain_queue(self) -> None:
        drained = 0
        while drained < 50:
            try:
                level, message = self._queue.get_nowait()
            except queue.Empty:
                break
            self._append(level, message)
            drained += 1
        self.after(150, self._drain_queue)

    def _append(self, level: str, message: str) -> None:
        self._text.configure(state="normal")

        # Trim old lines
        line_count = int(self._text.index("end-1c").split(".")[0])
        if line_count > self.MAX_LINES:
            self._text.delete("1.0", f"{line_count - self.MAX_LINES}.0")

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self._text.insert(tk.END, f"{message}\n", level if level in {"info", "success", "warning", "error"} else "info")

        self._text.see(tk.END)
        self._text.configure(state="disabled")