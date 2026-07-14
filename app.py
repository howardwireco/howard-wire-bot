"""
Howard Wire AI Product Assistant — Flask backend
Run: python3 app.py
Redeploy marker: static-launcher build (2026-07-14)
"""
import os, json, subprocess, sys, hashlib, datetime
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

# Where customer-conversation transcripts are written. Set TRANSCRIPT_DIR to a Railway
# VOLUME mount (e.g. /data) to keep history across deploys; otherwise it lives next to
# the app and resets when the app redeploys.
TRANSCRIPT_PATH = os.path.join(os.environ.get("TRANSCRIPT_DIR", os.path.dirname(__file__)), "transcripts.jsonl")

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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
    reply_text = response.content[0].text

    # Log the conversation so the sales team can review what customers asked,
    # where Meshy got stuck, and which chats need follow-up. Wrapped so a logging
    # failure can never break the chat reply.
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "") or ""
        ua = request.headers.get("User-Agent", "")
        first = messages[0].get("content", "") if messages else ""
        sid = hashlib.sha1((ip + ua + first).encode("utf-8", "ignore")).hexdigest()[:12]
        entry = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "sid": sid,
            "ip": ip,
            "ua": ua[:180],
            "messages": messages,
            "reply": reply_text,
        }
        with open(TRANSCRIPT_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print("transcript log error:", e)

    return jsonify({"reply": reply_text})

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/transcripts")
def transcripts():
    """Private viewer of Meshy ↔ customer conversations. Protected by the
    TRANSCRIPT_KEY env var: open /transcripts?key=YOUR_KEY ."""
    key = os.environ.get("TRANSCRIPT_KEY")
    if not key:
        return ("Transcript viewing isn't enabled yet. In Railway, set a TRANSCRIPT_KEY "
                "environment variable to any secret word, then open /transcripts?key=YOUR_KEY"), 200
    if request.args.get("key") != key:
        return "Unauthorized. Add ?key=YOUR_KEY to the URL.", 401

    convos = {}
    try:
        with open(TRANSCRIPT_PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                cur = convos.get(e.get("sid"))
                if not cur or len(e.get("messages", [])) >= len(cur.get("messages", [])):
                    convos[e.get("sid")] = e
    except FileNotFoundError:
        pass

    items = sorted(convos.values(), key=lambda x: x.get("ts", ""), reverse=True)
    cards = []
    for e in items:
        turns = []
        for m in e.get("messages", []):
            role = "Customer" if m.get("role") == "user" else "Meshy"
            cls = "user" if m.get("role") == "user" else "assistant"
            turns.append(f'<div class="t {cls}"><b>{role}:</b> {_esc(m.get("content", ""))}</div>')
        turns.append(f'<div class="t assistant"><b>Meshy:</b> {_esc(e.get("reply", ""))}</div>')
        cards.append(f'<div class="c"><div class="meta">{_esc(e.get("ts", ""))} · {_esc(e.get("ip", ""))}</div>{"".join(turns)}</div>')

    body = "".join(cards) or "<p>No conversations logged yet.</p>"
    return ("<!doctype html><meta charset=utf-8><title>Meshy transcripts</title>"
            "<style>body{font-family:-apple-system,Segoe UI,sans-serif;background:#0a0a0c;color:#eee;margin:0;padding:24px}"
            "h1{font-size:18px}.c{background:#15151a;border:1px solid #2a2a30;border-radius:8px;padding:14px 16px;margin:14px 0;max-width:800px}"
            ".meta{font-size:11px;color:#888;margin-bottom:8px;font-family:ui-monospace,monospace}"
            ".t{margin:6px 0;line-height:1.5;font-size:14px}.t.user b{color:#f26919}.t.assistant b{color:#7ab8ff}</style>"
            f"<h1>Meshy — customer conversations ({len(items)})</h1>{body}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Howard Wire Bot running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
