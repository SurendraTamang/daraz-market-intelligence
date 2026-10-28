import os

from analyze import niches, score_rows
from brief import md_text, render, write_briefs
from tests.test_analyze import row


def test_render_labels_lifetime_only_and_links():
    n = niches(score_rows([row("a")]))[0]
    md = render(1, n, "2026-10-12", has_velocity=False)
    assert "no trend yet" in md
    assert "(https://www.daraz.com.np/a.html)" in md
    assert "## Your notes" in md
    assert "(notes/tea.md)" in md
    assert "- [ ] Sourcing cost" not in md


def test_md_text_handles_newline_pipe_brackets_and_none():
    assert md_text("foo\nbar") == "foo bar"
    assert md_text("a|b") == "a/b"
    assert md_text("[Non EQ]") == "(Non EQ)"
    assert md_text(None) == ""


def test_write_briefs_creates_notes_once_and_preserves_edits(tmp_path):
    out = str(tmp_path / "briefs")
    ns = niches(score_rows([row("a")]))

    write_briefs(out, ns, "2026-10-12", has_v=False, top=20, n_products=1)
    notes_path = os.path.join(out, "notes", "tea.md")
    assert os.path.exists(notes_path)
    assert "- [ ] Sourcing cost" in open(notes_path).read()

    with open(notes_path, "a") as f:
        f.write("\nMy hand-filled sourcing note.\n")

    write_briefs(out, ns, "2026-10-12", has_v=False, top=20, n_products=1)
    content = open(notes_path).read()
    assert "My hand-filled sourcing note." in content  # edit survives a rerun
