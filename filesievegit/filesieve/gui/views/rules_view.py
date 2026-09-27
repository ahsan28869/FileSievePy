"""Rules management view."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable

import customtkinter as ctk

from filesieve.core.rules import Rule, RuleSet
from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.widgets import (
    Card,
    DangerButton,
    PrimaryButton,
    SecondaryButton,
)
from filesieve.utils.config import load_config


class RulesView(ctk.CTkFrame):
    """Read-only view + toggle of rules (editing is done via YAML)."""

    def __init__(
        self,
        master,
        ruleset_provider: Callable[[], RuleSet],
        on_rules_changed: Callable[[], None],
        **kwargs,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self._ruleset_provider = ruleset_provider
        self._on_rules_changed = on_rules_changed

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_list()
        self.refresh()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["lg"], pady=(PADDING["lg"], PADDING["md"]))
        header.grid_columnconfigure(0, weight=1)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_frame,
            text="Routing Rules",
            font=FONTS["title"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_frame,
            text="Rules are evaluated by priority (highest first).",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w")

        SecondaryButton(header, text="↻ Refresh", width=110, command=self.refresh).grid(row=0, column=1, sticky="e")

    def _build_list(self) -> None:
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=PADDING["lg"], pady=(0, PADDING["lg"]))
        self._scroll.grid_columnconfigure(0, weight=1)

    def refresh(self) -> None:
        for widget in self._scroll.winfo_children():
            widget.destroy()

        ruleset = self._ruleset_provider()
        if not ruleset.rules:
            ctk.CTkLabel(
                self._scroll,
                text="No rules defined.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
            ).grid(row=0, column=0, pady=PADDING["lg"])
            return

        sorted_rules = sorted(ruleset.rules, key=lambda r: r.priority, reverse=True)
        for idx, rule in enumerate(sorted_rules):
            self._render_rule(rule, idx)

    def _render_rule(self, rule: Rule, row: int) -> None:
        card = Card(self._scroll)
        card.grid(row=row, column=0, sticky="ew", pady=(0, PADDING["sm"]))
        card.grid_columnconfigure(1, weight=1)

        # Priority badge
        badge = ctk.CTkLabel(
            card,
            text=f" {rule.priority} ",
            font=FONTS["subheading"],
            text_color="#ffffff",
            fg_color=COLORS["accent"] if rule.enabled else COLORS["text_muted"],
            corner_radius=8,
            width=44,
        )
        badge.grid(row=0, column=0, rowspan=2, padx=PADDING["md"], pady=PADDING["md"], sticky="n")

        # Name + meta
        ctk.CTkLabel(
            card,
            text=rule.name,
            font=FONTS["subheading"],
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, PADDING["md"]), pady=(PADDING["md"], 0))

        meta_parts = []
        if rule.mime_types:
            meta_parts.append("MIME: " + ", ".join(rule.mime_types))
        if rule.extensions:
            meta_parts.append("EXT: " + ", ".join(rule.extensions))
        if rule.name_contains:
            meta_parts.append("CONTAINS: " + ", ".join(rule.name_contains))
        meta = "  •  ".join(meta_parts) if meta_parts else "Matches all files"

        ctk.CTkLabel(
            card,
            text=meta,
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).grid(row=1, column=1, sticky="w", padx=(0, PADDING["md"]), pady=(0, 2))

        ctk.CTkLabel(
            card,
            text=f"→  {rule.destination}",
            font=FONTS["small"],
            text_color=COLORS["accent"],
            anchor="w",
        ).grid(row=2, column=1, sticky="w", padx=(0, PADDING["md"]), pady=(0, PADDING["md"]))

        # Toggle button
        toggle_text = "Disable" if rule.enabled else "Enable"
        SecondaryButton(
            card,
            text=toggle_text,
            width=90,
            command=lambda r=rule: self._toggle_rule(r),
        ).grid(row=0, column=2, rowspan=3, padx=PADDING["md"], pady=PADDING["md"])

    def _toggle_rule(self, rule: Rule) -> None:
        ruleset = self._ruleset_provider()
        for r in ruleset.rules:
            if r.name == rule.name:
                r.enabled = not r.enabled
                break
        self._on_rules_changed()
        self.refresh()