"""Shared dark theme."""

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
.ptab .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%;
             margin-right: 6px; vertical-align: 0; }}
"""
