"""Shared dark theme.  (Panel only for the Fast design, made when first asked for:
the colours alone, e.g. for figures rendered without the viewer, need no Panel.)"""

BG = "#0b0f17"
PANEL = "#111723"
RAISED = "#161d2b"
GRID = "#253045"
TEXT = "#d7dde8"
MUTED = "#7f8aa0"
ACCENT = "#22d3ee"
POINT_COLORS = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24"]
POINT_LABELS = ["1", "2", "3", "4"]

# dialogs in the dark theme (Panel's dialog box is white by default)
DIALOG_DARK = f"""
.dialog-content {{ background-color: {PANEL} !important; color: {TEXT};
  border: 1px solid {GRID}; border-radius: 12px; padding: 14px 16px 20px 16px;
  box-shadow: 0 18px 50px rgba(0,0,0,.55); }}
.dialog-overlay {{ background-color: rgba(5, 8, 14, 0.78) !important; }}
.pnx-dialog-close {{ color: {MUTED} !important; }}
.pnx-dialog-close:hover {{ color: {TEXT} !important; }}
"""

# Every widget's own stylesheet (Panel applies it inside each widget's shadow root):
# one button, input and checkbox style across the window.  Selectors sit in :where()
# so they carry no specificity: they beat Panel's / Fast's rules through !important,
# and a stylesheet set on a widget (the borderless toolbar pills) still beats them.
HOVER_LINE = "#3a4a66"
WIDGETS = f"""
:where(.bk-btn) {{
  background-color: rgba(148,163,184,.06) !important; border: 1px solid {GRID} !important;
  color: {TEXT} !important; box-shadow: none !important; }}
:where(.bk-btn:hover) {{
  background-color: rgba(148,163,184,.13) !important; border-color: {HOVER_LINE} !important; }}
:where(.bk-btn.bk-active) {{
  background-color: rgba(34,211,238,.18) !important; border-color: rgba(34,211,238,.5) !important;
  color: #a5f3fc !important; }}
:host(.solid) :where(.bk-btn.bk-btn-primary) {{
  background-color: {ACCENT} !important; border-color: {ACCENT} !important;
  color: #062830 !important; font-weight: 600; }}
:host(.solid) :where(.bk-btn.bk-btn-primary:hover) {{
  background-color: #67e8f9 !important; border-color: #67e8f9 !important; }}
:where(.bk-btn.bk-btn-danger) {{ color: #fca5a5 !important;
  border-color: rgba(248,113,113,.45) !important; }}
:where(.bk-btn.bk-btn-warning) {{ color: #fcd34d !important;
  border-color: rgba(251,191,36,.45) !important; }}
:where(.bk-btn[disabled], .bk-btn[disabled]:hover),
:host(.solid) :where(.bk-btn[disabled], .bk-btn[disabled]:hover) {{
  background-color: transparent !important; border-color: {GRID} !important;
  color: {MUTED} !important; opacity: .45 !important; cursor: not-allowed !important; }}

:where(.bk-input) {{
  background-color: #0d131e !important; border: 1px solid {GRID} !important;
  color: {TEXT} !important; box-shadow: none !important; }}
:where(.bk-input:hover) {{ border-color: {HOVER_LINE} !important; }}
:where(.bk-input:focus) {{ border-color: rgba(34,211,238,.7) !important;
  box-shadow: 0 0 0 2px rgba(34,211,238,.15) !important; outline: none !important; }}
:where(.bk-input[disabled]) {{ opacity: .45 !important; }}
:where(.choices__inner) {{ background-color: #0d131e !important;
  border: 1px solid {GRID} !important; border-radius: 4px !important; }}
:where(.choices__inner:hover) {{ border-color: {HOVER_LINE} !important; }}
:where(.bk-spin-btn.bk-spin-btn-up)::before {{ border-bottom-color: {MUTED} !important; }}
:where(.bk-spin-btn.bk-spin-btn-down)::before {{ border-top-color: {MUTED} !important; }}
:where(.bk-spin-btn.bk-spin-btn-up:hover)::before {{ border-bottom-color: {TEXT} !important; }}
:where(.bk-spin-btn.bk-spin-btn-down:hover)::before {{ border-top-color: {TEXT} !important; }}
:where(.bk-spin-btn) {{ opacity: .7; }}

:where(input[type=checkbox]) {{
  appearance: none !important; -webkit-appearance: none !important; width: 15px !important;
  height: 15px !important; margin: 0 6px 0 0 !important; flex: 0 0 auto;
  border: 1.5px solid #5b6880 !important; border-radius: 4px !important;
  background: transparent no-repeat center / 11px 11px !important;
  cursor: pointer; vertical-align: -3px; }}
:where(input[type=checkbox]:hover) {{ border-color: {TEXT} !important; }}
:where(input[type=checkbox]:checked) {{
  background-color: {ACCENT} !important; border-color: {ACCENT} !important;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path d='M2.5 6.2 5 8.6l4.6-5' fill='none' stroke='%23062830' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>") !important; }}
:where(input[type=checkbox]:checked)::before {{ content: none !important; }}
:where(input[type=checkbox]:disabled) {{ opacity: .4 !important; cursor: not-allowed; }}
:where(input[type=checkbox]:focus-visible) {{ outline: 2px solid rgba(34,211,238,.5); }}
"""

# Bokeh figures: no dotted focus ring around the whole plot after a click (the
# canvas draws it in --highlight-color, which a rule on its host here overrides)
FIGURE = """
.bk-Canvas { --highlight-color: transparent; }
"""
# a figure's toolbar: dark when it sits over the plot (toolbar_inner)
TOOLBAR = f"""
:host(.bk-inner) {{ background-color: rgba(17,23,35,0.88) !important; opacity: 1 !important;
  border-radius: 6px; }}
"""

CSS = f"""
:root {{
  --cv-bg: {BG}; --cv-panel: {PANEL}; --cv-raised: {RAISED}; --cv-grid: {GRID};
  --cv-text: {TEXT}; --cv-muted: {MUTED}; --cv-accent: {ACCENT};
}}
:root {{ color-scheme: dark; }}
* {{ scrollbar-color: {GRID} transparent; scrollbar-width: thin; }}
body, #main, .main {{ background: var(--cv-bg) !important; }}
#sidebar {{ background: var(--cv-panel) !important; border-right: 1px solid var(--cv-grid); }}
.cv-card {{
  background: var(--cv-panel); border: 1px solid var(--cv-grid); border-radius: 10px;
}}
.cv-h {{ font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
        color: var(--cv-muted); margin: 6px 0 2px 0; font-weight: 600; }}
.cv-run {{ font-size: 12px; color: var(--cv-muted); line-height: 1.5; }}
.cv-run b {{ color: var(--cv-text); font-weight: 600; }}
.cv-time {{ font: 600 22px/1.1 ui-monospace, SFMono-Regular, Menlo, monospace;
           color: var(--cv-text); }}
.cv-time small {{ font-size: 12px; color: var(--cv-muted); font-weight: 400; }}
.cv-hint {{ font-size: 12px; color: var(--cv-muted); }}
.cv-hint kbd {{ background: var(--cv-raised); border: 1px solid var(--cv-grid);
               border-radius: 4px; padding: 0 4px; font-size: 11px; color: var(--cv-text); }}
.cv-status {{ font-size: 12px; color: var(--cv-muted); }}
.cv-status .busy {{ color: var(--cv-accent); }}
.cv-maptitle {{ font-size: 13px; color: var(--cv-text); }}
.cv-maptitle span {{ color: var(--cv-muted); }}
.cv-empty {{ color: var(--cv-muted); font-size: 13px; padding: 40px 10px; text-align: center; }}
.ptabs {{ display: flex; flex-wrap: wrap; gap: 8px 28px; align-items: flex-start; }}
.ptab {{ border-collapse: collapse; flex: 1 1 340px; font-size: 12px; color: var(--cv-text); }}
.ptab th {{ text-align: right; font-weight: 600; padding: 4px 8px; color: var(--cv-text);
           border-bottom: 1px solid var(--cv-grid); white-space: nowrap; }}
.ptab td {{ padding: 2px 8px; text-align: right; font-variant-numeric: tabular-nums;
           font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: nowrap; }}
.ptab td.pn {{ text-align: left; font-family: inherit; color: var(--cv-muted); }}
.ptab td.u {{ text-align: left; color: var(--cv-muted); font-family: inherit; font-size: 11px; }}
.ptab td.hot {{ color: {ACCENT}; font-weight: 700; }}
.ptab tr.sec td {{ text-align: left; color: var(--cv-accent); font-family: inherit;
                  font-size: 11px; letter-spacing: .08em; text-transform: uppercase;
                  padding-top: 10px; border-bottom: 1px solid var(--cv-grid); }}
.ptab tbody tr:not(.sec):hover td {{ background: var(--cv-raised); }}
/* Bokeh hover tooltips (attached to the page body) in the dark theme */
.bk-Tooltip {{ --tooltip-color: {RAISED}; --tooltip-text: {TEXT};
  --tooltip-border: {GRID}; --tooltip-arrow-color: {GRID}; border-radius: 6px;
  box-shadow: 0 6px 18px rgba(0,0,0,.45); }}
.ptab .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%;
             margin-right: 6px; vertical-align: 0; }}
"""


def __getattr__(name):
    if name != "Fast":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from panel.theme import Inherit, fast
    from panel.widgets import Widget

    class Fast(fast.Fast):
        """The template's Fast design plus the shared widget styles.  (Named Fast: Panel
        finds a design's bundled files under the lower-cased class name.)"""

        modifiers = {Widget: {"stylesheets": [Inherit, WIDGETS]}}

    Fast.__qualname__ = "Fast"
    globals()["Fast"] = Fast
    return Fast
