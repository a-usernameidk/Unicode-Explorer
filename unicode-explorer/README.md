# Unicode Explorer

A tray-resident, keyboard-driven picker for every named Unicode character.
Press the hotkey, type a few letters, hit Enter, paste.

## Quick start

**Windows:** run `setup.bat` once, then `run.bat`.
**macOS / Linux:** `python3 -m venv venv && venv/bin/pip install -r requirements.txt && ./run.sh`

Default hotkey is `Ctrl+Alt+U`. If the hotkey can't be registered (it needs
Administrator on Windows / root on Linux) the app still works — click the tray
icon instead.

Verify the engine without launching the GUI: `python tools/selftest.py`

## Keys

| Key | Action |
|---|---|
| `↑` `↓` `PgUp` `PgDn` | move through results (focus stays in the search box) |
| `Enter` | copy the character |
| `Ctrl+Enter` | copy the Python escape (`\u2713`) |
| `Ctrl+Shift+Enter` | copy the HTML entity (`&#x2713;`) |
| `Ctrl+D` | toggle favourite |
| `Esc` | hide |

## Settings

Click the **⚙** in the top-right of the window, or pick *Settings…* from the
tray menu.

**General** — rebind the global hotkey by clicking the field and pressing a
combination. At least one modifier is required; a bare key as a *global*
hotkey would hijack that key in every application. Also toggles whether the
window hides after you copy.

**Appearance** — six built-in palettes (Midnight, Nord, Dracula, Forest, Paper,
High Contrast) or edit any of the six colours yourself, which switches the
theme to *Custom*. Changes preview live. Text colour on selected rows is
derived from accent luminance, so a light accent doesn't end up unreadable.

**Advanced** — *Developer mode* is off by default and reveals **Project
tools**, containing *Export Package…*. Below that, *Uninstall…* clears saved
settings, favourites and recents, then removes the virtual environment, caches
and any auto-start entry.

### Export Package

Writes a clean archive to `dist/`. It prunes `venv/`, `.venv/`, `env/`,
`__pycache__/`, `.git/`, `.vscode/`, `.idea/`, `node_modules/`, previous
`dist/` output, and any loose `.zip`, `.pyc`, `.log` or `.db` files, then nests
everything under a single folder so unzipping doesn't scatter files. If the
project has no `.gitignore`, one is generated into the archive.

Verified: a tree of 16 files containing a 300 KB `venv/` exports as 6 files.

The old `tools/build_release.py` is gone. It matched `"/venv/"` as a plain
substring, so a top-level `venv/` could slip through, and it wrote the archive
*into* the directory it was walking, so a rebuild could swallow the previous
archive mid-walk.

## Uninstall

Nothing here deletes the project folder itself — a running process can't
reliably remove the directory it's executing from, especially on Windows. The
uninstaller reports the path and leaves it to you.

## Searching

- **By name** — `check mark`, `black star`, `rightwards arrow`
- **By nickname** — `tick`, `shrug`, `nbsp`, `zwj`, `lol`, `degrees`
- **By ASCII shorthand** — `->`, `!=`, `<=`, `...`, `+-`, `(c)`
- **By codepoint** — `U+2713`, `0x2713`, `\u2713`, `2713`
- **By the character itself** — paste `→` to identify it

## What changed from the previous version

The old build crashed on launch and, once patched past that, could only ever
show eight hardcoded characters.

**Bugs fixed**

1. `ui/window.py` imported `ClipboardEngine` from `core.` while the file lived
   in `ui/` — instant `ImportError` on startup.
2. The window called `ClipboardEngine.copy()`, which did not exist; the class
   only defined `inject_unicode()`. `AttributeError` on every copy.
3. `filter_symbols()` was `pass`, so the search box did nothing at all.
4. `requierements.txt` was misspelled.
5. Clipboard writes were broken four ways: UTF-16LE with no NUL terminator,
   "HTML Format" without the mandatory CF_HTML byte-offset header (so Word and
   browsers pasted garbage), `CF_TEXT` set to the *Python escape* so plain-text
   targets pasted `\u2713` instead of `✓`, and `OpenClipboard()` called outside
   the `try` block — any failure leaked the clipboard lock and froze copy/paste
   system-wide.
6. `silent_launcher.bat` hardcoded `C:\Users\liaml\...`, so it worked on
   exactly one machine.
7. `keyboard.add_hotkey(..., suppress=True)` swallowed the keystroke globally,
   breaking that shortcut in every other application.
8. A failure to register the hotkey was uncaught and killed the app at startup.
9. The hotkey callback touched Qt widgets directly from the keyboard library's
   background thread — a latent crash. It now goes through a signal.
10. `ui/styles.py` and `core/__init__.py` were empty; `core/database.py` was
    mock data that nothing imported.

**Improvements**

- **143,041 characters instead of 8.** No database file, no download: Python's
  stdlib `unicodedata` already embeds the full UCD. The index builds in ~0.4s.
- **Ranked fuzzy search** with synonyms, ASCII shorthand, codepoint lookup and
  reverse glyph lookup. Every query in the test suite resolves in under 25ms.
- **Cross-platform.** Dropping pywin32 for Qt's clipboard means it now runs on
  macOS and Linux, not just Windows.
- Index builds on a background thread, so the window opens instantly.
- Block filter, favourites and recents (persisted), detail bar showing
  codepoint / block / category / escapes / UTF-8 bytes.
- Combining marks and zero-width characters are drawn on a dotted circle so
  they're actually visible.
- Single-instance guard; frameless window is draggable; opens on whichever
  monitor the cursor is on.
- Four confusing `.bat` files (including one that ran `wmic ... call terminate`
  under a "NUCLEAR TERMINATION SEQUENCE" banner) replaced by `setup.bat`,
  `run.bat` / `run.sh`, and `run.bat debug` for logs. All use `%~dp0`, so the
  project folder can live anywhere.

## Layout

```
main.py                 tray icon, rebindable hotkey, single-instance guard
core/index.py           UCD index + ranked search  (the interesting part)
core/clipboard.py       cross-platform clipboard
core/settings.py        typed store over QSettings, with change signals
core/theme.py           palettes + stylesheet builder
core/packager.py        release packaging       (Qt-free)
core/uninstall.py       cleanup                 (Qt-free)
ui/window.py            picker window, delegate, keyboard handling
ui/settings_dialog.py   settings, hotkey capture, developer tools
tools/selftest.py       headless search + packaging tests
tools/checkmodules.py   static import-graph validation
```

`packager` and `uninstall` deliberately avoid importing Qt so they can be run
and tested headlessly.

## Checks

```
python tools/selftest.py       # search correctness + packaging exclusions
python tools/checkmodules.py   # missing imports and circular dependencies
```

`checkmodules.py` exists because of how v1 died: it imported `ClipboardEngine`
from `core.` while the class lived in `ui/`. That's a one-line mistake no
linter in the project would have caught, and it made the app unlaunchable.
