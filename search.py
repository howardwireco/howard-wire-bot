"""
Keyword search over the Shopify-sourced product catalog.
Returns relevant products to include in the Claude system prompt.
"""
import json, re, os

_catalog = None

def _load():
    global _catalog
    if _catalog is None:
        path = os.path.join(os.path.dirname(__file__), "catalog.json")
        with open(path) as f:
            _catalog = json.load(f)
    return _catalog

# ── Alias maps ────────────────────────────────────────────────────────────────

MATERIAL_ALIASES = {
    "stainless":        ["304 Stainless Steel", "316 Stainless Steel"],
    "stainless steel":  ["304 Stainless Steel", "316 Stainless Steel"],
    "ss":               ["304 Stainless Steel", "316 Stainless Steel"],
    "304":              ["304 Stainless Steel"],
    "316":              ["316 Stainless Steel"],
    "galvanized":       ["Galvanized Steel"],
    "galv":             ["Galvanized Steel"],
    "plain steel":      ["Plain Steel"],
    "plainsteel":       ["Plain Steel"],
    "steel":            ["Plain Steel", "304 Stainless Steel", "316 Stainless Steel", "Galvanized Steel"],
    "aluminum":         ["Aluminum", "Bright Aluminum", "Charcoal Aluminum"],
    "aluminium":        ["Aluminum"],
    "alum":             ["Aluminum"],
    "copper":           ["Copper"],
    "brass":            ["Brass"],
    "bronze":           ["Bronze"],
    "monel":            ["Monel"],
    "nickel":           ["Nickel", "Nichrome"],
    "pvc":              ["PVC Black", "Epoxy Black"],
    "fiberglass":       ["Grey Fiberglass", "Charcoal Fiberglass"],
    "hardware cloth":   ["Hdwr Cloth"],
    "hardware":         ["Hdwr Cloth"],
}

TYPE_ALIASES = {
    "woven":        "Woven Wire Mesh",
    "welded":       "Welded Wire Mesh",
    "perforated":   "Perforated Sheet",
    "perf":         "Perforated Sheet",
    "expanded":     "Expanded Metal",
    "insect":       "Insect Screen",
    "screen":       "Insect Screen",
    "dutch":        "Dutch Weave Mesh",
    "twill":        "Twilled Wire Mesh",
    "twilled":      "Twilled Wire Mesh",
    "hardware cloth": "Hardware Cloth",
    "wire":         "Wire",
}

# Fraction → decimal/string equivalents for matching
FRAC_MAP = {
    "1/16": ["1/16", ".0625", "0625"],
    "1/8":  ["1/8",  ".125",  "125"],
    "3/16": ["3/16", ".1875", "1875"],
    "1/4":  ["1/4",  ".25",   "250"],
    "5/16": ["5/16", ".3125", "3125"],
    "3/8":  ["3/8",  ".375",  "375"],
    "7/16": ["7/16", ".4375", "4375"],
    "1/2":  ["1/2",  ".5",    "500"],
    "5/8":  ["5/8",  ".625",  "625"],
    "3/4":  ["3/4",  ".75",   "750"],
    "7/8":  ["7/8",  ".875",  "875"],
    "1":    ["1\"",  "1.0"],
    "1-1/4":["1-1/4","1.25"],
    "1-1/2":["1-1/2","1.5"],
    "2":    ["2\"",  "2.0"],
    "3":    ["3\"",  "3.0"],
    "4":    ["4\"",  "4.0"],
}

def _extract_sizes(text):
    fractions = re.findall(r'\d+-?\d*/\d+', text)
    decimals  = re.findall(r'\.\d+', text)
    mesh_nums = re.findall(r'(\d+)\s*mesh', text, re.IGNORECASE)
    return fractions + decimals + mesh_nums

def search(query: str, max_results: int = 40) -> list[dict]:
    catalog   = _load()
    ql        = query.lower()

    # Resolve material filters
    mat_filters = []
    for alias, mats in MATERIAL_ALIASES.items():
        if alias in ql:
            mat_filters.extend(m.lower() for m in mats)

    # Resolve product type filters
    type_filter = None
    for alias, ptype in TYPE_ALIASES.items():
        if alias in ql:
            type_filter = ptype.lower()
            break

    # Size terms
    sizes = _extract_sizes(ql)
    expanded_sizes = list(sizes)
    for s in sizes:
        if s in FRAC_MAP:
            expanded_sizes.extend(FRAC_MAP[s])

    def score(item):
        # Build a single searchable string from all fields
        combo = " ".join([
            item.get("title", ""),
            item.get("material", ""),
            item.get("product_type", ""),
            item.get("spec", ""),
            item.get("part_num", ""),
            item.get("mesh_opening", ""),
            item.get("wire_dia", ""),
            item.get("description", ""),
        ]).lower()

        pts = 0

        # Exact material match
        for m in mat_filters:
            if m in combo:
                pts += 4

        # Product type match
        if type_filter and type_filter in combo:
            pts += 3

        # Size match
        for sz in expanded_sizes:
            if sz.lower() in combo:
                pts += 2

        # General keyword match
        for word in re.findall(r'\w+', ql):
            if len(word) > 2 and word in combo:
                pts += 1

        return pts

    scored = [(score(item), item) for item in catalog]
    scored.sort(key=lambda x: -x[0])

    results = [item for pts, item in scored if pts > 0][:max_results]

    # Fallback: return a broad sample
    if not results:
        results = catalog[:max_results]

    return results

def format_for_prompt(results: list[dict]) -> str:
    seen  = set()
    lines = []
    for item in results:
        key = item["title"]
        if key in seen:
            continue
        seen.add(key)
        extras = []
        if item.get("part_num"):
            extras.append("SKU " + item["part_num"])
        if item.get("sizes"):
            extras.append("widths: " + item["sizes"])
        tail = ("  —  " + " · ".join(extras)) if extras else ""
        url_note = f"  →  {item['url']}" if item.get("url") else ""
        lines.append(f"• {item['title']}{tail}{url_note}")
    return "\n".join(lines)
