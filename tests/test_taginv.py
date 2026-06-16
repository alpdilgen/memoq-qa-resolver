from qa_engine.taginv import (
    tag_multiset, no_foreign_tags, count_parity, tag_verdict_2016,
)

# tokenized segments use ⟦id:label⟧ tokens; the label is the tag "kind"
SRC = "⟦1:<cf size=9.5>⟧At a meeting ⟦2:</cf>⟧⟦3:<cf bold=True size=10>⟧MAXMOR⟦4:</cf>⟧"
# same tags, reordered for target word order (company name first)
TGT_REORDER = "⟦3:<cf bold=True size=10>⟧MAXMOR⟦4:</cf>⟧⟦1:<cf size=9.5>⟧bir toplantıda⟦2:</cf>⟧"
TGT_MISSING = "⟦3:<cf bold=True size=10>⟧MAXMOR⟦4:</cf>⟧bir toplantıda"  # dropped cf 9.5 pair
TGT_FOREIGN = SRC + "⟦9:<b>⟧extra⟦10:</b>⟧"  # introduces tags not in source


def test_multiset_keyed_by_label_kind():
    ms = tag_multiset(SRC)
    assert ms["<cf size=9.5>"] == 1
    assert ms["</cf>"] == 2
    assert ms["<cf bold=True size=10>"] == 1


def test_reorder_keeps_equal_multiset():
    assert tag_multiset(SRC) == tag_multiset(TGT_REORDER)
    assert count_parity(TGT_REORDER, SRC) is True


def test_missing_breaks_parity():
    assert count_parity(TGT_MISSING, SRC) is False


def test_no_foreign_tags():
    assert no_foreign_tags(TGT_REORDER, SRC) is True       # only source tags, counts ok
    assert no_foreign_tags(TGT_MISSING, SRC) is True        # fewer is fine for this check
    assert no_foreign_tags(TGT_FOREIGN, SRC) is False       # invents <b>/</b>


def test_2016_false_positive_when_equal():
    assert tag_verdict_2016(TGT_REORDER, SRC) is True       # all tags present, just reordered
    assert tag_verdict_2016(TGT_MISSING, SRC) is False
