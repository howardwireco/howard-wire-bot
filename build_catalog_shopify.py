"""
Pulls the live product catalog from the Howard Wire Shopify store and rebuilds
catalog.json for Meshy. Parses the CURRENT spec-first titles (segments joined by
" – "), e.g.  '20 Mesh – .009" Wire Diameter – 304 Stainless Steel Woven Wire – 48" Wide'.

Run: python3 build_catalog_shopify.py
"""
import urllib.request, json, re, os, collections

STORE = "https://howardwire.com"

# Shopify product_type -> the canonical name search.py's aliases expect.
TYPE_MAP = {
    "Woven": "Woven Wire Mesh", "Welded": "Welded Wire Mesh",
    "Perforated": "Perforated Sheet", "Expanded": "Expanded Metal",
    "Wire": "Wire", "Insect": "Insect Screen", "Hardware Cloth": "Hardware Cloth",
}
# material patterns (most specific first) -> canonical material string
MATERIALS = [
    (r"316L Stainless Steel|Stainless Steel Type 316L|316L SS", "316L Stainless Steel"),
    (r"304L Stainless Steel|Stainless Steel Type 304L|304L SS", "304L Stainless Steel"),
    (r"316 Stainless Steel|Stainless Steel Type 316|316 SS",    "316 Stainless Steel"),
    (r"304 Stainless Steel|Stainless Steel Type 304|304 SS",    "304 Stainless Steel"),
    (r"Titanium",           "Titanium"),
    (r"Galvanized",         "Galvanized Steel"),
    (r"Bright Aluminum",    "Bright Aluminum"),
    (r"Charcoal Aluminum",  "Charcoal Aluminum"),
    (r"Aluminum",           "Aluminum"),
    (r"Grey Fiberglass",    "Grey Fiberglass"),
    (r"Charcoal Fiberglass","Charcoal Fiberglass"),
    (r"PVC Black",          "PVC Black"),
    (r"Epoxy Black",        "Epoxy Black"),
    (r"Corten|Weathering",  "Corten Steel"),
    (r"Nichrome",           "Nichrome"),
    (r"Monel",              "Monel"),
    (r"Nickel",             "Nickel"),
    (r"Brass",              "Brass"),
    (r"Bronze",             "Bronze"),
    (r"Copper",             "Copper"),
    (r"Plain Steel",        "Plain Steel"),
    (r"Stainless Steel|\bSS\b", "Stainless Steel"),   # generic fallback (ungraded)
]

def fetch_all_products():
    products, page = [], 1
    while True:
        url = f"{STORE}/products.json?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "HowardWireBot/1.0"})
        with urllib.request.urlopen(req) as r:
            batch = json.loads(r.read()).get("products", [])
        if not batch:
            break
        products.extend(batch)
        print(f"  page {page}: {len(batch)}")
        page += 1
    return products

def material_of(title):
    for pat, canon in MATERIALS:
        if re.search(pat, title, re.IGNORECASE):
            return canon
    return ""

def type_of(title, shopify_type):
    if re.search(r"Dutch Weave", title, re.IGNORECASE):
        return "Dutch Weave Mesh"
    if re.search(r"Twill", title, re.IGNORECASE):
        return "Twilled Wire Mesh"
    if re.search(r"Hardware Cloth", title, re.IGNORECASE):
        return "Hardware Cloth"
    if re.search(r"Insect Screen", title, re.IGNORECASE):
        return "Insect Screen"
    if re.search(r"Decorative", title, re.IGNORECASE):
        return "Decorative Perforated"
    return TYPE_MAP.get(shopify_type, shopify_type)

def spec_of(title):
    """Everything before the material+construction segment = the spec (mesh/opening/wire/thickness)."""
    segs = [s.strip() for s in title.split(" – ")]
    for i, s in enumerate(segs):
        if material_of(s):
            return " · ".join(segs[:i])
    return " · ".join(segs[:-1]) if len(segs) > 1 else ""

def build():
    print("Fetching live products from Shopify...")
    raw = fetch_all_products()
    print(f"total: {len(raw)}")

    items = []
    for p in raw:
        title  = (p.get("title") or "").strip()
        handle = (p.get("handle") or "").strip()
        body   = re.sub(r"<[^>]+>", " ", p.get("body_html") or "").strip()
        body   = re.sub(r"\s+", " ", body)
        variants = p.get("variants") or []
        skus  = [(v.get("sku") or "").strip() for v in variants if v.get("sku")]
        sizes = [(v.get("title") or "").strip() for v in variants
                 if v.get("title") and v["title"] != "Default Title"]

        material = material_of(title)
        ptype    = type_of(title, p.get("product_type", ""))
        spec     = spec_of(title)
        mesh  = re.search(r'(\d+(?:\s?x\s?\d+)?)\s*Mesh', title)
        openg = re.search(r'([\d./]+)"?\s*(?:Square Hole|Hole|Opening)', title)
        wire  = re.search(r'([\d.]+)"\s*Wire', title)

        desc = body
        if sizes:
            desc += "  Available sizes: " + ", ".join(sizes) + "."
        desc += "  Quote-only — cut to size on request."

        items.append({
            "title":        title,
            "handle":       handle,
            "url":          f"{STORE}/products/{handle}",
            "material":     material,
            "product_type": ptype,
            "spec":         spec,
            "part_num":     " / ".join(skus),
            "mesh_opening": (mesh.group(0) if mesh else (openg.group(0) if openg else "")),
            "wire_dia":     (wire.group(1) + '"' if wire else ""),
            "sizes":        " / ".join(sizes),
            "description":  desc[:400],
        })

    out = os.path.join(os.path.dirname(__file__), "catalog.json")
    json.dump(items, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"\ncatalog rebuilt: {len(items)} products -> {out}")
    print("\nby type:")
    for t, n in collections.Counter(i["product_type"] for i in items).most_common():
        print(f"  {n:4d}  {t}")
    print("\nby material:")
    for m, n in collections.Counter(i["material"] for i in items).most_common():
        print(f"  {n:4d}  {m or '(none)'}")
    miss = [i["title"] for i in items if not i["material"]]
    if miss:
        print(f"\n{len(miss)} with no material parsed (sample):")
        for t in miss[:12]:
            print("   ", t)

if __name__ == "__main__":
    build()
