from study_tracker.timestamps import assess_timestamp, parse_scope_ranges


def test_parse_numeric_scope_ranges():
    assert parse_scope_ranges("p(21-42,45)") == [(21, 42), (45, 45)]
    assert parse_scope_ranges("2-4, 7, 9-10") == [(2, 4), (7, 7), (9, 10)]


def test_timestamp_outside_planned_range_warns():
    result = assess_timestamp("43", "21-42,45", ["21", "30"])
    assert any("外" in warning for warning in result.warnings)
    assert result.completes_scope is False


def test_timestamp_in_previously_completed_prefix_warns():
    result = assess_timestamp("25", "21-42", ["21", "30"])
    assert any("実施済み" in warning for warning in result.warnings)


def test_duplicate_timestamp_warns():
    result = assess_timestamp("30", "21-42", ["21", "30"])
    assert any("既にタイムスタンプ" in warning for warning in result.warnings)


def test_final_planned_position_completes_scope():
    assert assess_timestamp("42", "21-42", ["21", "30"]).completes_scope is True
    assert assess_timestamp("42", "21-42,45", ["21", "30"]).completes_scope is False
    assert assess_timestamp("45", "21-42,45", ["21", "30"]).completes_scope is True


def test_non_numeric_scope_is_reported_as_unverifiable():
    result = assess_timestamp("3", "chapter-3", [])
    assert result.warnings
    assert result.completes_scope is False
