from lxml import etree
from xml.sax.saxutils import escape as _xml_escape
from .models import Member, Issue
from .tags import tokenize

_XLIFF = "urn:oasis:names:tc:xliff:document:1.2"
_MQ = "MQXliff"
_NS = {"x": _XLIFF, "mq": _MQ}


def _inner_xml(elem) -> str:
    """Serialize an element's inner content (text + child tags), no outer tag.

    Uses ``with_tail=False`` so that ``etree.tostring`` does not include the
    child's trailing text, which we then append manually — avoiding the tail
    being emitted twice.  Namespace declarations injected by lxml when
    serializing a standalone child element are stripped so the fragments are
    byte-faithful to the original source.
    """
    if elem is None:
        return ""
    parts = [_xml_escape(elem.text or "")]
    for child in elem:
        frag = etree.tostring(child, encoding="unicode", with_tail=False)
        frag = frag.replace(' xmlns="urn:oasis:names:tc:xliff:document:1.2"', '')
        frag = frag.replace(' xmlns:mq="MQXliff"', '')
        frag = frag.replace(' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"', '')
        parts.append(frag)
        parts.append(_xml_escape(child.tail or ""))
    return "".join(parts)


def parse_mqxliff(path: str) -> list:
    tree = etree.parse(path)
    root = tree.getroot()
    members = []
    for tu in root.iter(f"{{{_XLIFF}}}trans-unit"):
        tu_id = tu.get("id")
        segguid = tu.get(f"{{{_MQ}}}segmentguid")
        status = tu.get(f"{{{_MQ}}}status", "")

        source_el = tu.find(f"{{{_XLIFF}}}source")
        target_el = tu.find(f"{{{_XLIFF}}}target")
        src_raw = _inner_xml(source_el)
        tgt_raw = _inner_xml(target_el)
        src_tok, src_map = tokenize(src_raw)
        tgt_tok, tgt_map = tokenize(tgt_raw)

        # best TM match target, if any
        tm = None
        im = tu.find(f"{{{_MQ}}}insertedmatch")
        if im is not None:
            im_tgt = im.find(f"{{{_XLIFF}}}target")
            if im_tgt is not None:
                tm = _inner_xml(im_tgt)

        warnings = []
        for ew in tu.iter(f"{{{_MQ}}}errorwarning"):
            pn = ew.get(f"{{{_MQ}}}errorwarning-problemname", "")
            args = ew.get(f"{{{_MQ}}}errorwarning-localizationargs", "")
            warnings.append((pn, args))

        members.append(Member(
            tu_id=tu_id, segmentguid=segguid,
            source_text=src_tok, target_text=tgt_tok,
            source_tags=src_map, target_tags=tgt_map,
            status=status, tm_match=tm, warning_keys=warnings,
        ))
    return members


def parse_languages(content: bytes):
    root = etree.fromstring(content)
    f = root.find(f"{{{_XLIFF}}}file")
    if f is None:
        return None, None
    return f.get("source-language"), f.get("target-language")


def parse_issues(content: bytes):
    """Return (issues, members_by_guid). One Issue per <mq:errorwarning>."""
    import tempfile, os
    # parse_mqxliff takes a path; write bytes to a temp file
    fd, path = tempfile.mkstemp(suffix=".mqxliff")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        members = parse_mqxliff(path)
    finally:
        os.unlink(path)
    by_guid = {m.segmentguid: m for m in members}

    root = etree.fromstring(content)
    issues = []
    for tu in root.iter(f"{{{_XLIFF}}}trans-unit"):
        guid = tu.get(f"{{{_MQ}}}segmentguid")
        tu_id = tu.get("id")
        for ew in tu.iter(f"{{{_MQ}}}errorwarning"):
            issues.append(Issue(
                code=ew.get(f"{{{_MQ}}}errorwarning-code", ""),
                problemname=ew.get(f"{{{_MQ}}}errorwarning-problemname", ""),
                args=ew.get(f"{{{_MQ}}}errorwarning-localizationargs", ""),
                segmentguid=guid, tu_id=tu_id,
            ))
    return issues, by_guid
