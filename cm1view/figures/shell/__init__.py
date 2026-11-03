"""The figure editor's new layout, on the figure document (spec/doc.py): a toolbar, a tree of
what the figure holds, the preview and an inspector of the one thing picked in the tree.
Where you click says what an edit reaches: a panel alone, or all panels of a kind.

Beside the old editor until every kind has moved here; shown when CM1VIEW_FIGURE_SHELL is set."""

from .frame import FigureShell

__all__ = ["FigureShell"]
