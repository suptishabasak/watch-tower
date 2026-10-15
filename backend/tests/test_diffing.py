from app.diffing import (
    change_key,
    compare_text,
    fingerprint,
    normalize_text,
    relevant_changes,
    summarize,
)


def test_whitespace_and_blank_lines_are_ignored():
    a = normalize_text("Hello   world\n\n\n  Second line  \t")
    b = normalize_text("Hello world\nSecond line")
    assert a == b


def test_timestamps_and_relative_times_are_masked():
    a = normalize_text("Posted 5 minutes ago: Big news\nLast updated 2026-01-01 10:00:00")
    b = normalize_text("Posted 7 minutes ago: Big news\nLast updated 2026-01-01 10:05:00")
    assert fingerprint(a) == fingerprint(b)
    assert a[0] == "Posted : Big news"


def test_scores_with_colons_are_not_treated_as_clock_times():
    assert normalize_text("Final: 21:14") == ["Final: 21:14"]


def test_ad_labels_and_copyright_year_are_dropped():
    lines = normalize_text("Advertisement\nReal content\n© 2026 Acme Inc.\nSponsored")
    assert lines == ["Real content", "Acme Inc."]


def test_detects_added_removed_modified():
    old = ["Title", "Price: $10.00", "Old line"]
    new = ["Title", "Price: $12.00", "Brand new line about shipping"]
    result = compare_text(old, new)
    kinds = sorted(c.kind for c in result.changes)
    assert "modified" in kinds
    assert result.counts["modified"] == 1
    assert result.significant


def test_pure_insert_and_delete():
    result = compare_text(["a", "b"], ["a", "b", "c"])
    assert [c.kind for c in result.changes] == ["added"]
    result = compare_text(["a", "b", "c"], ["a", "c"])
    assert [c.kind for c in result.changes] == ["removed"]


def test_modified_line_has_word_segments():
    result = compare_text(["Price: $10.00 today"], ["Price: $12.00 today"])
    change = result.changes[0]
    assert change.kind == "modified"
    types = {s["type"] for s in change.segments}
    assert {"equal", "del", "add"} <= types
    assert "".join(s["text"] for s in change.segments if s["type"] != "add") == "Price: $10.00 today"
    assert "".join(s["text"] for s in change.segments if s["type"] != "del") == "Price: $12.00 today"


def test_dissimilar_lines_are_not_paired_as_modified():
    result = compare_text(["apple pie recipe"], ["quarterly earnings call"])
    assert sorted(c.kind for c in result.changes) == ["added", "removed"]


def test_identical_text_has_no_changes():
    result = compare_text(["a", "b"], ["a", "b"])
    assert not result.has_changes
    assert not result.significant


def test_focus_price_marks_only_price_lines_relevant():
    old = ["Shoe", "Price: $10.00", "Sizes: 7, 8"]
    new = ["Shoe", "Price: $9.00", "Sizes: 7, 8, 9 and more colours"]
    result = compare_text(old, new, focus="price")
    assert result.significant
    assert result.ignored == 1
    assert all("Price" in (c.after or "") for c in relevant_changes(result))


def test_focus_with_no_matching_change_is_not_significant():
    result = compare_text(["Price: $10.00", "Footer"], ["Price: $10.00", "Different footer text"], focus="price")
    assert not result.significant
    assert result.ignored >= 1


def test_focus_keywords_are_case_insensitive():
    result = compare_text(["x"], ["Registration is OPEN now"], focus="registration open")
    assert result.significant


def test_summary_is_concise_and_lists_counts():
    result = compare_text(["Price: $10.00", "gone"], ["Price: $12.00", "new1", "new2"])
    text = summarize(result)
    assert text.splitlines()[0].startswith("2 added") or "modified" in text.splitlines()[0]
    assert "$10.00" in text and "$12.00" in text


def test_change_key_is_directional():
    assert change_key("a", "b") != change_key("b", "a")
    assert change_key("a", "b") == change_key("a", "b")