"""
Pulls the live product catalog from the Howard Wire Shopify store
and rebuilds catalog.json for the chatbot.

Run: python3 build_catalog_shopify.py
"""
import urllib.request, json, re, os

STORE = "https://howard-wire-cloth-co.myshopify.com"

def fetch_all_products():
    products = []
    page = 1
    while True:
        url = f"{STORE}/products.json?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "HowardWireBot/1.0"})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        print(f"  Page {page}: {len(batch)} products")
        page += 1
    return products

def parse_title(title):
    """
    Parse titles like:
      '304 Stainless Steel · Woven Wire Mesh · 4 Mesh · .035" Wire · KU4035N'
      '316 Stainless Steel · Wire · 1/4" Wire · RT1/4"-10\''
      'Plain Steel · Perforated Sheet · 3/8" Opening · EA3/8"SQ'
    """
    parts = [p.strip() for p in title.split("·")]
    material     = parts[0] if len(parts) > 0 else ""
    product_type = parts[1] if len(parts) > 1 else ""
    # Everything between product_type and the last part is spec
    spec         = " · ".join(parts[2:-1]) if len(parts) > 3 else (parts[2] if len(parts) > 2 else "")
    part_num     = parts[-1] if len(parts) > 2 else ""
    return material.strip(), product_type.strip(), spec.strip(), part_num.strip()

def extract_mesh_size(spec, title):
    """Extract mesh count or opening size from spec string."""
    # Mesh count: '4 Mesh', '100 Mesh'
    m = re.search(r'(\d+(?:×\d+)?)\s*[Mm]esh', spec or title)
    if m:
        return m.group(1) + " Mesh"
    # Opening size: '1/4" Opening', '.250" Opening'
    m = re.search(r'([\d./]+["\s]*(?:Opening|opening))', spec or title)
    if m:
        return m.group(1).strip()
    return spec

def extract_wire_dia(spec, title):
    """Extract wire diameter from spec."""
    m = re.search(r'([\d.]+)"\s*[Ww]ire', spec or title)
    if m:
        return m.group(1) + '"'
    return ""

def build():
    print("Fetching products from Shopify...")
    raw = fetch_all_products()
    print(f"Total products fetched: {len(raw)}")

    items = []
    for p in raw:
        title  = p.get("title", "").strip()
        handle = p.get("handle", "").strip()
        body   = re.sub(r"<[^>]+>", "", p.get("body_html", "") or "").strip()
        url    = f"{STORE}/products/{handle}"

        material, product_type, spec, part_num = parse_title(title)
        mesh_or_opening = extract_mesh_size(spec, title)
        wire_dia        = extract_wire_dia(spec, title)

        items.append({
            "title":        title,
            "handle":       handle,
            "url":          url,
            "material":     material,
            "product_type": product_type,
            "spec":         spec,
            "part_num":     part_num,
            "mesh_opening": mesh_or_opening,
            "wire_dia":     wire_dia,
            "description":  body[:300] if body else title,
        })

    out = os.path.join(os.path.dirname(__file__), "catalog.json")
    with open(out, "w") as f:
        json.dump(items, f, indent=2)

    print(f"\nCatalog rebuilt: {len(items)} products → {out}")

    # Summary by product type
    from collections import Counter
    types = Counter(i["product_type"] for i in items)
    print("\nProduct types:")
    for t, n in types.most_common():
        print(f"  {n:4d}  {t}")

    mats = Counter(i["material"] for i in items)
    print("\nMaterials:")
    for m, n in mats.most_common():
        print(f"  {n:4d}  {m}")

if __name__ == "__main__":
    build()
