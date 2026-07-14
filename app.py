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
