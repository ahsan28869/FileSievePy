# FileSieve

**FileSieve** is an intelligent, background file organizer for Windows, macOS, and Linux.
It watches selected directories and automatically sorts, renames, and routes new files
into structured `year/month` folder hierarchies based on MIME type, metadata, and
user-defined rules.

---

## Features

- 🔍 **Real-time monitoring** of one or more directories via `watchdog`
- 📁 **Rule-based routing** with priorities and MIME wildcards (e.g. `image/*`)
- 🧠 **Smart invoice detection** — routes PDFs containing "invoice"/"receipt" to Finance
- 🎨 **Modern dark GUI** built with `customtkinter`
- 📊 **Live dashboard** with stats and an activity log
- ⚙️ **YAML configuration** stored in `~/.filesieve/`
- 🪶 **No admin rights required** — uses standard user-space filesystem events

---

## Installation

```bash
# 1. (Recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt
```

> **Windows users:** `python-magic-bin` is installed automatically via the
> environment marker in `requirements.txt`. If you get an `ImportError`,
> run `pip install python-magic-bin` manually.

---

## Running

```bash
python main.py
```

1. Open the **Dashboard** and click **+ Add Folder** to add directories to watch.
2. Go to **Settings** and set your **Archive Destination**.
3. Click **▶ Start Monitoring** — new files will be sorted automatically.
4. Check **Rules** to see or toggle routing rules, or edit
   `~/.filesieve/rules.yaml` directly.

---

## Configuration

Configuration lives in `~/.filesieve/`:

| File | Purpose |
|------|---------|
| `config.yaml` | Watched directories, output path, recursive flag |
| `rules.yaml`  | Routing rules (priority-ordered) |
| `logs/filesieve.log` | Persistent log file |

### Example rule

```yaml
- name: Invoices
  enabled: true
  priority: 100
  mime_types: [application/pdf]
  name_contains: [invoice, receipt, bill]
  destination: Finance/Invoices/{year}/{month}
```

### Destination tokens

| Token | Example |
|-------|---------|
| `{year}`  | `2025` |
| `{month}` | `04` |
| `{day}`   | `17` |
| `{name}`  | `report` |
| `{ext}`   | `pdf` |
| `{date}`  | `2025-04-17` |

---

## Project layout

```
filesieve/
├── main.py
├── requirements.txt
├── config/default_rules.yaml
├── filesieve/
│   ├── core/      # router, monitor, rules, identifier
│   ├── gui/       # customtkinter UI
│   └── utils/     # config, logger, helpers
└── tests/
```

---

## License

MIT