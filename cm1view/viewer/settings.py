"""Settings window (first-run setup and the ⚙ button) and the overwrite prompt."""

import html
import os

import panel as pn

from .. import config
from ..theme import CSS, DIALOG_DARK, GRID, PANEL, RAISED

OK, ERR = "#4ade80", "#f87171"


def _html(text="", **kw):
    return pn.pane.HTML(text, stylesheets=[CSS], **kw)


def _note(text, color=None):
    col = f' style="color:{color}"' if color else ""
    return f'<div class="cv-hint"{col}>{text}</div>'


class Settings:
    """`modal` edits the config file.  required=True is the first-run setup: it can't
    be closed until the settings are saved with a usable runs_root.  `on_saved()` is
    called after a save."""

    def __init__(self, run_path=None, on_saved=None):
        self.run_path, self.on_saved = run_path, on_saved
        self.required = False
        self.w, self.notes = {}, {}
        for k in config.KEYS:
            self.w[k.name] = self._widget(k)
            self.notes[k.name] = _html(margin=(0, 10, 6, 10))
            self.w[k.name].param.watch(lambda e, n=k.name: self._recheck(n), "value")
        self.title = _html()
        self.msg = _html(margin=(4, 10))
        self.save_btn = pn.widgets.Button(name="Save", button_type="primary", width=150)
        self.cancel_btn = pn.widgets.Button(name="Cancel", button_type="light",
                                            button_style="outline", width=90)
        self.reset_btn = pn.widgets.Button(
            name="Reset to defaults", button_type="light", button_style="outline",
            width=150, description="Fill the form with the built-in defaults (saved only "
                                   "when you press Save)")
        self.raw = pn.widgets.TextAreaInput(sizing_mode="stretch_width", height=420,
                                            stylesheets=[_MONO])
        self.raw_save = pn.widgets.Button(name="Save file", button_type="primary", width=120)
        self.raw_msg = _html(margin=(4, 10))

        def row(name):
            return pn.Column(self.w[name], self.notes[name], margin=0)

        others = [k.name for k in config.KEYS if not k.required and not k.advanced]
        adv = [k.name for k in config.KEYS if k.advanced]
        card = dict(collapsed=True, sizing_mode="stretch_width", header_background=RAISED,
                    active_header_background=RAISED, header_color="#d7dde8",
                    styles={"background": PANEL, "border": f"1px solid {GRID}"})
        self.more = pn.Card(*map(row, others), title="More settings", **card)
        self.adv = pn.Card(*map(row, adv), title="Advanced (server and performance)", **card)
        form = pn.Column(*[row(k.name) for k in config.KEYS if k.required], self.more,
                         self.adv, margin=0, sizing_mode="stretch_width")
        self.path_html = _html()
        raw = pn.Column(self.path_html, self.raw, pn.Row(self.raw_save), self.raw_msg,
                        margin=0, sizing_mode="stretch_width")
        self.tabs = pn.Tabs(("Settings", form), ("Config file", raw), dynamic=False,
                            sizing_mode="stretch_width")
        # kept in view at the bottom of the window while the form scrolls
        self.buttons = pn.Row(self.save_btn, self.cancel_btn, pn.Spacer(), self.reset_btn,
                              sizing_mode="stretch_width", styles={
                                  "position": "sticky", "bottom": "-20px", "z-index": "5",
                                  "background": PANEL, "padding": "8px 0 20px 0",
                                  "border-top": f"1px solid {GRID}"})
        self.modal = pn.Modal(self.title, self.tabs, self.msg, self.buttons, width=720,
                              margin=10, stylesheets=[DIALOG_DARK, _SCROLL])
        self.save_btn.on_click(self._save)
        self.cancel_btn.on_click(lambda e: self.modal.hide())
        self.reset_btn.on_click(self._reset)
        self.raw_save.on_click(self._save_raw)
        self.tabs.param.watch(self._on_tab, "active")

    # ------------------------------------------------------------ widgets
    @staticmethod
    def _widget(k):
        if k.kind in ("dirs", "list"):
            hint = "one folder per line" if k.kind == "dirs" else "one per line"
            return pn.widgets.TextAreaInput(name=f"{k.label} ({hint})", height=72 if
                                            k.kind == "dirs" else 96,
                                            sizing_mode="stretch_width")
        if k.kind == "bool":
            return pn.widgets.Checkbox(name=k.label, margin=(10, 10, 4, 10))
        return pn.widgets.TextInput(name=k.label, sizing_mode="stretch_width",
                                    placeholder="auto" if k.kind.startswith("auto") else "")

    def _set(self, name, v):
        k = config.BY_NAME[name]
        if k.kind in ("dirs", "list"):
            v = "\n".join(v)
        elif k.kind != "bool":
            v = "" if v is None else str(v)
        self.w[name].value = v

    def _value(self, name):
        k, v = config.BY_NAME[name], self.w[name].value
        if k.kind in ("dirs", "list"):
            return [s.strip() for s in (v or "").splitlines() if s.strip()]
        if k.kind == "bool":
            return bool(v)
        v = (v or "").strip()
        if k.kind in ("auto_float", "auto_int"):
            return v or "auto"
        return v

    # ------------------------------------------------------------ open
    def show(self, required=False, flagged=None):
        """Open the window; `flagged` = {name: message} of settings that need fixing."""
        self.required = required
        vals = config.suggestions(self.run_path) if not config.exists() else \
            {k.name: config.file_value(k.name) for k in config.KEYS}
        for name, v in vals.items():
            self._set(name, v)
        for name in self.w:
            self._recheck(name)
        flagged = flagged or {}
        if flagged and any(n not in ("runs_root",) for n in flagged):
            self.more.collapsed = not any(not config.BY_NAME[n].advanced and n != "runs_root"
                                          for n in flagged)
            self.adv.collapsed = not any(config.BY_NAME[n].advanced for n in flagged)
        else:
            self.more.collapsed, self.adv.collapsed = required, True
        if required:
            first = not config.exists()
            self.title.object = (
                '<div class="cv-maptitle" style="font-size:18px"><b>Welcome to cm1view'
                '</b></div>' + _note(
                    "Tell cm1view where your CM1 runs live; everything else has a "
                    "default you can change now or later (⚙ in the top bar). Settings "
                    f"are saved in <code>{html.escape(config.config_path())}</code>.")
                if first else
                '<div class="cv-maptitle" style="font-size:18px"><b>cm1view settings need '
                'attention</b></div>' + _note(
                    html.escape(config.read_error()) or
                    "The folder where your runs live is missing or no longer exists."))
        else:
            self.title.object = ('<div class="cv-maptitle" style="font-size:18px"><b>'
                                 'Settings</b></div>' + _note(
                                     f"Saved in <code>{html.escape(config.config_path())}"
                                     "</code>. Paths apply to the next save; settings "
                                     "marked “restart” apply when cm1view starts again."))
            if flagged:
                self.title.object += _note("Some saved paths no longer work: fix the "
                                           "fields marked in red.", ERR)
        self.save_btn.name = "Save and continue" if required else "Save"
        self.cancel_btn.visible = not required
        self.modal.param.update(show_close_button=not required,
                                background_close=not required)
        self.msg.object = ""
        self.tabs.active = 0
        self.modal.show()

    # ------------------------------------------------------------ checks
    def _recheck(self, name):
        k = config.BY_NAME[name]
        try:
            v = self._value(name)
            err = config.check(name, v)
            if not err and k.kind in ("auto_float", "auto_int", "int") and v != "auto":
                float(v) if k.kind == "auto_float" else int(v)
        except ValueError:
            err = "Not a number (or auto)." if k.kind.startswith("auto") else "Not a number."
        parts = [html.escape(k.help)]
        src = config.source(name)
        if src.startswith(("command line", "environment")):
            parts.append(f"Currently set by the {src}, which wins over this file.")
        if name == "cache_gb":
            gb, how = config.cache_gb()
            parts.append(f"Running with {gb:.0f} GB" + (f" ({how})" if how != "set" else ""))
        elif name == "workers":
            n, how = config.workers()
            parts.append(f"Running with {n}" + (f" ({how})" if how != "set" else ""))
        if k.restart:
            parts.append("Applies on restart.")
        text = " ".join(parts)
        if err:
            self.notes[name].object = _note(html.escape(err), ERR) + _note(text)
        elif name == "runs_root" and v:
            runs, complete = config.scan_runs(v)
            n = f"{len(runs)}{'' if complete else '+'}"
            found = (_note(f"✓ found {n} run{'s' * (len(runs) != 1)}", OK) if runs else
                     _note("No CM1 output found under these folders (yet).", ERR))
            self.notes[name].object = found + _note(text)
        else:
            self.notes[name].object = _note(text)
        return err

    # ------------------------------------------------------------ save
    def _save(self, ev):
        errs = {n: e for n in self.w if (e := self._recheck(n))}
        if errs:
            names = ", ".join(config.BY_NAME[n].label for n in errs)
            self.msg.object = _note(f"Fix these first: {html.escape(names)}", ERR)
            if any(not config.BY_NAME[n].required and not config.BY_NAME[n].advanced
                   for n in errs):
                self.more.collapsed = False
            if any(config.BY_NAME[n].advanced for n in errs):
                self.adv.collapsed = False
            return
        try:
            config.save({n: self._value(n) for n in self.w})
        except (OSError, ValueError) as e:
            self.msg.object = _note(f"Could not save: {html.escape(str(e))}", ERR)
            return
        self._done()

    def _save_raw(self, ev):
        try:
            config.save_text(self.raw.value or "")
        except Exception as e:  # noqa: BLE001  (TOML errors, bad values, OSError)
            self.raw_msg.object = _note(f"Not saved: {html.escape(str(e))}", ERR)
            return
        self.raw_msg.object = _note("Saved.", OK)
        if self.required and config.needs_setup():
            self.raw_msg.object = _note("Saved, but runs_root is still missing or not a "
                                        "folder.", ERR)
            return
        self._done()

    def _done(self):
        self.modal.hide()
        self.required = False
        if self.on_saved:
            self.on_saved()

    def _reset(self, ev):
        for k in config.KEYS:
            if not k.required:
                self._set(k.name, list(k.default) if isinstance(k.default, list)
                          else k.default)
        self.msg.object = _note("Defaults filled in: press Save to keep them.")

    def _on_tab(self, ev):
        if ev.new == 1:
            self.path_html.object = _note(
                f"<code>{html.escape(config.config_path())}</code>"
                + ("" if config.exists() else " (not written yet: this is what Save "
                                              "would write)"))
            self.raw.value = config.file_text()
            self.raw_msg.object = ""
        self.buttons.visible = ev.new == 0


class ConfirmOverwrite:
    """ask(paths, then): runs then() at once when none of the files exists, else after
    the user agrees in a dialog."""

    def __init__(self):
        self.text = _html()
        self.yes = pn.widgets.Button(name="Overwrite", button_type="danger", width=120)
        self.no = pn.widgets.Button(name="Cancel", button_type="light",
                                    button_style="outline", width=90)
        self.modal = pn.Modal(self.text, pn.Row(self.yes, self.no), width=560, margin=10,
                              stylesheets=[DIALOG_DARK])
        self._then = None
        self.yes.on_click(self._yes)
        self.no.on_click(lambda e: self.modal.hide())

    def ask(self, paths, then):
        there = [p for p in paths if os.path.exists(p)]
        if not there:
            then()
            return
        self._then = then
        files = "".join(f"<li><code>{html.escape(p)}</code></li>" for p in there)
        self.text.object = ('<div class="cv-maptitle" style="font-size:16px"><b>Replace '
                            f'existing file{"s" * (len(there) > 1)}?</b></div>'
                            f'<ul class="cv-hint" style="margin:8px 0">{files}</ul>')
        self.modal.show()

    def _yes(self, ev):
        self.modal.hide()
        then, self._then = self._then, None
        if then:
            then()


_MONO = ":host textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; " \
        "font-size: 12px; }"
_SCROLL = ".dialog-content { max-height: 90vh; overflow-y: auto; }"
