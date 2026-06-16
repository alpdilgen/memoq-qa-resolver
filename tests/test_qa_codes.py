from qa_engine.qa_codes import QA_CODE_DESCRIPTIONS, BULK_SUITABLE_CODES, describe_code


def test_known_descriptions():
    assert "3101" in QA_CODE_DESCRIPTIONS
    assert "translation" in QA_CODE_DESCRIPTIONS["3101"].lower()
    assert "3091" in QA_CODE_DESCRIPTIONS  # terminology


def test_bulk_suitable_is_whitespace_family():
    assert "3050" in BULK_SUITABLE_CODES and "3193" in BULK_SUITABLE_CODES
    assert "3101" not in BULK_SUITABLE_CODES  # judgment -> not bulk


def test_describe_code_falls_back_to_problemname():
    assert describe_code("99999", "some new problem") == "some new problem"
    assert describe_code("3101", "x") == QA_CODE_DESCRIPTIONS["3101"]
