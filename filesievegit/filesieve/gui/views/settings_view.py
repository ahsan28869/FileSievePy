"""Settings view."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.widgets import Card, PrimaryButton, SecondaryButton
from filesieve.utils.config import load_config, save_config


class SettingsView(ctk.CTkFrame):
    """Application settings."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_form()
        self._load()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["lg"], pady=(PADDING["lg"], PADDING["md"]))

        ctk.CTkLabel(
            header,
            text="Settings",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Configure archive destination and monitoring behaviour.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w")

    def _build_form(self) -> None:
        card = Card(self)
        card.grid(row=1, column=0, sticky="ew", padx=PADDING["lg"], pady=(0, PADDING["lg"]))
        card.grid_columnconfigure(1, weight=1)

        # Output directory
        ctk.CTkLabel(
            card,
            text="Archive Destination",
            font=FONTS["body"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=PADDING["md"], pady=(PADDING["md"], 4))

        out_row = ctk.CTkFrame(card, fg_color="transparent")
        out_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=PADDING["md"], pady=(0, PADDING["md"]))
        out_row.grid_columnconfigure(0, weight=1)

        self._output_entry = ctk.CTkEntry(
            out_row,
            font=FONTS["body"],
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=36,
        )
        self._output_entry.grid(row=0, column=0, sticky="ew")

        SecondaryButton(out_row, text="Browse…", width=100, command=self._browse_output).grid(
            row=0, column=1, padx=(PADDING["sm"], 0)
        )

        # Recursive
        self._recursive_var = ctk.BooleanVar(value=False)
        self._recursive_check = ctk.CTkCheckBox(
            card,
            text="Watch directories recursively (include subfolders)",
            variable=self._recursive_var,
            font=FONTS["body"],
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        )
        self._recursive_check.grid(row=2, column=0, columnspan=2, sticky="w", padx=PADDING["md"], pady=(0, PADDING["md"]))

        # Buttons
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", padx=PADDING["md"], pady=(0, PADDING["md"]))

        PrimaryButton(actions, text="Save Settings", width=140, command=self._save).pack(side="left")
        SecondaryButton(actions, text="Reset to Defaults", width=160, command=self._reset).pack(
            side="left", padx=(PADDING["sm"], 0)
        )

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        config = load_config()
        self._output_entry.delete(0, "end")
        self._output_entry.insert(0, config.get("output_directory", ""))
        self._recursive_var.set(bool(config.get("recursive", False)))

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select archive destination")
        if not folder:
            return
        self._output_entry.delete(0, "end")
        self._output_entry.insert(0, folder)

    def _save(self) -> None:
        output = self._output_entry.get().strip()
        if not output:
            messagebox.showerror("FileSieve", "Archive destination cannot be empty.")
            return

        try:
            Path(output).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("FileSieve", f"Cannot create destination:\n{exc}")
            return

        config = load_config()
        config["output_directory"] = output
        config["recursive"] = bool(self._recursive_var.get())
        save_config(config)
        messagebox.showinfo("FileSieve", "Settings saved successfully.")

    def _reset(self) -> None:
        from filesieve.utils.config import DEFAULT_CONFIG

        save_config(dict(DEFAULT_CONFIG))
        self._load()
        messagebox.showinfo("FileSieve", "Settings reset to defaults.")