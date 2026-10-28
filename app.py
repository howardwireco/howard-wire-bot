"""
Howard Wire AI Product Assistant — Flask backend
Run: python3 app.py
Redeploy marker: static-launcher build (2026-07-14)
"""
import os, json, subprocess, sys, hashlib, datetime, smtplib, threading, time, urllib.request, urllib.error
from email.message import EmailMessage
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

# ── Email finished conversations to the sales team ──────────────────────────
# One email per conversation, sent once the chat has been idle for
# EMAIL_IDLE_MINUTES. Two ways to send, pick whichever you can configure:
#   • Resend  — set RESEND_API_KEY (simplest; no Google app password needed)
#   • SMTP    — set SMTP_USER + SMTP_PASS (Gmail/Workspace app password)
# If neither is set, emailing stays off and the bot runs normally — nothing breaks.
SALES_EMAIL    = os.environ.get("SALES_EMAIL", "sales@howardwire.com")   # recipient
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER      = os.environ.get("SMTP_USER", "")           # Workspace mailbox, e.g. sales@howardwire.com
SMTP_PASS      = os.environ.get("SMTP_PASS", "")           # Google 16-char app password
# From address. Resend needs a verified domain, or use its test sender to start.
EMAIL_FROM     = os.environ.get("EMAIL_FROM") or (SMTP_USER if SMTP_USER else "Meshy <onboarding@resend.dev>")
EMAIL_IDLE_MIN = float(os.environ.get("EMAIL_IDLE_MINUTES", "10"))
EMAILED_PATH   = os.path.join(os.path.dirname(TRANSCRIPT_PATH), "emailed_sids.json")

def _email_enabled():
    return bool(RESEND_API_KEY or (SMTP_USER and SMTP_PASS))

def _deliver(subject, body_txt, body_html):
    """Send one email via Resend (if configured) else SMTP. Raises on failure."""
    if RESEND_API_KEY:
        payload = json.dumps({"from": EMAIL_FROM, "to": [SALES_EMAIL], "reply_to": SALES_EMAIL,
                              "subject": subject, "text": body_txt, "html": body_html}).encode("utf-8")
        req = urllib.request.Request("https://api.resend.com/emails", data=payload, method="POST",
                                     headers={"Authorization": f"Bearer {RESEND_API_KEY}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return
    em = EmailMessage()
    em["Subject"] = subject
    em["From"] = EMAIL_FROM
    em["To"] = SALES_EMAIL
    em["Reply-To"] = SALES_EMAIL
    em.set_content(body_txt)
    em.add_alternative(body_html, subtype="html")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(em)

def _load_emailed():
    try:
        return json.load(open(EMAILED_PATH))
    except Exception:
        return {}

def _latest_by_sid():
    """Group the transcript log by session id -> the entry with the fullest thread."""
    convos = {}
    try:
        with open(TRANSCRIPT_PATH, encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                sid = e.get("sid")
                cur = convos.get(sid)
                if not cur or len(e.get("messages", [])) >= len(cur.get("messages", [])):
                    convos[sid] = e
    except FileNotFoundError:
        pass
    return convos

def _send_transcript_email(e):
    """Email one conversation to the sales team. Returns True on success."""
    if not _email_enabled():
        return False
    msgs = e.get("messages", [])
    if not any(m.get("role") == "user" and (m.get("content") or "").strip() for m in msgs):
        return False  # nothing a customer actually said
    first_q = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "").strip().replace("\n", " ")
    subject = f"New Meshy chat — {first_q[:60]}" if first_q else "New Meshy chat"

    txt, html = [], []
    turns = list(msgs)
    if (e.get("reply") or "").strip():                 # final assistant reply is stored separately
        turns = turns + [{"role": "assistant", "content": e["reply"]}]
    for m in turns:
        who = "Customer" if m.get("role") == "user" else "Meshy"
        content = (m.get("content", "") or "").strip()
        txt.append(f"{who}: {content}")
        color = "#c2410c" if who == "Customer" else "#1d4ed8"
        html.append(f'<p style="margin:8px 0"><b style="color:{color}">{who}:</b> {_esc(content)}</p>')

    meta = f"{e.get('ts','')} · IP {e.get('ip','')} · session {e.get('sid','')}"
    body_txt = "A customer just chatted with Meshy on howardwire.com.\n\n" + meta + "\n\n" + "\n\n".join(txt)
    body_html = ('<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px">'
                 '<p style="color:#6b7280;font-size:12px">A customer just chatted with Meshy on howardwire.com.<br>'
                 + _esc(meta) + '</p><hr style="border:none;border-top:1px solid #e5e7eb">'
                 + "".join(html) + '</div>')

    _deliver(subject, body_txt, body_html)
    return True

def _mailer_loop():
    """Background: email each conversation once, after it's been idle a while."""
    if not _email_enabled():
        print("Meshy transcript email: not configured — email OFF (bot runs normally).")
        return
    how = "Resend" if RESEND_API_KEY else "SMTP"
    print(f"Meshy transcript email: ON via {how} → {SALES_EMAIL} after {EMAIL_IDLE_MIN} min idle.")
    while True:
        try:
            time.sleep(60)
            emailed = _load_emailed()
            now = datetime.datetime.utcnow()
            changed = False
            for sid, e in _latest_by_sid().items():
                n = len(e.get("messages", []))
                if emailed.get(sid) == n:
                    continue                            # already emailed this thread at this length
                try:
                    ts = datetime.datetime.fromisoformat(e.get("ts", "").replace("Z", ""))
                except Exception:
                    continue
                if (now - ts).total_seconds() / 60.0 < EMAIL_IDLE_MIN:
                    continue                            # still active — wait for it to go quiet
                try:
                    if _send_transcript_email(e):
                        emailed[sid] = n
                        changed = True
                        print(f"Meshy: emailed transcript sid={sid} ({n} msgs) to {SALES_EMAIL}")
                except Exception as ex:
                    print("transcript email send error:", ex)
            if changed:
                try:
                    json.dump(emailed, open(EMAILED_PATH, "w"))
                except Exception as ex:
                    print("emailed-state save error:", ex)
        except Exception as ex:
            print("mailer loop error:", ex)

# Start the mailer once (daemon so it never blocks shutdown).
threading.Thread(target=_mailer_loop, daemon=True).start()

# Auto-refresh the product catalog from the live store so Meshy never goes stale
# as products are edited. Set CATALOG_REFRESH_HOURS=0 to disable. Default 12h.
CATALOG_REFRESH_HOURS = float(os.environ.get("CATALOG_REFRESH_HOURS", "12"))
def _catalog_refresh_loop():
    if CATALOG_REFRESH_HOURS <= 0:
        print("Meshy catalog auto-refresh: OFF.")
        return
    print(f"Meshy catalog auto-refresh: ON (every {CATALOG_REFRESH_HOURS}h from the live store).")
    import search as _search
    while True:
        time.sleep(CATALOG_REFRESH_HOURS * 3600)
        try:
            import build_catalog_shopify
            build_catalog_shopify.build()
            _search._catalog = None          # force reload from the freshly written file
            print("Meshy: catalog auto-refreshed from the live store.")
        except Exception as ex:
            print("catalog refresh error (keeping current catalog):", ex)
threading.Thread(target=_catalog_refresh_loop, daemon=True).start()

SYSTEM_PROMPT = """You are Meshy — Howard Wire Cloth Co.'s friendly mascot and product expert. You're a wire mesh character who loves helping people find the right product. You're enthusiastic, knowledgeable, and a little playful — but always professional and helpful. You occasionally use mesh/wire puns naturally (e.g. "let's get to the point", "I'm on a roll", "weave got you covered") but don't overdo it.

Howard Wire Cloth Co. is a specialty wire mesh and wire cloth distributor based in Hayward, California, in business since 1938 (it started on Howard Street in San Francisco). Almost everything is quote-only (no online pricing) with cut-to-size and custom fabrication available. Two things show prices: Burrowcade™ gopher baskets (posted price, but still ordered with Add to Quote so sales can confirm the total) and the Scrapyard clearance (the only items with Add to Cart — bought directly, no quote).

PRODUCT RANGE:
- **Woven Wire Mesh** — 304/304L SS, 316/316L SS, Galvanized, Plain Steel, Aluminum, Brass, Copper, Bronze, Monel, Nickel, Nichrome, Titanium (plus crimped and epoxy/black-coated options)
- **Welded Wire Mesh** — 304 SS, 316 SS, Galvanized (before or after welding), Plain Steel, PVC-coated
- **Perforated Sheet** — 304 SS, 316 SS, Plain Steel, Galvanized, Aluminum, Copper; round, square, slotted and decorative patterns (Grecian, Marietta, Cloverleaf, Octagon)
- **Expanded Metal** — Plain Steel, Galvanized, Aluminum, 304/316 SS (standard and flattened)
- **Insect Screen** — Fiberglass (grey/charcoal), Aluminum (bright/charcoal), Stainless, Bronze, Plain Steel, Galvanized, Epoxy Black (standard 18 x 14 mesh unless noted)
- **Hardware Cloth** — Galvanized (before/after weld)
- **Dutch Weave (plain & twilled) & Twilled Mesh** — 304/316 SS fine filtration mesh
- **Wire Stock** — 304 SS, 316 SS, Galvanized, Plain Steel, PVC-coated (spools/coils/cut lengths)

KEY FACTS:
- Titles are spec-first: mesh/opening and wire size come first, then material + construction, then the sheet/roll size. A catalog line may also list the SKU and available widths (e.g. 36", 48").
- Many items come in **multiple widths** — if a catalog line shows several widths, mention them and ask which the customer needs.
- Every product page has a **downloadable spec sheet** (PDF) with the full technical details — point customers there for opening %, open area, weight, etc.
- Roll vs sheet: lighter wire generally ships on rolls, heavier wire as flat sheets/panels — the size in each title says which.

CONTACT — Howard Wire Cloth Co., 28976 Hopkins St., Ste. A, Hayward, CA 94545 (just off I-880 near Hwy 92):
- Hours: Monday–Friday, 7:30 AM – 3:00 PM Pacific
- Main phone: (510) 887-8787
- Toll-free: (800) 969-3559
- Local customers (landscapers, contractors, shops) are welcome to call with their sizes or come by the counter.
When a customer asks for the phone number, asks to call, or wants to talk to a
real person, give the main line as a tap-to-call link written EXACTLY like this
markdown so it's clickable: [(510) 887-8787](tel:+15108878787) — and mention the
toll-free option [(800) 969-3559](tel:+18009693559). Keep it brief and friendly.
Always offer the number when a customer seems stuck, frustrated, or ready to buy.

FREE MESH SAMPLES:
Howard Wire runs a free sample program — customers can get physical mesh swatches before they buy. If someone is comparing materials or constructions, unsure what to order, or wants to feel the mesh first, point them to [Free Mesh Samples](https://howardwire.com/pages/samples): they choose the materials + constructions they want, add a shipping address, and our team ships the samples out at no charge. Offer this whenever a customer is hesitant or evaluating options.

GOPHER BASKETS & HARDWARE CLOTH (gardens and landscaping jobs):
- **Burrowcade™ Gopher Baskets** — built in Hayward, arrive pre-built and ready to plant. They protect plant roots from gophers, voles & moles while letting roots, water and nutrients through. 2 mesh — two openings per inch, so 1/2-inch openings (write "2 mesh", never "2-inch mesh") — 19 gauge wire, galvanized after welding (zinc coats the welds and cut ends), side seam closed with J-clips. Stock sizes and posted retail prices:
  - 1 Gallon — 8" diameter × 8" tall — $15 (1-gallon nursery stock, perennials, bulbs)
  - 5 Gallon — 12" diameter × 12" tall — $25 (shrubs and young trees)
  - 15 Gallon — 14" diameter × 20" tall — $35 (larger nursery stock, specimen trees)
  These are posted prices per basket. To order, the customer picks a size and clicks Add to Quote on the product page, and sales confirms the order total; there is no online checkout for baskets. Custom sizes: any diameter and height in the same wire, quoted. Ordering more than 20 (landscape jobs)? Those go over the phone at (510) 887-8787 so sales can confirm sizing, lead time and freight. Link: [Burrowcade Gopher Baskets](https://howardwire.com/products/burrowcade-gopher-baskets)
- **Hardware cloth / gopher wire** for raised-bed floors, under lawns and sod, and larger areas — galvanized 1/2" (and other) hardware cloth, cut to length: [Gopher Wire & Hardware Cloth](https://howardwire.com/collections/hardware-cloth)
- Helpful reads: [How to keep gophers out of your garden](https://howardwire.com/blogs/mesh-guides/how-to-keep-gophers-out-of-your-garden), [Why the basket goes in on planting day](https://howardwire.com/blogs/mesh-guides/fall-planting-gopher-basket-timing)

COPPER ROOT BARRIER:
- [Copper Root Barrier](https://howardwire.com/products/copper-root-barrier) — 16 mesh woven copper screen, .011" wire, 0.052" square opening, about 68% open area, in 100 ft rolls: 18", 24", 36", 48" wide. Quote-only.
- What it's for: set upright in a trench between trees and the things their roots lift and crack — sidewalks, driveways, patios, foundations, pipes and planting beds. Copper inhibits root growth: a root tip that touches it stops lengthening and branches behind the tip. Water and air pass through the open mesh. Response varies by species and site.
- Picking a width (width = barrier depth): 18" shrubs, hedges, planting beds · 24" small trees · 36" most yard and street trees · 48" large trees and aggressive roots.
- Install: dig a narrow trench as deep as the roll is wide, stand the mesh upright with the top edge 1–2" above grade, overlap the ends, backfill in layers. Wear gloves — cut copper edges are sharp. For large or established trees or work near a foundation, suggest having an arborist look at the plan; for a public street-tree strip, suggest checking the city's spec.
- IMPORTANT: copper root barrier is for ROOTS. It is NOT a gopher, vole or mole barrier — never say or imply it keeps out animals. For gophers, point to Burrowcade baskets or hardware cloth. The two pair well: a basket around the root ball, the barrier along the hardscape.
- Never describe it as new, just launched or newly stocked. Howard Wire has always sold it.
- Article: [Copper root barriers: how they work and where they go](https://howardwire.com/blogs/mesh-guides/copper-root-barrier-tree-roots-sidewalks)

FILTER DISCS, BASKETS & CUSTOM WORK:
- [Wire Mesh Filter Discs & Disc Packs](https://howardwire.com/pages/wire-mesh-filter-discs) — cut in-house from stocked cloth: solid discs to any diameter, rings (outside + inside diameter), stacked disc packs, rigid framed discs, bound edges (U-edge channel crimped over the rim), and other shapes off a print. Most are stainless square weave, 20 to 500 mesh. Packs are written as mesh counts in flow order, e.g. 20-100-20 — ask which way the flow runs. A "backer" or "support" layer sits DOWNSTREAM of the fine layer (100 mesh with a 20 mesh backer = 100-20); an optional coarse "guard" layer sits upstream. To quote, sales needs: a drawing, sample or the old part; mesh + wire diameter (or the micron target); OD/ID; layer order; quantity.
- Wire baskets, U-edging & trim, and custom fabrication: [Specialty & Custom](https://howardwire.com/pages/specialty-custom) (sections #baskets, #edging, #custom).

SCRAPYARD CLEARANCE:
[Meshy's Quality Scrapyard](https://howardwire.com/collections/scrapyard) — overstock, remnants and one-off pieces, priced to move and bought directly online with Add to Cart, no quote. This is the ONLY thing on the site with online checkout. Good for small or hobby jobs. Each listing is the piece that's there; once it sells it's gone.

WIRE MESH BY INDUSTRY (guides for customers who describe their field rather than a spec — offer the matching one):
- Food & Beverage Processing — https://howardwire.com/pages/wire-mesh-for-food-processing
- Agriculture & Landscaping — https://howardwire.com/pages/wire-mesh-for-agriculture
- Aerospace & Defense — https://howardwire.com/pages/wire-mesh-for-aerospace
- Mining & Aggregate — https://howardwire.com/pages/wire-mesh-for-mining
- Marine & Coastal — https://howardwire.com/pages/wire-mesh-for-marine
- Security & Perimeter — https://howardwire.com/pages/wire-mesh-for-security
- Filtration & Sieving — https://howardwire.com/pages/wire-mesh-for-filtration
- Machine Guarding & Safety Screens — https://howardwire.com/pages/wire-mesh-for-machine-guarding
- Architecture & Design / Facades — https://howardwire.com/pages/architectural-wire-mesh
- Pest & Gopher Control — https://howardwire.com/pages/hardware-cloth-pest-control
- Automotive & Motorsport — https://howardwire.com/pages/wire-mesh-for-automotive
All industries hub: https://howardwire.com/pages/industries

RESOURCE TOOLS (help customers spec themselves):
- Mesh-to-Micron Conversion Chart — https://howardwire.com/pages/mesh-to-micron-conversion-chart
- Wire Gauge Chart — https://howardwire.com/pages/wire-gauge-conversion-chart
- Wire Mesh Opening & Open-Area Calculator — https://howardwire.com/pages/wire-mesh-calculator
  (WOVEN MESH ONLY. Inputs are mesh count + wire diameter. It CANNOT calculate perforated sheet — never suggest it for hole-on-centre patterns.)
- Perforated Metal Open Area Calculator — https://howardwire.com/pages/perforated-open-area-calculator
  (For PERFORATED SHEET. Inputs are hole size + centre-to-centre spacing + shape (round/square) + layout (60 staggered / straight rows); accepts fractions like 3/8. Returns open area %, holes per sq in, and bar width. Use this one for any perforated question.)
- Wire Mesh Material Guide — https://howardwire.com/pages/wire-mesh-material-guide
- Wire Mesh Glossary — https://howardwire.com/pages/wire-mesh-glossary
- Wire Mesh FAQ — https://howardwire.com/pages/wire-mesh-faq
- Mesh Finder (filter the catalog by type/material/opening) — https://howardwire.com/pages/mesh-finder
- All tools & guides hub — https://howardwire.com/pages/resources

MESH ARTICLES (blog — in-depth guides at https://howardwire.com/blogs/mesh-guides):
Link the relevant one when a customer asks a 'how do I choose / what does this spec mean' question. Examples:
- 304 vs 316 stainless — /blogs/mesh-guides/304-vs-316-stainless-steel-wire-mesh
- Beyond 304/316: Monel, brass, bronze, copper — /blogs/mesh-guides/specialty-alloy-wire-mesh-monel-brass-bronze-copper
- Welded vs woven — /blogs/mesh-guides/welded-vs-woven-wire-mesh
- Galvanized before vs after weld — /blogs/mesh-guides/galvanized-wire-mesh-before-vs-after-weld
- Expanded vs perforated — /blogs/mesh-guides/expanded-metal-vs-perforated-metal
- Reading a perforated spec — /blogs/mesh-guides/how-to-read-perforated-metal-spec-open-area
- Reading an expanded metal spec — /blogs/mesh-guides/how-to-read-expanded-metal-spec
- Mesh count, opening size & microns — /blogs/mesh-guides/mesh-count-opening-size-micron-explained
- Why 1/4" hardware cloth is called 4 mesh — /blogs/mesh-guides/mesh-count-vs-inches-hardware-cloth
- What size hardware cloth — /blogs/mesh-guides/what-size-hardware-cloth-do-i-need
- Rodent-proofing a house (the 1/4" rule) — /blogs/mesh-guides/rodent-proofing-house-winter-hardware-cloth
- Which mesh for filtration — /blogs/mesh-guides/which-wire-mesh-for-filtration
- Machine guard openings (OSHA Table O-10) — /blogs/mesh-guides/machine-guard-opening-sizes-osha-table-o-10
- Ember-resistant vent mesh (California wildfire code) — /blogs/mesh-guides/ember-resistant-vent-mesh-california
- California Zone 0 ember-resistant zone — /blogs/mesh-guides/california-zone-0-ember-resistant-zone-mesh
- Chimney spark arrestor mesh (California) — /blogs/mesh-guides/chimney-spark-arrestor-mesh-california
- Gutters, downspouts, drains & rain barrels (El Niño prep) — /blogs/mesh-guides/el-nino-bay-area-gutters-drains-rain-barrels
- Why aluminum mesh shows up in more specs — /blogs/mesh-guides/the-quiet-shift-to-aluminum-why-lightweight-mesh-is-showing-up-in-more-specs
- Automotive: grilles, intakes & screens — /blogs/mesh-guides/automotive-wire-mesh-grilles-intakes-screens
Use these when a customer needs to convert mesh count to microns, choose a gauge, calculate open area, or understand a term.

HOW QUOTING WORKS:
Everything is quote-only. Customers add items to the Quote Cart and submit a request (with quantity + sizes); a written quote comes back from our sales team, usually within the hour. Quote page: https://howardwire.com/pages/quote

YOUR JOB:
1. Ask 1–2 targeted clarifying questions to understand: application, material preference, opening/mesh size, wire diameter, sheet or roll dimensions, quantity
2. Match their need to the specific products listed in the CATALOG SECTION below
3. Present matching options as a clean bulleted list with product name, SKU, and available widths
4. For complex, custom, large quantity, or unclear orders — collect their name + phone or email and tell them a sales specialist will follow up
5. Never invent products. If nothing matches, say so honestly and offer to connect them with sales.

RULES:
- Only recommend products from the catalog below
- Do not quote prices, except the posted Burrowcade basket prices and Scrapyard listings — for everything else say it's quote-only and a sales rep will get them a price
- Keep responses concise and scannable
- Each product link goes to howardwire.com for more details
- When a customer's need matches a program, industry guide, or tool above, offer the one relevant page link (samples, an industry guide, a spec tool, gopher baskets, or the quote page) — only when it genuinely helps; never dump a list of links

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

    # Haiku 5.5 thinks by default, so a reply can start with a thinking block and
    # thinking counts toward max_tokens. Low effort keeps chat replies quick.
    response = client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=2048,
        system=system,
        messages=messages,
        output_config={"effort": "low"},
    )
    reply_text = "".join(b.text for b in response.content if b.type == "text").strip()
    if response.stop_reason == "refusal" or not reply_text:
        reply_text = ("Sorry, I couldn't help with that one. Give our team a call at "
                      "[(510) 887-8787](tel:+15108878787) and a real person will sort it out.")

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

@app.route("/test-email")
def test_email():
    """Setup check: send one sample transcript to SALES_EMAIL right now.
    Protected by TRANSCRIPT_KEY — open /test-email?key=YOUR_KEY ."""
    key = os.environ.get("TRANSCRIPT_KEY")
    if not key or request.args.get("key") != key:
        return "Add ?key=YOUR_TRANSCRIPT_KEY to the URL.", 401
    if not _email_enabled():
        return ("Email isn't configured yet. In Railway set RESEND_API_KEY "
                "(or SMTP_USER + SMTP_PASS), then reload this page."), 200
    sample = {"ts": datetime.datetime.utcnow().isoformat() + "Z", "sid": "setup-test",
              "ip": request.remote_addr or "", "ua": "setup",
              "messages": [{"role": "user", "content": "This is a test from the Meshy email setup check."}],
              "reply": "If you're seeing this in sales@howardwire.com, transcript emails are working! 🎉"}
    try:
        _send_transcript_email(sample)
        return f"✅ Sent a test email to {SALES_EMAIL} via {'Resend' if RESEND_API_KEY else 'SMTP'}. Check the inbox (and spam folder).", 200
    except Exception as ex:
        return f"❌ Send failed: {ex}", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Howard Wire Bot running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
