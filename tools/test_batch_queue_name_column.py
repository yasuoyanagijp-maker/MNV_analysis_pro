"""Queue filenames must be one per line, not a single wrapping row."""

from src.flet_ui.components.shared import batch_queue_name_column


def test_one_filename_per_line_not_joined_row():
    names = ["a.png", "b.png", "c.png", "d.png"]
    col = batch_queue_name_column(names, current_idx=1, heading="キュー")
    values = [c.value for c in col.controls]
    assert values[0] == "キュー"
    assert values[1:] == ["1. a.png", "2. b.png", "3. c.png", "4. d.png"]
    assert all(" · " not in v for v in values)
