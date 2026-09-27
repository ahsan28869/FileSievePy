"""FileSieve entry point with single-instance guard and crash recovery."""

from __future__ import annotations

import sys
import traceback


def main() -> int:
    minimized = "--minimized" in sys.argv
    ...
    app = FileSieveApp(start_minimized=minimized)
    app.mainloop()
    
    # Single-instance check happens before Tk initializes
    from filesieve.utils.single_instance import SingleInstance

    guard = SingleInstance()
    if not guard.acquire():
        print("FileSieve is already running.", file=sys.stderr)
        # On Windows, try to show a message box informing the user
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0, "FileSieve is already running.", "FileSieve", 0x40
                )
            except Exception:
                pass
        return 1

    try:
        # Reconcile journaled moves that were interrupted
        try:
            from filesieve.utils.journal import Journal

            Journal().reconcile_on_startup()
        except Exception:
            traceback.print_exc()

        from filesieve.gui.app import FileSieveApp
    except ImportError as exc:
        print(f"Failed to import FileSieve: {exc}", file=sys.stderr)
        print("Run: pip install -r requirements.txt", file=sys.stderr)
        guard.release()
        return 1

    try:
        app = FileSieveApp()
        app.mainloop()
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        guard.release()

    return 0


if __name__ == "__main__":
    sys.exit(main())