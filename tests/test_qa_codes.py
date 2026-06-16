from qa_engine.qa_codes import QA_CODE_DESCRIPTIONS, BULK_SUITABLE_CODES, describe_code


def test_known_descriptions():
    assert "3101" in QA_CODE_DESCRIPTIONS
    assert "translation" in QA_CODE_DESCRIPTIONS["3101"].lower()
    assert "3091" in QA_CODE_DESCRIPTIONS  # terminology


def test_bulk_suitable_is_only_tag_boundary_codes():
    # only the tag-boundary / edge codes align_whitespace truly handles
    assert BULK_SUITABLE_CODES == {"3110", "3190", "3191", "3192", "3193"}
    # sign-spacing, internal multi-space and nbsp are NOT bulk (need AI)
    for c in ("3050", "3073", "3075", "3194", "3196"):
        assert c not in BULK_SUITABLE_CODES
    assert "3101" not in BULK_SUITABLE_CODES


def test_describe_code_falls_back_to_problemname():
    assert describe_code("99999", "some new problem") == "some new problem"
    assert describe_code("3101", "x") == QA_CODE_DESCRIPTIONS["3101"]
