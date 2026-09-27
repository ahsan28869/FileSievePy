"""Main application window."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk

from filesieve.licensing import is_licensed, trial_status
from filesieve.core.locations import LocationMap, load_location_map, save_location_map
from filesieve.core.monitor import DirectoryMonitor
from filesieve.core.router import FileRouter, RouteResult
from filesieve.core.rules import RuleSet, default_rules
from filesieve.gui.theme import COLORS, FONTS, PADDING
from filesieve.gui.views.dashboard import DashboardView
from filesieve.gui.views.locations_view import LocationsView
from filesieve.gui.views.log_view import LogView
from filesieve.gui.views.rules_view import RulesView
from filesieve.gui.views.settings_view import SettingsView
from filesieve.utils.config import CONFIG_DIR, load_config, save_config
from filesieve.utils.journal import Journal
from filesieve.utils.logger import get_logger

logger = get_logger(__name__)

RULES_FILE = CONFIG_DIR / "rules.yaml"


class FileSieveApp(ctk.CTk):
    """Root application window."""

    def __init__(self, start_minimized: bool = False) -> None:
        super().__init__()

        # ── Basic window setup ── #
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLORS["bg"])

        # ── Tray state ── #
        self._start_minimized = start_minimized
        self._tray_icon = None
        self._tray_enabled = True

        # ── Intercept window close ── #
        # Instead of quitting when X is clicked, hide to tray.
        self.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)

        # ── State init ── #
        self._journal = Journal()
        self._monitor = DirectoryMonitor(self._handle_new_file)
        self._stats_lock = threading.Lock()
        self._stats: dict[str, int] = {"organized": 0, "errors": 0}
        self._ruleset: RuleSet = self._load_ruleset()
        self._location_map: LocationMap = load_location_map()

        # ── Licensing gate ── #
        if not self._require_license():
            # Activation page is showing. Still set up the tray so the
            # user can quit from there if the window ever gets hidden.
            self.after(500, self._setup_tray)
            return

        self._build_main_ui()

        # ── Post-build tray setup ── #
        # Schedule tray setup to run AFTER the window has drawn. If the
        # window isn't fully built, pystray can hang waiting for a
        # window handle that doesn't exist yet.
        self.after(500, self._setup_tray)

        # If auto-started with --minimized, hide the window right away.
        if start_minimized:
            self.after(200, self._hide_to_tray)

    # ------------------------------------------------------------------ #
    # Licensing
    # ------------------------------------------------------------------ #
    def _require_license(self) -> bool:
        """Return True if the app should be usable. Show activation page if not."""
        from filesieve.licensing import has_access

        if has_access():
            return True

        # Not licensed, not in trial — show the gate
        self._show_activation_gate()
        return False

    def _show_activation_gate(self) -> None:
        from filesieve.gui.views.activation_view import ActivationView

        self.title("FileSieve — Activate")
        self.geometry("720x560")
        self.minsize(720, 560)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        view = ActivationView(self, on_activated=self._on_activation_success)
        view.grid(row=0, column=0, sticky="nsew")

    def _on_activation_success(self) -> None:
        # Re-check the license — in case the user somehow got here
        # without a valid state.
        from filesieve.licensing import has_access
        if not has_access():
            return

        # Tear down the activation view
        for child in self.winfo_children():
            child.destroy()

        # Reset grid weights (they were configured for the activation layout)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Build the main UI
        self._build_main_ui()

    # ------------------------------------------------------------------ #
    # Main UI construction
    # ------------------------------------------------------------------ #
    def _build_main_ui(self) -> None:
        self.title("FileSieve — Intelligent File Organizer")
        self.geometry("1080x720")
        self.minsize(920, 620)
        self.configure(fg_color=COLORS["bg"])

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()

        # Show the dashboard by default
        self._show_view("dashboard")

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, fg_color=COLORS["surface"], width=220, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(10, weight=1)

        # Logo
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.grid(
            row=0, column=0, sticky="ew",
            padx=PADDING["md"], pady=(PADDING["lg"], PADDING["lg"]),
        )

        ctk.CTkLabel(
            logo_frame,
            text="FileSieve",
            font=("Segoe UI", 20, "bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            logo_frame,
            text="Organize. Automatically.",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w")

        # Navigation
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("dashboard", "Dashboard"),
            ("locations", "File Type Locations"),
            ("rules", "Rules"),
            ("log", "Activity Log"),
            ("settings", "Settings"),
        ]

        for idx, (key, label) in enumerate(nav_items, start=1):
            btn = ctk.CTkButton(
                sidebar,
                text=f"   {label}",
                anchor="w",
                height=42,
                corner_radius=8,
                font=FONTS["body"],
                fg_color="transparent",
                hover_color=COLORS["surface_alt"],
                text_color=COLORS["text"],
                command=lambda k=key: self._show_view(k),
            )
            btn.grid(row=idx, column=0, sticky="ew", padx=PADDING["sm"], pady=2)
            self._nav_buttons[key] = btn

        # Footer
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=11, column=0, sticky="ew", padx=PADDING["md"], pady=PADDING["md"])

        # Version label
        ctk.CTkLabel(
            footer,
            text="v1.0.0",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(anchor="w")

        # Trial status label (only if not licensed)
        try:
            if not is_licensed():
                status = trial_status()
                if status["state"] == "active":
                    ctk.CTkLabel(
                        footer,
                        text=f"Trial: {status['days_left']} day(s) left",
                        font=FONTS["small"],
                        text_color=COLORS["warning"],
                    ).pack(anchor="w", pady=(4, 0))
        except Exception:
            logger.exception("Could not read trial status")

    def _build_content(self) -> None:
        self._content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

        self._views: dict[str, ctk.CTkFrame] = {
            "dashboard": DashboardView(
                self._content,
                on_start=self._start_monitoring,
                on_stop=self._stop_monitoring,
                on_undo=self._undo_last_move,
                get_stats=self._get_stats,
            ),
            "locations": LocationsView(
                self._content,
                location_map_provider=lambda: self._location_map,
                on_locations_changed=self._save_locations,
            ),
            "rules": RulesView(
                self._content,
                ruleset_provider=lambda: self._ruleset,
                on_rules_changed=self._save_ruleset,
            ),
            "log": LogView(self._content),
            "settings": SettingsView(self._content),
        }

        for view in self._views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self._current_view = "dashboard"
        self._show_view("dashboard")

    def _show_view(self, key: str) -> None:
        view = self._views.get(key)
        if view is None:
            return
        view.tkraise()
        self._current_view = key

        for nav_key, btn in self._nav_buttons.items():
            if nav_key == key:
                btn.configure(fg_color=COLORS["surface_alt"], text_color=COLORS["accent"])
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["text"])

        if key == "rules":
            self._views["rules"].refresh()  # type: ignore[attr-defined]
        elif key == "dashboard":
            self._views["dashboard"].refresh_stats()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # Rules & Locations persistence
    # ------------------------------------------------------------------ #
    def _load_ruleset(self) -> RuleSet:
        import yaml

        if not RULES_FILE.exists():
            ruleset = default_rules()
            self._write_rules(ruleset)
            return ruleset

        try:
            with RULES_FILE.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            ruleset = RuleSet(**data)
        except Exception as exc:
            logger.error("Failed to load rules, using defaults: %s", exc)
            ruleset = default_rules()
            self._write_rules(ruleset)

        return ruleset

    def _write_rules(self, ruleset: RuleSet) -> None:
        import yaml

        try:
            with RULES_FILE.open("w", encoding="utf-8") as f:
                yaml.safe_dump(
                    ruleset.model_dump(),
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
        except OSError as exc:
            logger.error("Failed to save rules: %s", exc)

    def _save_ruleset(self) -> None:
        self._write_rules(self._ruleset)

    def _save_locations(self) -> None:
        save_location_map(self._location_map)
        self._refresh_ignore_roots()

    def _refresh_ignore_roots(self) -> None:
        config = load_config()
        roots: list[Path] = []
        out = config.get("output_directory", "")
        if out:
            p = Path(out).resolve(strict=False)
            if p != p.anchor and p != p.parent:
                roots.append(p)

        for entry in self._location_map.entries:
            if not entry.enabled:
                continue
            try:
                p = Path(entry.destination).resolve(strict=False)
            except OSError:
                continue
            if p == p.anchor or p == p.parent:
                logger.warning(
                    "Ignoring unsafe location destination for %s: %s",
                    entry.extension,
                    entry.destination,
                )
                continue
            roots.append(p)

        logger.info("Ignore roots: %s", [str(r) for r in roots])
        self._monitor.set_ignore_roots(roots)

    # ------------------------------------------------------------------ #
    # Monitoring control
    # ------------------------------------------------------------------ #
    def _start_monitoring(self) -> None:
        if self._monitor.is_running:
            logger.info("Start ignored: monitor already running")
            self._log("Monitor is already running.", "warning")
            return

        config = load_config()
        directories = [Path(d) for d in config.get("watched_directories", [])]
        recursive = bool(config.get("recursive", False))

        if not directories:
            self._log("Cannot start — no watched directories configured.", "error")
            self._views["dashboard"].set_running(False)  # type: ignore[attr-defined]
            return

        # Verify each directory actually exists before trying
        valid: list[Path] = []
        for d in directories:
            if d.exists() and d.is_dir():
                valid.append(d)
            else:
                self._log(f"Skipping missing folder: {d}", "warning")

        if not valid:
            self._log("Cannot start — none of the watched folders exist.", "error")
            self._views["dashboard"].set_running(False)  # type: ignore[attr-defined]
            return

        self._refresh_ignore_roots()
        self._monitor.start(valid, recursive=recursive)

        # Don't claim success yet — wait and verify.
        self.after(700, self._verify_monitor_started)

    def _verify_monitor_started(self) -> None:
        running = self._monitor.is_running
        healthy = self._monitor.is_healthy
        err = self._monitor.last_error

        if running and healthy:
            active = len([r for r in self._ruleset.rules if r.enabled])
            self._log(f"Monitoring started — {active} active rule(s).", "success")
            self._views["dashboard"].set_running(True)  # type: ignore[attr-defined]
            cfg = load_config()
            cfg["monitoring_enabled"] = True
            save_config(cfg)
        else:
            reason = err or "observer failed to start"
            self._log(f"Failed to start monitoring: {reason}", "error")
            self._views["dashboard"].set_running(False)  # type: ignore[attr-defined]
            cfg = load_config()
            cfg["monitoring_enabled"] = False
            save_config(cfg)

        self._update_tray_menu()

    def _stop_monitoring(self) -> None:
        self._monitor.stop()
        self._log("Monitoring stopped.", "warning")
        self._views["dashboard"].set_running(False)  # type: ignore[attr-defined]
        config = load_config()
        config["monitoring_enabled"] = False
        save_config(config)
        self._update_tray_menu()

    def _undo_last_move(self) -> None:
        """Move the most recently archived file back to its original folder."""
        if self._monitor.is_running:
            # Refuse while monitoring is active to avoid a move war.
            self._log(
                "Stop monitoring before using Undo (avoids a move loop).",
                "warning",
            )
            return

        try:
            result = self._journal.undo_last()
        except Exception as exc:
            logger.exception("Undo failed: %s", exc)
            self._log(f"Undo failed: {exc}", "error")
            return

        if result is None:
            self._log("Nothing to undo — journal is empty or state is ambiguous.", "warning")
            return

        restored_from, restored_to = result

        # Update the counters: this move is now effectively "undone".
        with self._stats_lock:
            if self._stats["organized"] > 0:
                self._stats["organized"] -= 1

        self._log(
            f"↩  Restored  {restored_to.name}  →  {restored_to.parent}",
            "success",
        )

        # Refresh the dashboard counters on the main thread.
        try:
            self.after(0, lambda: self._views["dashboard"].refresh_stats())  # type: ignore[attr-defined]
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # File handling
    # ------------------------------------------------------------------ #
    def _handle_new_file(self, path: Path) -> None:
        config = load_config()
        output = Path(config.get("output_directory", str(Path.home() / "FileSieve_Archive")))

        # Build a combined rule set: user type rules first (if enabled), then general rules.
        if self._location_map.route_by_type_first:
            type_rules = self._location_map.to_rules(base_priority=1000)
        else:
            type_rules = self._location_map.to_rules(base_priority=1)

        combined = RuleSet(rules=type_rules + list(self._ruleset.rules))

        router = FileRouter(combined, output, journal=self._journal)
        result: RouteResult = router.route(path)

        if result.success:
            with self._stats_lock:
                self._stats["organized"] += 1
            self._log(f"✓  {path.name}  →  {result.destination}  [{result.rule_name}]", "success")
        else:
            with self._stats_lock:
                self._stats["errors"] += 1
            self._log(f"✗  {path.name}  —  {result.error}", "error")

        try:
            self.after(0, lambda: self._views["dashboard"].refresh_stats())
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _log(self, message: str, level: str = "info") -> None:
        try:
            self.after(0, lambda: self._views["log"].log(message, level))  # type: ignore[attr-defined]
        except Exception:
            logger.info(message)

    def _get_stats(self) -> dict[str, Any]:
        config = load_config()
        with self._stats_lock:
            organized = self._stats["organized"]
            errors = self._stats["errors"]

        try:
            undoable = len(self._journal.last_completed(n=1))
        except Exception:
            undoable = 0

        try:
            enabled_rules = len([r for r in self._ruleset.rules if r.enabled])
        except Exception:
            enabled_rules = 0

        return {
            "organized": organized,
            "errors": errors,
            "watched": len(config.get("watched_directories", [])),
            "rules": enabled_rules,
            "undoable": undoable,
        }

    # ------------------------------------------------------------------ #
    # System tray
    # ------------------------------------------------------------------ #
    def _setup_tray(self) -> None:
        """Initialize and run the system tray icon in a separate thread."""
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            logger.warning("pystray or Pillow not installed; system tray disabled.")
            self._tray_enabled = False
            return

        # Try to load the real icon.ico; fall back to a simple blue square.
        image = None
        for candidate in [
            Path(__file__).resolve().parents[2] / "icon.ico",
            Path(sys.executable).parent / "icon.ico",
            Path(sys.executable).parent / "_internal" / "icon.ico",
        ]:
            try:
                if candidate.exists():
                    image = Image.open(candidate).convert("RGBA")
                    break
            except Exception as exc:
                logger.warning("Could not load tray icon from %s: %s", candidate, exc)

        if image is None:
            image = Image.new("RGB", (64, 64), color=(33, 33, 33))
            draw = ImageDraw.Draw(image)
            draw.rectangle([16, 16, 48, 48], fill=(30, 144, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Open FileSieve", self._on_tray_show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start Monitoring",
                self._on_tray_start,
                enabled=lambda item: not self._monitor.is_running,
            ),
            pystray.MenuItem(
                "Stop Monitoring",
                self._on_tray_stop,
                enabled=lambda item: self._monitor.is_running,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_tray_quit),
        )

        self._tray_icon = pystray.Icon("filesieve", image, "FileSieve", menu)

        # Run pystray in a background daemon thread so it doesn't block Tkinter
        threading.Thread(
            target=self._tray_icon.run,
            name="FileSieveTray",
            daemon=True,
        ).start()

        logger.info("System tray icon initialized")

    def _update_tray_menu(self) -> None:
        """Refresh the tray menu (labels and enabled states)."""
        if self._tray_icon is None:
            return
        try:
            self._tray_icon.update_menu()
        except Exception:
            pass

    # Tray callbacks run on a worker thread — marshal to Tk thread.

    def _on_tray_show(self, icon=None, item=None) -> None:
        try:
            self.after(0, self._show_from_tray)
        except Exception as exc:
            logger.error("Could not restore from tray: %s", exc)

    def _on_tray_start(self, icon=None, item=None) -> None:
        try:
            self.after(0, self._start_monitoring)
        except Exception as exc:
            logger.error("Tray start failed: %s", exc)

    def _on_tray_stop(self, icon=None, item=None) -> None:
        try:
            self.after(0, self._stop_monitoring)
        except Exception as exc:
            logger.error("Tray stop failed: %s", exc)

    def _on_tray_quit(self, icon=None, item=None) -> None:
        try:
            self.after(0, self._do_quit)
        except Exception:
            self._do_quit()

    # Actual UI operations — run on the Tk main thread.

    def _hide_to_tray(self) -> None:
        """Hide the main window. The app keeps running in the tray."""
        try:
            self.withdraw()
            logger.info("Window hidden to system tray")
        except Exception as exc:
            logger.error("Could not hide to tray: %s", exc)

    def _show_from_tray(self) -> None:
        """Restore the main window from the tray."""
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            logger.info("Window restored from tray")
        except Exception as exc:
            logger.error("Could not restore window: %s", exc)

    def _on_close_to_tray(self) -> None:
        """User clicked X — minimize to tray instead of quitting."""
        if self._tray_enabled and self._tray_icon is not None:
            self._hide_to_tray()
        else:
            self._do_quit()

    def _do_quit(self) -> None:
        """Safely shut down monitoring, stop tray icon, and destroy app."""
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

        self._tray_enabled = False

        try:
            self._monitor.stop()
        except Exception:
            pass

        try:
            self.destroy()
        except Exception:
            pass

    def _on_close(self) -> None:
        """Kept for backwards compatibility."""
        self._do_quit()