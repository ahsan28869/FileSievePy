"""File Type Locations view — per-extension destination mapping."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from filesieve.core.locations import LocationEntry, LocationMap
from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.widgets import (
    Card,
    DangerButton,
    PrimaryButton,
    SecondaryButton,
)


class LocationsView(ctk.CTkFrame):
    """Tab where users map extensions to specific folders."""

    def __init__(
        self,
        master,
        location_map_provider: Callable[[], LocationMap],
        on_locations_changed: Callable[[], None],
        **kwargs,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._provider = location_map_provider
        self._on_change = on_locations_changed

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_toggle()
        self._build_list()
        self._build_footer()
        self.refresh()

    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["lg"], pady=(PADDING["lg"], PADDING["sm"]))
        header.grid_columnconfigure(0, weight=1)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_frame,
            text="File Type Locations",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_frame,
            text="Send files by extension to specific folders — overrides general rules.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w")

        SecondaryButton(header, text="↻ Refresh", width=110, command=self.refresh).grid(
            row=0, column=1, sticky="e"
        )

    def _build_toggle(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=PADDING["lg"], pady=(0, PADDING["md"]))

        self._priority_var = ctk.BooleanVar(value=True)
        self._priority_check = ctk.CTkCheckBox(
            row,
            text="Route by type first (recommended — type rules override general rules)",
            variable=self._priority_var,
            font=FONTS["body"],
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
            command=self._toggle_priority,
        )
        self._priority_check.pack(anchor="w")

    def _build_list(self) -> None:
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=PADDING["lg"], pady=(0, PADDING["md"]))
        self._scroll.grid_columnconfigure(0, weight=1)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=PADDING["lg"], pady=(0, PADDING["lg"]))

        PrimaryButton(footer, text="+ Add Location", width=160, command=self._add_entry).pack(side="left")

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        for widget in self._scroll.winfo_children():
            widget.destroy()

        location_map = self._provider()
        self._priority_var.set(location_map.route_by_type_first)

        if not location_map.entries:
            ctk.CTkLabel(
                self._scroll,
                text="No custom locations yet.\nClick '+ Add Location' to map a file extension to a folder.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
                justify="center",
            ).grid(row=0, column=0, pady=PADDING["xl"])
            return

        for idx, entry in enumerate(location_map.entries):
            self._render_entry(entry, idx)

    def _render_entry(self, entry: LocationEntry, row: int) -> None:
        card = Card(self._scroll)
        card.grid(row=row, column=0, sticky="ew", pady=(0, PADDING["sm"]))
        card.grid_columnconfigure(2, weight=1)

        # Extension badge
        ctk.CTkLabel(
            card,
            text=f" {entry.extension} ",
            font=FONTS["subheading"],
            text_color="#ffffff",
            fg_color=COLORS["accent"] if entry.enabled else COLORS["text_muted"],
            corner_radius=8,
            width=70,
        ).grid(row=0, column=0, rowspan=2, padx=PADDING["md"], pady=PADDING["md"], sticky="n")

        ctk.CTkLabel(
            card,
            text="Destination",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).grid(row=0, column=1, columnspan=2, sticky="w", padx=(0, PADDING["md"]), pady=(PADDING["md"], 0))

        ctk.CTkLabel(
            card,
            text=entry.destination,
            font=FONTS["body"],
            text_color=COLORS["text"],
            anchor="w",
            wraplength=520,
            justify="left",
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, PADDING["md"]), pady=(0, PADDING["md"]))

        # Date subfolder tag
        if entry.organize_by_date:
            ctk.CTkLabel(
                card,
                text=" + year/month ",
                font=FONTS["small"],
                text_color=COLORS["accent"],
                fg_color=COLORS["surface_alt"],
                corner_radius=6,
            ).grid(row=2, column=1, sticky="w", padx=(0, PADDING["md"]), pady=(0, PADDING["md"]))

        # Actions
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=3, rowspan=3, padx=PADDING["md"], pady=PADDING["md"], sticky="e")

        SecondaryButton(
            actions,
            text="Edit",
            width=70,
            command=lambda e=entry: self._edit_entry(e),
        ).pack(pady=(0, 4))

        DangerButton(
            actions,
            text="Remove",
            width=80,
            command=lambda e=entry: self._remove_entry(e),
        ).pack()

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _add_entry(self) -> None:
        dialog = _EntryDialog(self, title="Add Location")
        self.wait_window(dialog)
        if dialog.result is None:
            return

        location_map = self._provider()
        # Prevent duplicate extensions
        for existing in location_map.entries:
            if existing.extension == dialog.result.extension:
                messagebox.showwarning(
                    "FileSieve",
                    f"{dialog.result.extension} is already mapped. Edit the existing entry instead.",
                )
                return

        location_map.entries.append(dialog.result)
        self._on_change()
        self.refresh()

    def _edit_entry(self, entry: LocationEntry) -> None:
        dialog = _EntryDialog(self, title="Edit Location", initial=entry)
        self.wait_window(dialog)
        if dialog.result is None:
            return

        location_map = self._provider()
        for i, existing in enumerate(location_map.entries):
            if existing.extension == entry.extension:
                location_map.entries[i] = dialog.result
                break
        self._on_change()
        self.refresh()

    def _remove_entry(self, entry: LocationEntry) -> None:
        if not messagebox.askyesno(
            "FileSieve",
            f"Remove the mapping for {entry.extension}?\n\nFiles will fall back to general rules.",
        ):
            return
        location_map = self._provider()
        location_map.entries = [e for e in location_map.entries if e.extension != entry.extension]
        self._on_change()
        self.refresh()

    def _toggle_priority(self) -> None:
        location_map = self._provider()
        location_map.route_by_type_first = bool(self._priority_var.get())
        self._on_change()


# ---------------------------------------------------------------------- #
# Modal dialog for adding/editing an entry
# ---------------------------------------------------------------------- #
class _EntryDialog(ctk.CTkToplevel):
    """Modal dialog for creating or editing a location entry."""

    def __init__(self, master, title: str, initial: LocationEntry | None = None) -> None:
        super().__init__(master)
        self.result: LocationEntry | None = None

        self.title(title)
        self.geometry("520x320")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self,
            text=title,
            font=FONTS["heading"],
            text_color=COLORS["text"],
        ).grid(row=0, column=0, sticky="w", padx=PADDING["lg"], pady=(PADDING["lg"], PADDING["md"]))

        form = Card(self)
        form.grid(row=1, column=0, sticky="ew", padx=PADDING["lg"])
        form.grid_columnconfigure(1, weight=1)

        # Extension
        ctk.CTkLabel(
            form, text="Extension", font=FONTS["body"], text_color=COLORS["text"], anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=PADDING["md"], pady=(PADDING["md"], 4))

        self._ext_entry = ctk.CTkEntry(
            form,
            font=FONTS["body"],
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=34,
            placeholder_text=".mp4",
        )
        self._ext_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=PADDING["md"], pady=(0, PADDING["sm"]))

        # Destination
        ctk.CTkLabel(
            form, text="Destination folder", font=FONTS["body"], text_color=COLORS["text"], anchor="w"
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=PADDING["md"], pady=(PADDING["sm"], 4))

        dest_row = ctk.CTkFrame(form, fg_color="transparent")
        dest_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=PADDING["md"], pady=(0, PADDING["sm"]))
        dest_row.grid_columnconfigure(0, weight=1)

        self._dest_entry = ctk.CTkEntry(
            dest_row,
            font=FONTS["body"],
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=34,
            placeholder_text="D:\\Videos",
        )
        self._dest_entry.grid(row=0, column=0, sticky="ew")

        SecondaryButton(dest_row, text="Browse…", width=100, command=self._browse).grid(
            row=0, column=1, padx=(PADDING["sm"], 0)
        )

        # Date toggle
        self._date_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            form,
            text="Append /year/month subfolders to destination",
            variable=self._date_var,
            font=FONTS["body"],
            text_color=COLORS["text"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"],
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=PADDING["md"], pady=(0, PADDING["md"]))

        # Buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", padx=PADDING["lg"], pady=PADDING["lg"])

        PrimaryButton(btns, text="Save", width=120, command=self._save).pack(side="right")
        SecondaryButton(btns, text="Cancel", width=110, command=self._cancel).pack(side="right", padx=(0, PADDING["sm"]))

        # Prefill
        if initial is not None:
            self._ext_entry.insert(0, initial.extension)
            self._dest_entry.insert(0, initial.destination)
            self._date_var.set(initial.organize_by_date)
            self._ext_entry.configure(state="disabled")  # don't allow renaming the key

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._ext_entry.focus_set()

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Select destination folder")
        if folder:
            self._dest_entry.delete(0, "end")
            self._dest_entry.insert(0, folder)

    def _save(self) -> None:
        ext = self._ext_entry.get().strip().lower()
        dest = self._dest_entry.get().strip()

        if not ext:
            messagebox.showerror("FileSieve", "Extension is required.", parent=self)
            return
        if not ext.startswith("."):
            ext = "." + ext
        if len(ext) > 12 or any(c in ext for c in "/\\ "):
            messagebox.showerror("FileSieve", "That doesn't look like a valid extension.", parent=self)
            return
        if not dest:
            messagebox.showerror("FileSieve", "Destination folder is required.", parent=self)
            return

        try:
            Path(dest).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("FileSieve", f"Cannot use that destination:\n{exc}", parent=self)
            return

        try:
            self.result = LocationEntry(
                extension=ext,
                destination=dest,
                enabled=True,
                organize_by_date=bool(self._date_var.get()),
            )
        except Exception as exc:
            messagebox.showerror("FileSieve", str(exc), parent=self)
            return

        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()