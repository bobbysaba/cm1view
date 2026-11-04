"""The figure editor, on the figure document (spec/doc.py): a toolbar, a tree of
what the figure holds, the preview and an inspector of the one thing picked in the tree.
Where you click says what an edit reaches: a panel alone, or all panels of a kind."""

from .frame import FigureShell

__all__ = ["FigureShell"]
