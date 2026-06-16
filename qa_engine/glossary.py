def load_glossary(path):
    """Load a source<TAB>target TSV. Returns {} when path is None/missing."""
    if not path:
        return {}
    table = {}
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            src, tgt = line.split("\t", 1)
            table[src.strip().lower()] = tgt.strip()
    return table


def lookup(table, source_text):
    return table.get(source_text.strip().lower())
