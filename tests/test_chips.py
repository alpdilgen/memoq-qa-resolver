from qa_engine.tags import to_chips

PH = '<ph id="2">&lt;x id="63" mmq78catalogvalue="&amp;lt;cf size=9.5&amp;gt;" /&gt;</ph>'
STRONG = '<x id="34" mmq78catalogvalue="&lt;/strong&gt;" />'


def test_chips_from_raw_tag_xml():
    assert to_chips(f"A{PH}B") == "A[<cf size=9.5>]B"
    assert to_chips(f"A{STRONG}B") == "A[</strong>]B"


def test_chips_from_token_form():
    assert to_chips("A⟦1:<cf size=9.5>⟧B") == "A[<cf size=9.5>]B"
    assert to_chips("X⟦2:</li>⟧Y") == "X[</li>]Y"


def test_chips_plain_text_unchanged():
    assert to_chips("just text, no tags") == "just text, no tags"
