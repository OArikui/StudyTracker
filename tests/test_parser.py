from study_tracker.parser import parse, render, is_time_placeholder


def test_partial_text_sync():
    text = """2026.10.04 15:10:00.00 ~ --:--:--
-----
[物理]
リードα<波動>
<熱力学>,section(2-4)
"""
    rows = parse(text)
    assert len(rows) == 2
    assert rows[0].subject == "物理"
    assert rows[0].material == "リードα"
    assert rows[0].position == "波動"
    assert rows[0].unit == ""
    assert rows[0].scope == ""
    assert rows[1].subject == "物理"
    assert rows[1].position == "熱力学"
    assert is_time_placeholder(rows[0].end)


def test_subject_only_and_placeholder():
    text = """2026.10.04 --:--:-- ~ --:--:--
-----
[物理]
"""
    rows = parse(text)
    assert len(rows) == 1
    assert rows[0].subject == "物理"
    assert rows[0].material == ""
    assert rows[0].start == "--:--:--"
    assert rows[0].end == "--:--:--"


def test_partial_roundtrip():
    text = """2026.10.04 10:00:00.00 ~ --:--:--
-----
[数学]
青チャート<二次関数>
"""
    rows = parse(text)
    rendered = render(rows)
    assert "--:--:--" in rendered
    rows2 = parse(rendered)
    assert rows2[0].subject == "数学"
    assert rows2[0].material == "青チャート"
    assert rows2[0].position == "二次関数"
