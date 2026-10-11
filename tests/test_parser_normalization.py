from study_tracker.parser import parse


def test_strip_averages_indentation_blank_lines_and_tabs():
    text = """
          2026.10.04    10:00:00.00   ~   --:--:--

          -----

          [物理]

              リードα    <波動>  ,   p ( 21-42, 45 )

                  <熱力学>   , section( 2-4 )

    """
    rows = parse(text)

    assert len(rows) == 2
    assert rows[0].subject == "物理"
    assert rows[0].material == "リードα"
    assert rows[0].position == "波動"
    assert rows[0].unit == "p"
    assert rows[0].scope == "21-42,45"

    assert rows[1].subject == "物理"
    assert rows[1].material == "リードα"
    assert rows[1].position == "熱力学"
    assert rows[1].unit == "section"
    assert rows[1].scope == "2-4"


def test_crlf_cr_tabs_and_fullwidth_spaces_are_normalized():
    text = (
        "  2026.10.04\t10:00:00.00 ~ --:--:--  \r\n"
        "  -----\r\n"
        "\r\n"
        "  [物理]\r\n"
        "\tリードα　 <波動>\t,\tp(1-5)\r\n"
    )
    rows = parse(text)

    assert len(rows) == 1
    assert rows[0].subject == "物理"
    assert rows[0].material == "リードα"
    assert rows[0].position == "波動"
    assert rows[0].unit == "p"
    assert rows[0].scope == "1-5"


def test_blank_lines_between_context_and_content_do_not_break_inheritance():
    text = """2026.10.04 10:00:00.00 ~ --:--:--
-----

[物理]

リードα<波動>,p(21-42,45)

<熱力学>,section(2-4)

"""
    rows = parse(text)
    assert len(rows) == 2
    assert rows[1].material == "リードα"
    assert rows[1].position == "熱力学"


def test_note_block_is_normalized_independently():
    text = """2026.10.04 10:00:00.00 ~ --:--:--
-----
[数学]
青チャート<二次関数>,p(1-10)

/*
    備考1

    \t備考2\t
*/
"""
    rows = parse(text)
    assert rows[0].notes == ["備考1\n備考2"]
