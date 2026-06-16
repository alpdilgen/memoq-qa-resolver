# Official memoQ QA code meanings (from the memoQ docs "QA warnings" page).
# Fed to the AI so it understands each code regardless of UI language.
QA_CODE_DESCRIPTIONS = {
    "1001": "The translation contains extra tags that should be removed.",
    "1002": "Some tags are missing in the translation and must be added.",
    "2004": "Some required tags are missing in the translated text.",
    "2010": "Inline tags in the translation are not well-formed vs the source.",
    "2011": "An inline tag is missing from the translated text.",
    "2015": "There is an extra inline tag in the translation.",
    "2016": "The order of tags in the translation differs from the source.",
    "3020": "Source and translation end with different punctuation marks.",
    "3030": "The first letters of source and translation are capitalized differently.",
    "3040": "The translation is identical to the source.",
    "3061": "A number has a non-standard format for the target language.",
    "3062": "Numbers do not match between source and translation.",
    "3063": "A number from the source is missing in the translation.",
    "3064": "The translation contains an extra number not in the source.",
    "3067": "Strict number formats do not match between source and target.",
    "3068": "A number is formatted differently in source and translation.",
    "3077": "Quotation marks, apostrophes or brackets differ between source and translation.",
    "3078": "A punctuation mark seems incorrect for the target language.",
    "3079": "An incorrect sequence of punctuation marks.",
    "3085": "Repeated (duplicate) words detected in the translation.",
    "3086": "There is an extra quote/bracket punctuation mark.",
    "3087": "A quote/bracket is missing.",
    "3088": "A quote/bracket has no matching pair.",
    "3089": "Source and target quotes/brackets do not match.",
    "3091": "A termbase term is missing from the translation.",
    "3092": "The translation includes an extra term.",
    "3093": "A term is translated with a forbidden translation.",
    "3094": "A non-translatable element is missing from the translation.",
    "3095": "An extra non-translatable element is in the translation.",
    "3096": "The count of a non-translatable element differs from the source.",
    "3097": "A forbidden term was used; a different term should be used.",
    "3100": "Same source segment translated in two different ways (inconsistent).",
    "3101": "Two different source segments have the same translation (inconsistent).",
    "3120": "The translation contains a forbidden character.",
    "3131": "Bold/italic/underline formatting is missing in the translation.",
    "3132": "Extra bold/italic/underline formatting in the translation.",
    "3133": "Bold/italic/underline formatting differs from the source.",
}

# Codes safe to fix mechanically in bulk (no AI judgment needed).
# Only the tag-boundary / segment-edge codes that align_whitespace truly handles:
#   3110  – space at end of segment (edge)
#   3190  – missing space before tag
#   3191  – missing space after tag
#   3192  – extra space before tag
#   3193  – extra space after tag
# Codes removed from this set (need AI):
#   3050  – internal multiple spaces between words
#   3071–3076 – space missing/extra before/after punctuation sign
#   3194–3197 – non-breaking space issues
BULK_SUITABLE_CODES = {
    "3110",
    "3190",
    "3191",
    "3192",
    "3193",
}


def describe_code(code: str, problemname: str = "") -> str:
    """Official description for a code; fall back to the warning's problemname."""
    return QA_CODE_DESCRIPTIONS.get(code, problemname or f"QA code {code}")
