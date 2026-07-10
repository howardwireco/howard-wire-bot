/* Howard Wire — Meshy Chat Widget (embeddable) */
(function () {
  var script  = document.currentScript;
  var API_URL = script ? (script.getAttribute("data-api") || "/chat") : "/chat";
  var BASE    = API_URL.replace("/chat", "");   // e.g. https://web-production-bed4.up.railway.app

  var MESHY_ROLL   = BASE + "/static/meshy.png";
  var MESHY_HEADER = BASE + "/static/meshy-header.png";
  var STORE        = "https://howard-wire-cloth-co.myshopify.com";

  var QUICK_LINKS = [
    { icon:"📋", color:"orange", title:"Request a Quote",  sub:"Get pricing from our sales team",    url: STORE + "/pages/contact"    },
    { icon:"🔩", color:"blue",   title:"Browse Products",  sub:"View our full product range",        url: STORE + "/collections/all"  },
    { icon:"❓", color:"green",  title:"FAQ",               sub:"Common questions answered",          url: STORE + "/pages/faq-1"      },
    { icon:"📚", color:"purple", title:"Catalogue",         sub:"Download our product catalogue",     url: STORE + "/pages/catalogue-2"},
  ];

  // ── Inject CSS ──────────────────────────────────────────────────
  var css = `
.hw-launcher{position:fixed;bottom:24px;right:24px;width:68px;height:68px;border-radius:50%;background:#e85d04;border:3px solid #fff;cursor:pointer;box-shadow:0 4px 18px rgba(232,93,4,.45);display:flex;align-items:center;justify-content:center;overflow:hidden;z-index:2147483646;padding:0;}
.hw-launcher img{width:100%;height:100%;object-fit:cover;object-position:50% 18%;}
.hw-launcher .hw-badge{position:absolute;top:3px;right:3px;width:14px;height:14px;border-radius:50%;background:#1a3a5c;border:2px solid #fff;display:none;}
.hw-launcher.hw-unread .hw-badge{display:block;}
.hw-panel{position:fixed;bottom:104px;right:24px;width:390px;max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 120px);background:#fff;border-radius:18px;box-shadow:0 10px 44px rgba(0,0,0,.18);display:flex;flex-direction:column;overflow:hidden;z-index:2147483647;transform:scale(.9) translateY(20px);opacity:0;pointer-events:none;transform-origin:bottom right;transition:transform .22s ease,opacity .22s ease;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
.hw-panel.hw-open{transform:scale(1) translateY(0);opacity:1;pointer-events:all;}
.hw-view{display:flex;flex-direction:column;height:100%;}
.hw-view.hw-hidden{display:none;}

/* HOME */
.hw-home-hero{background:linear-gradient(160deg,#e85d04 0%,#ff8c42 50%,#ffb347 100%);padding:28px 20px 0;display:flex;flex-direction:column;align-items:center;position:relative;flex-shrink:0;}
.hw-home-close{position:absolute;top:12px;right:14px;background:rgba(255,255,255,.25);border:none;color:#fff;width:28px;height:28px;border-radius:50%;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;}
.hw-home-close:hover{background:rgba(255,255,255,.4);}
.hw-home-meshy{width:150px;height:150px;object-fit:contain;object-position:center center;filter:drop-shadow(0 6px 16px rgba(0,0,0,.25));margin-bottom:-10px;}
.hw-home-body{flex:1;overflow-y:auto;padding:24px 20px 16px;}
.hw-home-body::-webkit-scrollbar{width:4px;}
.hw-home-body::-webkit-scrollbar-thumb{background:#ddd;border-radius:2px;}
.hw-greeting{font-size:1.35rem;font-weight:700;color:#1a1a1a;margin-bottom:4px;}
.hw-sub{font-size:.9rem;color:#555;margin-bottom:20px;line-height:1.5;}
.hw-chat-cta{background:#fff;border:1.5px solid #ffd7bc;border-radius:14px;padding:14px 16px;display:flex;align-items:center;gap:14px;cursor:pointer;margin-bottom:16px;transition:border-color .15s,box-shadow .15s;text-decoration:none;}
.hw-chat-cta:hover{border-color:#e85d04;box-shadow:0 2px 12px rgba(232,93,4,.15);}
.hw-cta-av{width:46px;height:46px;border-radius:50%;overflow:hidden;flex-shrink:0;border:2px solid #ffd7bc;background:#fff4ee;}
.hw-cta-av img{width:100%;height:100%;object-fit:cover;object-position:50% 18%;}
.hw-cta-title{font-weight:700;font-size:.95rem;color:#1a1a1a;}
.hw-cta-sub{font-size:.78rem;color:#888;margin-top:2px;}
.hw-cta-arrow{margin-left:auto;color:#e85d04;font-size:1.2rem;}
.hw-qa-list{background:#f9f9f9;border:1px solid #eee;border-radius:14px;overflow:hidden;margin-bottom:16px;}
.hw-qa-item{display:flex;align-items:center;gap:12px;padding:13px 16px;border-bottom:1px solid #eee;cursor:pointer;text-decoration:none;transition:background .12s;color:#1a1a1a;}
.hw-qa-item:last-child{border-bottom:none;}
.hw-qa-item:hover{background:#f0f0f0;}
.hw-qa-icon{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.hw-qa-icon.orange{background:#fff0e6;}.hw-qa-icon.blue{background:#e8f0fe;}.hw-qa-icon.green{background:#e8f5e9;}.hw-qa-icon.purple{background:#f3e8fd;}
.hw-qa-lbl{flex:1;}
.hw-qa-title{font-size:.9rem;font-weight:600;}
.hw-qa-sub{font-size:.75rem;color:#888;margin-top:1px;}
.hw-qa-chev{color:#bbb;font-size:1rem;}
.hw-home-foot{text-align:center;font-size:.68rem;color:#bba898;padding:8px;border-top:1px solid #f5ede8;flex-shrink:0;}
.hw-home-foot a{color:#bba898;text-decoration:none;}

/* CHAT */
.hw-chat-hdr{background:linear-gradient(135deg,#e85d04 0%,#c44d02 100%);color:#fff;padding:12px 14px;display:flex;align-items:center;gap:10px;flex-shrink:0;}
.hw-back{background:rgba(255,255,255,.2);border:none;color:#fff;width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.hw-back:hover{background:rgba(255,255,255,.35);}
.hw-ch-av{width:42px;height:42px;border-radius:50%;overflow:hidden;border:2px solid rgba(255,255,255,.4);flex-shrink:0;background:#c44d02;}
.hw-ch-av img{width:100%;height:100%;object-fit:cover;object-position:50% 18%;}
.hw-ch-info{flex:1;}
.hw-ch-name{font-weight:700;font-size:.95rem;}
.hw-ch-status{font-size:.72rem;opacity:.85;display:flex;align-items:center;gap:4px;margin-top:2px;}
.hw-ch-status::before{content:"";width:6px;height:6px;border-radius:50%;background:#90ee90;}
.hw-ch-close{background:none;border:none;color:#fff;cursor:pointer;opacity:.75;font-size:22px;line-height:1;}
.hw-ch-close:hover{opacity:1;}
.hw-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;}
.hw-msgs::-webkit-scrollbar{width:4px;}
.hw-msgs::-webkit-scrollbar-thumb{background:#ddd;border-radius:2px;}
.hw-msg{max-width:84%;padding:10px 14px;border-radius:16px;font-size:.875rem;line-height:1.5;word-wrap:break-word;box-sizing:border-box;}
.hw-msg.hw-bot{background:#fff4ee;color:#1a1a1a;align-self:flex-start;border-bottom-left-radius:4px;border:1px solid #ffd7bc;}
.hw-msg.hw-user{background:#e85d04;color:#fff;align-self:flex-end;border-bottom-right-radius:4px;}
.hw-msg.hw-bot ul{padding-left:16px;margin-top:6px;}.hw-msg.hw-bot li{margin-bottom:4px;}
.hw-msg.hw-bot strong{color:#c44d02;}.hw-msg.hw-bot a{color:#c44d02;}
.hw-typing{display:flex;align-items:center;gap:4px;background:#fff4ee;border:1px solid #ffd7bc;padding:10px 14px;border-radius:16px;border-bottom-left-radius:4px;width:fit-content;}
.hw-typing span{width:7px;height:7px;border-radius:50%;background:#e85d04;animation:hw-blink 1.2s ease-in-out infinite;}
.hw-typing span:nth-child(2){animation-delay:.2s;}.hw-typing span:nth-child(3){animation-delay:.4s;}
@keyframes hw-blink{0%,80%,100%{opacity:.25;transform:scale(.8);}40%{opacity:1;transform:scale(1);}}
.hw-sugs{padding:0 14px 10px;display:flex;flex-wrap:wrap;gap:6px;flex-shrink:0;}
.hw-sug{background:#fff4ee;border:1px solid #ffd7bc;color:#c44d02;font-size:.78rem;padding:5px 11px;border-radius:20px;cursor:pointer;white-space:nowrap;font-weight:500;font-family:inherit;}
.hw-sug:hover{background:#ffe8d6;}
.hw-inp-row{padding:10px 12px;border-top:1px solid #f0e8e0;display:flex;gap:8px;flex-shrink:0;background:#fff;}
.hw-inp{flex:1;border:1px solid #f0cdb0;border-radius:22px;padding:9px 14px;font-size:.875rem;outline:none;resize:none;line-height:1.4;max-height:100px;overflow-y:auto;font-family:inherit;}
.hw-inp:focus{border-color:#e85d04;}
.hw-send{width:38px;height:38px;border-radius:50%;background:#e85d04;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;align-self:flex-end;transition:background .15s;}
.hw-send:hover{background:#c44d02;}.hw-send:disabled{background:#f0b090;cursor:default;}
.hw-send svg{width:16px;height:16px;fill:#fff;}
.hw-chat-foot{text-align:center;font-size:.68rem;color:#bba898;padding:6px;border-top:1px solid #f5ede8;flex-shrink:0;}
.hw-chat-foot a{color:#bba898;text-decoration:none;}
`;
  var styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // ── Build DOM ───────────────────────────────────────────────────
  function el(tag, cls) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }
  function img(src, alt) {
    var i = document.createElement("img");
    i.src = src; i.alt = alt || "";
    return i;
  }
  function a(href, cls) {
    var e = document.createElement("a");
    e.href = href; e.target = "_blank"; e.className = cls;
    return e;
  }

  // Launcher
  var launcher = el("button", "hw-launcher");
  launcher.setAttribute("aria-label", "Chat with Meshy");
  var badge = el("div", "hw-badge");
  launcher.appendChild(badge);
  launcher.appendChild(img(MESHY_ROLL, "Meshy"));
  launcher.onclick = toggle;

  // Panel
  var panel = el("div", "hw-panel");
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Chat with Meshy — Howard Wire");

  /* ── HOME VIEW ── */
  var homeView = el("div", "hw-view");
  homeView.id = "hw-home-view";

  var hero = el("div", "hw-home-hero");
  var homeClose = el("button", "hw-home-close");
  homeClose.textContent = "×"; homeClose.setAttribute("aria-label","Close");
  homeClose.onclick = close;
  var heroImg = img(MESHY_HEADER, "Meshy");
  heroImg.className = "hw-home-meshy";
  hero.appendChild(homeClose);
  hero.appendChild(heroImg);

  var homeBody = el("div", "hw-home-body");
  var greeting = el("div", "hw-greeting"); greeting.textContent = "Hi there! 👋";
  var sub = el("div", "hw-sub");
  sub.textContent = "Meshy & the Howard Wire team are ready to help you find the perfect mesh.";

  // Chat CTA
  var cta = el("div", "hw-chat-cta");
  var ctaAv = el("div", "hw-cta-av"); ctaAv.appendChild(img(MESHY_HEADER,"Meshy"));
  var ctaTxt = el("div");
  var ctaTitle = el("div", "hw-cta-title"); ctaTitle.textContent = "Ask Meshy a question";
  var ctaSub = el("div", "hw-cta-sub"); ctaSub.textContent = "AI-powered product search · instant answers";
  ctaTxt.appendChild(ctaTitle); ctaTxt.appendChild(ctaSub);
  var ctaArrow = el("div", "hw-cta-arrow"); ctaArrow.textContent = "›";
  cta.appendChild(ctaAv); cta.appendChild(ctaTxt); cta.appendChild(ctaArrow);
  cta.onclick = showChat;

  // Quick links
  var qaList = el("div", "hw-qa-list");
  QUICK_LINKS.forEach(function(lnk) {
    var item = a(lnk.url, "hw-qa-item");
    var icon = el("div", "hw-qa-icon " + lnk.color); icon.textContent = lnk.icon;
    var lbl  = el("div", "hw-qa-lbl");
    var t = el("div", "hw-qa-title"); t.textContent = lnk.title;
    var s = el("div", "hw-qa-sub");   s.textContent = lnk.sub;
    lbl.appendChild(t); lbl.appendChild(s);
    var chev = el("div", "hw-qa-chev"); chev.textContent = "›";
    item.appendChild(icon); item.appendChild(lbl); item.appendChild(chev);
    qaList.appendChild(item);
  });

  homeBody.appendChild(greeting);
  homeBody.appendChild(sub);
  homeBody.appendChild(cta);
  homeBody.appendChild(qaList);

  var homeFoot = el("div", "hw-home-foot");
  var homeFootA = a("https://howard-wire-cloth-co.myshopify.com");
  homeFootA.textContent = "howardwire.com";
  homeFoot.appendChild(document.createTextNode("Howard Wire Cloth Co. · "));
  homeFoot.appendChild(homeFootA);

  homeView.appendChild(hero);
  homeView.appendChild(homeBody);
  homeView.appendChild(homeFoot);

  /* ── CHAT VIEW ── */
  var chatView = el("div", "hw-view hw-hidden");
  chatView.id = "hw-chat-view";

  var chatHdr = el("div", "hw-chat-hdr");
  var backBtn = el("button", "hw-back");
  backBtn.textContent = "‹"; backBtn.setAttribute("aria-label","Back");
  backBtn.onclick = showHome;
  var chAv = el("div", "hw-ch-av"); chAv.appendChild(img(MESHY_HEADER,"Meshy"));
  var chInfo = el("div", "hw-ch-info");
  var chName = el("div", "hw-ch-name"); chName.textContent = "Meshy";
  var chStatus = el("div", "hw-ch-status"); chStatus.textContent = "Online · Howard Wire Product Expert";
  chInfo.appendChild(chName); chInfo.appendChild(chStatus);
  var chClose = el("button", "hw-ch-close");
  chClose.textContent = "×"; chClose.setAttribute("aria-label","Close");
  chClose.onclick = close;
  chatHdr.appendChild(backBtn); chatHdr.appendChild(chAv);
  chatHdr.appendChild(chInfo); chatHdr.appendChild(chClose);

  var msgsEl = el("div", "hw-msgs"); msgsEl.id = "hw-msgs-el";

  var sugsEl = el("div", "hw-sugs");
  ["Stainless steel mesh","1/4\" wire cloth","Galvanized welded wire","Talk to sales"].forEach(function(s) {
    var b = el("button", "hw-sug"); b.textContent = s;
    b.onclick = function() { inp.value = s; sendMsg(); };
    sugsEl.appendChild(b);
  });

  var inpRow = el("div", "hw-inp-row");
  var inp = document.createElement("textarea");
  inp.className = "hw-inp"; inp.rows = 1;
  inp.placeholder = "Ask Meshy anything about wire mesh…";
  inp.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMsg(); }
  });
  inp.addEventListener("input", function() {
    inp.style.height = "auto";
    inp.style.height = Math.min(inp.scrollHeight, 100) + "px";
  });
  var sendBtn = el("button", "hw-send");
  sendBtn.setAttribute("aria-label","Send");
  sendBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>';
  sendBtn.onclick = sendMsg;
  inpRow.appendChild(inp); inpRow.appendChild(sendBtn);

  var chatFoot = el("div", "hw-chat-foot");
  var chatFootA = a("https://howard-wire-cloth-co.myshopify.com");
  chatFootA.textContent = "howardwire.com";
  chatFoot.appendChild(document.createTextNode("Howard Wire Cloth Co. · "));
  chatFoot.appendChild(chatFootA);

  chatView.appendChild(chatHdr);
  chatView.appendChild(msgsEl);
  chatView.appendChild(sugsEl);
  chatView.appendChild(inpRow);
  chatView.appendChild(chatFoot);

  panel.appendChild(homeView);
  panel.appendChild(chatView);
  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  // ── State ────────────────────────────────────────────────────
  var messages = [], isOpen = false, isBusy = false;
  var WELCOME = "Hey! I'm **Meshy** — I know Howard Wire's entire catalog inside and out. 🧡\n\nTell me what you're working on — material, opening size, application — and I'll find exactly what you need. What are you looking for?";

  function open()  {
    panel.classList.add("hw-open");
    launcher.classList.remove("hw-unread");
    isOpen = true;
  }
  function close() { panel.classList.remove("hw-open"); isOpen = false; }
  function toggle(){ isOpen ? close() : open(); }

  function showChat() {
    homeView.classList.add("hw-hidden");
    chatView.classList.remove("hw-hidden");
    if (messages.length === 0) addBot(WELCOME);
    setTimeout(function(){ inp.focus(); }, 100);
  }
  function showHome() {
    chatView.classList.add("hw-hidden");
    homeView.classList.remove("hw-hidden");
  }

  // ── Messages ─────────────────────────────────────────────────
  function scrollEnd() { msgsEl.scrollTop = msgsEl.scrollHeight; }

  function addBot(text) {
    var d = el("div", "hw-msg hw-bot");
    d.innerHTML = md(text);
    msgsEl.appendChild(d); scrollEnd();
    if (!isOpen) launcher.classList.add("hw-unread");
  }
  function addUser(text) {
    var d = el("div", "hw-msg hw-user");
    d.textContent = text;
    msgsEl.appendChild(d); scrollEnd();
  }
  function showTyping() {
    var d = el("div", "hw-typing"); d.id = "hw-typing-el";
    d.innerHTML = "<span></span><span></span><span></span>";
    msgsEl.appendChild(d); scrollEnd();
  }
  function hideTyping() { var t = document.getElementById("hw-typing-el"); if(t) t.remove(); }
  function hideSugs()   { sugsEl.style.display = "none"; }

  async function sendMsg() {
    var text = inp.value.trim();
    if (!text || isBusy) return;
    isBusy = true; sendBtn.disabled = true;
    hideSugs(); addUser(text);
    inp.value = ""; inp.style.height = "auto";
    messages.push({ role:"user", content:text });
    showTyping();
    try {
      var res  = await fetch(API_URL, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ messages: messages })
      });
      var data = await res.json();
      hideTyping();
      var reply = data.reply || "Something went wrong — try again!";
      addBot(reply);
      messages.push({ role:"assistant", content:reply });
    } catch(e) {
      hideTyping();
      addBot("Connection error. Please refresh and try again.");
    } finally {
      isBusy = false; sendBtn.disabled = false; inp.focus();
    }
  }

  // ── Markdown renderer ────────────────────────────────────────
  function md(t) {
    t = t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    t = t.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
    t = t.replace(/\*(.+?)\*/g,"<em>$1</em>");
    t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
    t = t.replace(/^[-•] (.+)$/gm,"<li>$1</li>");
    t = t.replace(/(<li>[\s\S]+?<\/li>)/g,"<ul>$1</ul>");
    t = t.replace(/\n\n/g,"</p><p>").replace(/\n/g,"<br>");
    return "<p>" + t + "</p>";
  }
})();
