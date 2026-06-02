"""
Run once to build catalog.json from the QuickBooks CSV export.
Usage: python3 build_catalog.py "path/to/item list.CSV"
"""
import csv, json, sys, os

def build(csv_path, out_path="catalog.json"):
    items = []
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 5:
                continue
            status = row[1].strip()
            itype  = row[2].strip()
            item   = row[3].strip()
            desc   = row[4].strip()
            qty    = row[11].strip() if len(row) > 11 else ""
            price  = row[16].strip() if len(row) > 16 else ""

            if (status == "Active"
                    and itype == "Inventory Part"
                    and "DO NOT USE" not in desc
                    and desc
                    and item.count(":") >= 2):

                parts = [p.strip() for p in item.split(":")]
                items.append({
                    "item_code":    item,
                    "description":  desc,
                    "opening":      parts[0],
                    "material":     parts[1] if len(parts) > 1 else "",
                    "part_num":     parts[2] if len(parts) > 2 else "",
                    "qty_on_hand":  qty,
                    "price":        price,
                })

    with open(out_path, "w") as f:
        json.dump(items, f, indent=2)

    print(f"Built {len(items)} active products → {out_path}")

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/Desktop/item list.CSV"
    )
    build(csv_path)
