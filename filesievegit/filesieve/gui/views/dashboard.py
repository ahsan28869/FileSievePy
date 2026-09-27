"""Dashboard view showing status and controls."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.widgets import (
    Card,
    DangerButton,
    PrimaryButton,
    SecondaryButton,
    StatCard,
)
from filesieve.utils.config import load_config, save_config


class DashboardView(ctk.CTkFrame):
    """Main dashboard with start/stop controls and stats."""

    def __init__(
        self,
        master,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_undo: Callable[[], dict],
        get_stats: Callable[[], dict],
        **kwargs,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._on_start = on_start
        self._on_stop = on_stop
        self._on_undo = on_undo
        self._get_stats = get_stats

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_stats()
        self._build_directories()
        self._build_controls()

    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["lg"], pady=(PADDING["lg"], PADDING["md"]))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Dashboard",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._status_pill = ctk.CTkLabel(
            header,
            text="  ●  STOPPED  ",
            font=FONTS["subheading"],
            text_color="#ffffff",
            fg_color=COLORS["danger"],
            corner_radius=12,
        )
        self._status_pill.grid(row=0, column=1, sticky="e")

    def _build_stats(self) -> None:
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.grid(row=1, column=0, sticky="ew", padx=PADDING["lg"], pady=(0, PADDING["md"]))
        for i in range(4):
            stats_frame.grid_columnconfigure(i, weight=1, uniform="stat")

        self._stat_files = StatCard(stats_frame, "Files Organized", "0")
        self._stat_files.grid(row=0, column=0, sticky="nsew", padx=(0, PADDING["sm"]))

        self._stat_errors = StatCard(stats_frame, "Errors", "0")
        self._stat_errors.grid(row=0, column=1, sticky="nsew", padx=PADDING["sm"])

        self._stat_watched = StatCard(stats_frame, "Watched Dirs", "0")
        self._stat_watched.grid(row=0, column=2, sticky="nsew", padx=PADDING["sm"])

        self._stat_rules = StatCard(stats_frame, "Active Rules", "0")
        self._stat_rules.grid(row=0, column=3, sticky="nsew", padx=(PADDING["sm"], 0))

    def _build_directories(self) -> None:
        card = Card(self)
        card.grid(row=2, column=0, sticky="nsew", padx=PADDING["lg"], pady=(0, PADDING["md"]))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["md"], pady=(PADDING["md"], PADDING["sm"]))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Watched Directories",
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        SecondaryButton(btn_frame, text="+ Add Folder", width=120, command=self._add_directory).pack(side="left", padx=(0, 6))
        SecondaryButton(btn_frame, text="Remove", width=90, command=self._remove_selected).pack(side="left")

        self._dir_listbox = tk.Listbox(
            card,
            bg=COLORS["surface_alt"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="#ffffff",
            highlightthickness=0,
            borderwidth=0,
            font=FONTS["body"],
            activestyle="none",
        )
        self._dir_listbox.grid(row=1, column=0, sticky="nsew", padx=PADDING["md"], pady=(0, PADDING["md"]))

        self._refresh_directory_list()

    def _build_controls(self) -> None:
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=PADDING["lg"], pady=(0, PADDING["lg"]))

        self._start_btn = PrimaryButton(
            controls, text="▶  Start Monitoring", width=200, command=self._handle_start
        )
        self._start_btn.pack(side="left")

        self._stop_btn = DangerButton(
            controls, text="■  Stop Monitoring", width=200, command=self._handle_stop
        )
        self._stop_btn.pack(side="left", padx=(PADDING["sm"], 0))
        self._stop_btn.configure(state="disabled")

        # Undo button — right-aligned, disabled until there is something to undo.
        self._undo_btn = SecondaryButton(
            controls, text="↩  Undo Last Move", width=170, command=self._handle_undo
        )
        self._undo_btn.pack(side="right")
        self._undo_btn.configure(state="disabled")

    # ------------------------------------------------------------------ #
    def _add_directory(self) -> None:
        folder = filedialog.askdirectory(title="Select a folder to watch")
        if not folder:
            return
        config = load_config()
        dirs = list(config.get("watched_directories", []))
        if folder in dirs:
            messagebox.showinfo("FileSieve", "This folder is already being watched.")
            return
        dirs.append(folder)
        config["watched_directories"] = dirs
        save_config(config)
        self._refresh_directory_list()
        self.refresh_stats()

    def _remove_selected(self) -> None:
        selection = self._dir_listbox.curselection()
        if not selection:
            messagebox.showinfo("FileSieve", "Select a folder first.")
            return
        folder = self._dir_listbox.get(selection[0])
        config = load_config()
        dirs = [d for d in config.get("watched_directories", []) if d != folder]
        config["watched_directories"] = dirs
        save_config(config)
        self._refresh_directory_list()
        self.refresh_stats()

    def _handle_undo(self) -> None:
        # Confirm before doing anything destructive-feeling.
        if not messagebox.askyesno(
            "FileSieve",
            "Move the most recently archived file back to its original folder?",
        ):
            return
        self._on_undo()

    def _refresh_directory_list(self) -> None:
        self._dir_listbox.delete(0, tk.END)
        config = load_config()
        for d in config.get("watched_directories", []):
            self._dir_listbox.insert(tk.END, d)

    def _handle_start(self) -> None:
        config = load_config()
        if not config.get("watched_directories"):
            messagebox.showwarning("FileSieve", "Add at least one folder to watch first.")
            return
        self._on_start()

    def _handle_stop(self) -> None:
        self._on_stop()

    # ------------------------------------------------------------------ #
    def set_running(self, running: bool) -> None:
        if running:
            self._status_pill.configure(text="  ●  RUNNING  ", fg_color=COLORS["success"])
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
        else:
            self._status_pill.configure(text="  ●  STOPPED  ", fg_color=COLORS["danger"])
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")

        # Undo is only available when stopped.
        self._undo_btn.configure(state="disabled" if running else "normal")
        self._refresh_undo_state()

    def _refresh_undo_state(self) -> None:
        """Enable the Undo button only if there's at least one completed move."""
        try:
            stats = self._get_stats()
            if stats.get("undoable", 0) > 0 and self._stop_btn.cget("state") == "disabled":
                self._undo_btn.configure(state="normal")
            elif self._stop_btn.cget("state") == "disabled" and self._start_btn.cget("state") == "normal":
                # Stopped state — enable if undoable
                self._undo_btn.configure(state="normal" if stats.get("undoable", 0) > 0 else "disabled")
        except Exception:
            pass

    def refresh_stats(self) -> None:
        stats = self._get_stats()
        self._stat_files.set_value(str(stats.get("organized", 0)))
        self._stat_errors.set_value(str(stats.get("errors", 0)))
        self._stat_watched.set_value(str(stats.get("watched", 0)))
        self._stat_rules.set_value(str(stats.get("rules", 0)))
        self._refresh_directory_list()
        self._refresh_undo_state()