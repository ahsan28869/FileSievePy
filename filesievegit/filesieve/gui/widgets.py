"""Reusable custom widgets."""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from filesieve.gui.theme import COLORS, FONTS, PADDING


class Card(ctk.CTkFrame):
    """A bordered surface panel."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", COLORS["surface"])
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        super().__init__(master, **kwargs)


class StatCard(Card):
    """A card that displays a single numeric statistic."""

    def __init__(self, master, title: str, value: str = "0", **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self._title = ctk.CTkLabel(
            self,
            text=title.upper(),
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self._title.grid(row=0, column=0, sticky="w", padx=PADDING["md"], pady=(PADDING["md"], 0))

        self._value = ctk.CTkLabel(
            self,
            text=value,
            font=("Segoe UI", 26, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        self._value.grid(row=1, column=0, sticky="w", padx=PADDING["md"], pady=(0, PADDING["md"]))

    def set_value(self, value: str) -> None:
        self._value.configure(text=value)


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", COLORS["accent"])
        kwargs.setdefault("hover_color", COLORS["accent_hover"])
        kwargs.setdefault("text_color", "#ffffff")
        kwargs.setdefault("font", FONTS["body"])
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("height", 36)
        super().__init__(master, **kwargs)


class DangerButton(ctk.CTkButton):
    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", COLORS["danger"])
        kwargs.setdefault("hover_color", COLORS["danger_hover"])
        kwargs.setdefault("text_color", "#ffffff")
        kwargs.setdefault("font", FONTS["body"])
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("height", 36)
        super().__init__(master, **kwargs)


class SecondaryButton(ctk.CTkButton):
    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", COLORS["surface_alt"])
        kwargs.setdefault("hover_color", COLORS["border"])
        kwargs.setdefault("text_color", COLORS["text"])
        kwargs.setdefault("font", FONTS["body"])
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("height", 36)
        super().__init__(master, **kwargs)


class SectionHeader(ctk.CTkFrame):
    """A header with a title and optional subtitle."""

    def __init__(
        self,
        master,
        title: str,
        subtitle: Optional[str] = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        ctk.CTkLabel(
            self,
            text=title,
            font=FONTS["heading"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")

        if subtitle:
            ctk.CTkLabel(
                self,
                text=subtitle,
                font=FONTS["small"],
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))


def add_hover(widget, normal: str, hover: str) -> None:
    """Attach hover color change to a widget."""
    widget.bind("<Enter>", lambda _e: widget.configure(fg_color=hover))
    widget.bind("<Leave>", lambda _e: widget.configure(fg_color=normal))