"""The table of figure-level settings (figures/settings.py) behind set_spec and collect."""

import pytest


def _shown(obj, into):
    """The ids of what is shown under obj (sections opened: they fill when first opened)."""
    if not getattr(obj, "visible", True):
        return
    into.add(id(obj))
    if getattr(obj, "collapsed", False):
        obj.collapsed = False
    for o in list(getattr(obj, "objects", None) or []):
        _shown(o, into)


def test_each_row_has_its_own_widget_and_key(ed):
    from cm1view.figures import settings
    rows = settings.SETTINGS
    assert len({r.key for r in rows}) == len(rows)
    assert len({r.widget for r in rows}) == len(rows)
    for r in rows:
        assert settings.widget_of(ed, r) is not None
        assert r.section and r.kinds


@pytest.mark.parametrize("attr", ["sk", "ds", "po", "jo", "ao", "to"])
def test_every_widget_of_a_kinds_block_is_in_the_table(ed, attr):
    from cm1view.figures import settings
    listed = {r.widget.split(".")[1] for r in settings.SETTINGS
              if r.widget.startswith(attr + ".")}
    assert listed == set(getattr(ed, attr))


def test_number_boxes_are_read_as_numbers(ed):
    """A number box left RAW would put a blank in the spec; a blank-able list would fail."""
    from cm1view.figures import settings
    from cm1view.viewer.numinput import FloatInput
    for r in settings.SETTINGS:
        boxed = isinstance(settings.widget_of(ed, r), FloatInput)
        assert not (boxed and r.as_ is settings.RAW), r.key
        assert boxed or r.as_ not in (settings.BLANKABLE, settings.SIZE), r.key


