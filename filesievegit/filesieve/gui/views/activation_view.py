"""First-run activation / trial screen."""
from __future__ import annotations

import threading

import customtkinter as ctk

from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.widgets import PrimaryButton, SecondaryButton
from filesieve.licensing import (
    TRIAL_DAYS,
    activate_license,
    start_trial,
    trial_status,
)


class ActivationView(ctk.CTkFrame):
    """Full-screen activation page shown on first run or when trial expires."""

    def __init__(self, master, on_activated, **kwargs) -> None:
        kwargs.setdefault("fg_color", COLORS["bg"])
        super().__init__(master, **kwargs)
        self._on_activated = on_activated

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0)
        container.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(
            container,
            text="FileSieve",
            font=("Segoe UI", 34, "bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Set it once. Never sort a file again.",
            font=FONTS["heading"],
            text_color=COLORS["text"],
        ).grid(row=1, column=0, pady=(0, PADDING["xl"]))

        # Feature highlights
        features = [
            "✓  Automatically organizes every new file",
            "✓  Watches your folders in real time",
            "✓  Sorts invoices, images, videos, and more",
            "✓  Never loses or overwrites a file",
        ]
        for i, text in enumerate(features):
            ctk.CTkLabel(
                container,
                text=text,
                font=FONTS["body"],
                text_color=COLORS["text_muted"],
                anchor="w",
            ).grid(row=2 + i, column=0, sticky="w", pady=2)

        # Status line
        status = trial_status()
        if status["state"] == "expired":
            status_text = "Your free trial has ended."
            status_color = COLORS["danger"]
        else:
            status_text = f"Start your free {TRIAL_DAYS}-day trial — no credit card required."
            status_color = COLORS["success"]

        ctk.CTkLabel(
            container,
            text=status_text,
            font=FONTS["subheading"],
            text_color=status_color,
        ).grid(row=6, column=0, pady=(PADDING["xl"], PADDING["md"]))

        # Buttons
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.grid(row=7, column=0, pady=(0, PADDING["md"]))

        PrimaryButton(
            btn_row,
            text=f"▶  Start {TRIAL_DAYS}-Day Free Trial",
            width=260,
            command=self._start_trial,
        ).pack(pady=4)

        SecondaryButton(
            btn_row,
            text="I already purchased — Enter License Key",
            width=260,
            command=self._show_license_dialog,
        ).pack(pady=4)

        # Buy link
        buy_link = ctk.CTkLabel(
            container,
            text="Buy Lifetime License — $19  →  opens in your browser",
            font=FONTS["small"],
            text_color=COLORS["accent"],
            cursor="hand2",
        )
        buy_link.grid(row=8, column=0, pady=(PADDING["md"], 0))
        buy_link.bind("<Button-1>", lambda _e: self._open_buy_page())

    def _start_trial(self) -> None:
        status = trial_status()

        # Trial already used up? Refuse to enter.
        if status["state"] == "expired":
            from tkinter import messagebox
            messagebox.showerror(
                "FileSieve",
                "Your free trial has ended.\n\n"
                "Please purchase a license to continue using FileSieve.",
            )
            return

        # Fresh trial — record the start time and enter
        start_trial()
        self._on_activated()

    def _show_license_dialog(self) -> None:
        dialog = _LicenseDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self._on_activated()

    def _open_buy_page(self) -> None:
        import webbrowser
        webbrowser.open("https://gumroad.com/l/your-product-permalink")


class _LicenseDialog(ctk.CTkToplevel):
    """Modal dialog to paste a Gumroad license key."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.result = False

        self.title("Activate FileSieve")
        self.geometry("480x260")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg"])
        self.transient(master.winfo_toplevel())
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Enter your Gumroad License Key",
            font=FONTS["heading"],
            text_color=COLORS["text"],
        ).pack(pady=(PADDING["lg"], PADDING["sm"]))

        ctk.CTkLabel(
            self,
            text="You'll find it in your purchase receipt email.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack()

        self._entry = ctk.CTkEntry(
            self,
            width=380,
            height=40,
            font=FONTS["body"],
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            placeholder_text="XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX",
        )
        self._entry.pack(pady=PADDING["lg"])
        self._entry.focus_set()

        self._status = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=COLORS["danger"],
        )
        self._status.pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=PADDING["md"])

        PrimaryButton(
            btn_row, text="Activate", width=140, command=self._activate
        ).pack(side="left", padx=(0, PADDING["sm"]))
        SecondaryButton(
            btn_row, text="Cancel", width=120, command=self.destroy
        ).pack(side="left")

    def _activate(self) -> None:
        key = self._entry.get().strip()
        if not key:
            self._status.configure(text="Please enter a license key.")
            return

        self._status.configure(text="Verifying…", text_color=COLORS["text_muted"])

        def worker():
            ok, msg = activate_license(key)
            self.after(0, lambda: self._handle_result(ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_result(self, ok: bool, msg: str) -> None:
        if ok:
            self.result = True
            self.destroy()
        else:
            self._status.configure(text=msg, text_color=COLORS["danger"])