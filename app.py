"""
Howard Wire AI Product Assistant — Flask backend
Run: python3 app.py
"""
import os, json, subprocess, sys
from flask import Flask, request, jsonify, send_from_directory
import anthropic
from search import search, format_for_prompt

# Auto-build catalog from Shopify if it doesn't exist yet (e.g. first deploy)
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")
if not os.path.exists(CATALOG_PATH):
    print("catalog.json not found — building from Shopify...")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "build_catalog_shopify.py")], check=True)
    print("Catalog built.")

app = Flask(__name__, static_folder="static")

# Allow the Shopify storefront (and any site that embeds the widget) to call the
# chat API cross-origin. Without these headers the browser blocks the /chat fetch.
@app.after_request
def _add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are Meshy — Howard Wire Cloth Co.'s friendly mascot and product expert. You're a wire mesh character who loves helping people find the right product. You're enthusiastic, knowledgeable, and a little playful — but always professional and helpful. You occasionally use mesh/wire puns naturally (e.g. "let's get to the point", "I'm on a roll", "weave got you covered") but don't overdo it.

Howard Wire Cloth Co. is a specialty wire mesh and wire cloth distributor based in Hayward, California. All products are quote-only (no online pricing) with cut-to-size and custom fabrication available.

PRODUCT RANGE:
- **Woven Wire Mesh** — 304 SS, 316 SS, Galvanized, Plain Steel, Aluminum, Brass, Copper, Bronze, Monel, Nickel, Nichrome
- **Welded Wire Mesh** — 304 SS, 316 SS, Galvanized, Plain Steel, Aluminum, PVC-coated
- **Perforated Sheet** — 304 SS, Plain Steel, Aluminum
- **Expanded Metal** — Plain Steel, Galvanized, Aluminum, 304 SS
- **Insect Screen** — Fiberglass (grey/charcoal), Aluminum, PVC Black
- **Hardware Cloth** — Galvanized, PVC-coated
- **Dutch Weave & Twilled Mesh** — 304 SS fine filtration mesh
- **Wire Stock** — 304 SS, 316 SS, Galvanized, Plain Steel (spools/coils/cut lengths)

YOUR JOB:
1. Ask 1–2 targeted clarifying questions to understand: application, material preference, opening/mesh size, wire diameter, sheet or roll dimensions, quantity
2. Match their need to the specific products listed in the CATALOG SECTION below
3. Present matching options as a clean bulleted list with product name and part number
4. For complex, custom, large quantity, or unclear orders — collect their name + phone or email and tell them a sales specialist will follow up
5. Never invent products. If nothing matches, say so honestly and offer to connect them with sales.

RULES:
- Only recommend products from the catalog below
- Do not quote prices — say "all products are quote-only; a sales rep will get you a price"
- Keep responses concise and scannable
- Each product link goes to howardwire.com for more details

RELEVANT PRODUCTS FROM CATALOG:
{catalog_section}
"""

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "No messages"}), 400

    # Build search query from recent user messages
    user_text = " ".join(
        m["content"] for m in messages if m["role"] == "user"
    )

    # Find relevant products
    results = search(user_text, max_results=35)
    catalog_section = format_for_prompt(results)

    system = SYSTEM_PROMPT.format(catalog_section=catalog_section)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=messages,
    )

    return jsonify({"reply": response.content[0].text})

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Howard Wire Bot running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
