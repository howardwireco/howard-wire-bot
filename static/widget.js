/* Howard Wire Chat Widget — embeddable */
(function () {
  var API_URL = document.currentScript
    ? document.currentScript.getAttribute("data-api") || "/chat"
    : "/chat";

  var messages = [];
  var isOpen   = false;
  var isBusy   = false;

  var WELCOME = "Hi! I'm the Howard Wire product assistant. Tell me what you're looking for — material, opening size, wire diameter, application — and I'll find the right mesh from our catalog.\n\nWhat do you need?";

  var SUGGESTIONS = [
    "Stainless steel mesh",
    "1/4\" opening wire cloth",
    "Galvanized welded wire",
    "Talk to sales"
  ];

  // ── Build DOM ────────────────────────────────────────────────
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html) e.innerHTML = html;
    return e;
  }

  var launcher = el("button", "hw-launcher");
  launcher.setAttribute("aria-label", "Open Howard Wire chat");
  launcher.innerHTML =
    '<div class="hw-badge"></div>' +
    '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 10H6V10h12v2zm0-3H6V7h12v2z"/></svg>';
  launcher.onclick = toggle;

  var panel = el("div", "hw-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Howard Wire Product Assistant");
  panel.innerHTML = [
    '<div class="hw-header">',
    '  <div class="hw-avatar">🔩</div>',
    '  <div class="hw-info">',
    '    <div class="hw-name">Howard Wire Assistant</div>',
    '    <div class="hw-status">Online — Ready to help</div>',
    '  </div>',
    '  <button class="hw-close-btn" aria-label="Close">×</button>',
    '</div>',
    '<div class="hw-messages" id="hw-msgs"></div>',
    '<div class="hw-suggestions" id="hw-sugs"></div>',
    '<div class="hw-input-row">',
    '  <textarea class="hw-input" id="hw-inp" rows="1" placeholder="Describe what you need…"></textarea>',
    '  <button class="hw-send" id="hw-btn" aria-label="Send">',
    '    <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>',
    '  </button>',
    '</div>',
    '<div class="hw-footer">Howard Wire · <a href="https://howardwire.com" target="_blank">howardwire.com</a></div>',
  ].join("");

  panel.querySelector(".hw-close-btn").onclick = close;

  var msgsEl = panel.querySelector("#hw-msgs");
  var sugsEl = panel.querySelector("#hw-sugs");
  var inp    = panel.querySelector("#hw-inp");
  var sendBtn= panel.querySelector("#hw-btn");

  // Suggestions
  SUGGESTIONS.forEach(function (s) {
    var b = el("button", "hw-sug");
    b.textContent = s;
    b.onclick = function () { inp.value = s; send(); };
    sugsEl.appendChild(b);
  });

  inp.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  inp.addEventListener("input", function () {
    inp.style.height = "auto";
    inp.style.height = Math.min(inp.scrollHeight, 100) + "px";
  });
  sendBtn.onclick = send;

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  // ── Controls ─────────────────────────────────────────────────
  function open() {
    panel.classList.add("hw-open");
    launcher.classList.remove("hw-unread");
    isOpen = true;
    if (messages.length === 0) addBot(WELCOME);
    setTimeout(function () { inp.focus(); }, 250);
  }

  function close() {
    panel.classList.remove("hw-open");
    isOpen = false;
  }

  function toggle() { isOpen ? close() : open(); }

  // ── Messaging ─────────────────────────────────────────────────
  function scrollEnd() { msgsEl.scrollTop = msgsEl.scrollHeight; }

  function addBot(text) {
    var d = el("div", "hw-msg hw-bot");
    d.innerHTML = mdToHtml(text);
    msgsEl.appendChild(d);
    scrollEnd();
    if (!isOpen) launcher.classList.add("hw-unread");
  }

  function addUser(text) {
    var d = el("div", "hw-msg hw-user");
    d.textContent = text;
    msgsEl.appendChild(d);
    scrollEnd();
  }

  function showTyping() {
    var d = el("div", "hw-typing");
    d.id = "hw-typing";
    d.innerHTML = "<span></span><span></span><span></span>";
    msgsEl.appendChild(d);
    scrollEnd();
  }

  function hideTyping() {
    var t = document.getElementById("hw-typing");
    if (t) t.remove();
  }

  function hideSugs() { sugsEl.style.display = "none"; }

  async function send() {
    var text = inp.value.trim();
    if (!text || isBusy) return;

    isBusy = true;
    sendBtn.disabled = true;
    hideSugs();
    addUser(text);
    inp.value = "";
    inp.style.height = "auto";
    messages.push({ role: "user", content: text });

    showTyping();
    try {
      var res  = await fetch(API_URL, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ messages: messages }),
      });
      var data = await res.json();
      hideTyping();
      var reply = data.reply || "Something went wrong. Please try again.";
      addBot(reply);
      messages.push({ role: "assistant", content: reply });
    } catch (err) {
      hideTyping();
      addBot("Connection error. Please refresh and try again.");
    } finally {
      isBusy = false;
      sendBtn.disabled = false;
      inp.focus();
    }
  }

  // ── Minimal markdown renderer ─────────────────────────────────
  function mdToHtml(t) {
    t = t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    t = t.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
    t = t.replace(/\*(.+?)\*/g,"<em>$1</em>");
    // bullet lines
    t = t.replace(/^[-•] (.+)$/gm,"<li>$1</li>");
    t = t.replace(/(<li>[\s\S]+?<\/li>)/g,"<ul>$1</ul>");
    t = t.replace(/\n\n/g,"</p><p>").replace(/\n/g,"<br>");
    return "<p>" + t + "</p>";
  }
})();
