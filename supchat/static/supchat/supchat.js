/* django-supchat visitor widget. Vanilla JS, no build step. All user content is rendered with textContent. */
(function () {
  'use strict';

  var I = window.SupchatI18n, Snd = window.SupchatSound, NS = 'http://www.w3.org/2000/svg';
  var LS = { get: function (k, d) { try { return localStorage.getItem(k) || d; } catch (_) { return d; } }, set: function (k, v) { try { localStorage.setItem(k, v); } catch (_) { /* ignore */ } } };

  function h(tag, props) {
    var n = document.createElement(tag), kids = Array.prototype.slice.call(arguments, 2);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k]; if (v == null || v === false) return;
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v;
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
      else if (k === 'style') n.style.cssText = v; else if (v === true) n.setAttribute(k, ''); else n.setAttribute(k, v);
    });
    kids.flat().forEach(function (c) { if (c != null && c !== false) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function ic(name, cls) {
    var s = document.createElementNS(NS, 'svg'), u = document.createElementNS(NS, 'use');
    s.setAttribute('class', 'ic ' + (cls || '')); s.setAttribute('aria-hidden', 'true'); u.setAttribute('href', '#sc-' + name); s.appendChild(u); return s;
  }
  function debounce(fn, ms) { var id; return function () { var a = arguments; clearTimeout(id); id = setTimeout(function () { fn.apply(null, a); }, ms); }; }
  function fire(name, detail) { document.dispatchEvent(new CustomEvent(name, { detail: detail })); }
  function dayKey(iso) { var d = new Date(iso); return d.getFullYear() + '-' + d.getMonth() + '-' + d.getDate(); }
  function fmtSize(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }

  function init(root) {
    if (root.dataset.ready) return; root.dataset.ready = '1';
    var cfg = {}; try { cfg = JSON.parse(root.dataset.config || '{}'); } catch (_) { /* default */ }
    var BASE = cfg.startUrl.replace(/start\/?$/, '');
    var panel = root.querySelector('[data-sc="panel"]'), toggle = root.querySelector('[data-sc="toggle"]'), badge = root.querySelector('[data-sc="badge"]');
    var langs = (cfg.languages && cfg.languages.length) ? cfg.languages : I.languages;
    var lang = I.detect(LS.get('supchat.lang', null) || (cfg.language !== 'auto' ? cfg.language : null), langs);
    var theme = LS.get('supchat.theme', cfg.theme || 'auto');
    var S = { conv: null, msgs: [], els: new Map(), reply: null, file: null, typing: false, unread: 0, hasOlder: false, closed: false, online: 0, aiOn: !!cfg.ai, token: LS.get('supchat.token', ''), nearBottom: true };
    var es = null, ui = {}, typingTimer = null, typingSent = 0, tempId = 0, built = false;

    function t(k, v) { return I.t(lang, k, v); }
    var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    function applyTheme() {
      var dark = theme === 'dark' || (theme === 'auto' && mq && mq.matches);
      root.classList.toggle('sc-dark', dark);
      if (cfg.accent) root.style.setProperty('--sc-accent', cfg.accent);
    }
    if (mq && mq.addEventListener) mq.addEventListener('change', applyTheme);
    function applyLang() {
      var m = I.META[lang]; root.setAttribute('dir', m.dir); root.setAttribute('lang', lang); panel.setAttribute('dir', m.dir);
      toggle.setAttribute('aria-label', t('openChat'));
    }
    applyTheme(); applyLang();

    /* ---------------------------------------------------------------- network */
    function csrf() {
      var i = root.querySelector('input[name="csrfmiddlewaretoken"]'); if (i && i.value) return i.value;
      var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : '';
    }
    async function api(path, opts) {
      opts = opts || {}; var headers = { 'X-CSRFToken': csrf() }, body;
      if (opts.form) body = opts.form; else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body); }
      var res = await fetch(path, { method: opts.method || (body !== undefined ? 'POST' : 'GET'), headers: headers, body: body, credentials: 'same-origin' });
      var data = {}; try { data = await res.json(); } catch (_) { /* ignore */ }
      if (!res.ok || data.ok === false) { var e = new Error(data.error || t('error')); e.status = res.status; throw e; }
      return data;
    }
    function ep(suffix) { return BASE + 'conversations/' + S.conv.id + '/' + suffix; }
    function setStatus(msg, err) { if (ui.status) { ui.status.textContent = msg || ''; ui.status.className = 'sc-status' + (err ? ' err' : ''); } }

    /* ------------------------------------------------------------------ build */
    function build() {
      if (built) return; built = true; panel.textContent = '';
      ui.title = h('b', { text: cfg.title }); ui.sub = h('small'); ui.dot = h('i');
      ui.menuBtn = h('button', { class: 'sc-ib', type: 'button', 'aria-label': t('menu'), 'aria-haspopup': 'true', onclick: function (e) { e.stopPropagation(); toggleMenu(); } }, ic('more'));
      ui.langBtn = h('button', { class: 'sc-ib', type: 'button', 'aria-label': t('language') + ': ' + I.META[lang].native, title: t('language'), onclick: function (e) { e.stopPropagation(); if (ui.menu) closeMenu(); else langMenu(); } }, ic('globe'));
      var head = h('header', { class: 'sc-head' }, h('div', { class: 'sc-av' }, ic('user'), ui.dot), h('div', { class: 'sc-ttl' }, ui.title, ui.sub), ui.langBtn, ui.menuBtn,
        h('button', { class: 'sc-ib', type: 'button', 'aria-label': t('closeChat'), onclick: closePanel }, ic('x')));
      ui.msgs = h('div', { class: 'sc-msgs', role: 'log', 'aria-live': 'polite', tabindex: 0 }); ui.msgs.addEventListener('scroll', onScroll);
      ui.status = h('div', { class: 'sc-status', role: 'status' });
      ui.body = h('div', { class: 'sc-body' }, ui.msgs, ui.status);
      ui.pop = h('div'); ui.barHost = h('div');
      ui.input = h('textarea', { rows: 1, maxlength: cfg.maxLength || 2000, placeholder: t('typeMessage'), 'aria-label': t('typeMessage') });
      ui.send = h('button', { class: 'sc-send', type: 'button', disabled: true, 'aria-label': t('send'), onclick: send }, ic('send'));
      ui.fileIn = h('input', { type: 'file', hidden: true, onchange: function (e) { var f = e.target.files[0]; if (f) pickFile(f); e.target.value = ''; } });
      ui.row = h('div', { class: 'sc-row' }, h('div', { class: 'sc-box' },
        h('button', { class: 'sc-ib', type: 'button', 'aria-label': t('emoji'), onclick: emojiPop }, ic('smile')), ui.input,
        cfg.attachments ? h('button', { class: 'sc-ib', type: 'button', 'aria-label': t('attach'), onclick: function () { ui.fileIn.click(); } }, ic('clip')) : null, ui.fileIn), ui.send);
      ui.foot = h('div', { class: 'sc-foot' }, t('poweredBy') + ' ', h('a', { href: 'https://github.com/xo-aria/django-supchat', target: '_blank', rel: 'noopener', text: 'SupChat' }));
      ui.comp = h('div', { class: 'sc-comp' }, ui.pop, ui.barHost, ui.row, ui.foot);
      panel.append(head, ui.body, ui.comp);
      ui.input.addEventListener('input', function () { autosize(); syncSend(); onTyping(); });
      ui.input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } if (e.key === 'Escape') { S.reply = null; renderBar(); ui.pop.textContent = ''; } });
      ui.input.addEventListener('paste', function (e) { var f = e.clipboardData && e.clipboardData.files[0]; if (f && cfg.attachments) { e.preventDefault(); pickFile(f); } });
      panel.addEventListener('click', function (e) { if (ui.menu && !ui.menu.contains(e.target)) closeMenu(); });
      renderHeader(); renderSkeleton();
    }
    function renderSkeleton() { ui.msgs.textContent = ''; var box = h('div', { class: 'sc-empty', 'aria-hidden': 'true', style: 'display:flex;flex-direction:column;margin-top:auto' }); [58, 40, 66].forEach(function (w, i) { box.appendChild(h('div', { class: 'sc-sk', style: 'width:' + w + '%;align-self:' + (i % 2 ? 'flex-end' : 'flex-start') })); }); ui.msgs.appendChild(box); }
    function renderHeader() {
      if (!ui.sub) return;
      ui.title.textContent = cfg.title;
      ui.dot.className = S.online ? 'on' : ''; ui.sub.textContent = S.online ? t('online') : t('offline');
      if (S.aiOn && !S.operatorSeen) ui.sub.appendChild(h('span', { class: 'sc-pill', text: t('aiBadge') }));
    }
    function renderEmpty() {
      if (!ui.msgs || S.msgs.length || S.closed) return;
      var old = ui.msgs.querySelector('.sc-empty'); if (old) old.remove();
      var box = h('div', { class: 'sc-empty', style: 'display:flex;flex-direction:column;gap:6px;margin-top:auto' });
      box.appendChild(h('div', { class: 'sc-msg them', style: 'animation-delay:.05s' }, h('div', { class: 'sc-bub', text: cfg.welcome || t('welcome'), dir: 'auto' })));
      if (S.aiOn) box.appendChild(h('div', { class: 'sc-note', text: t('aiNote') }));
      if (cfg.quickReplies && cfg.quickReplies.length) { var qr = h('div', { class: 'sc-qr' }); cfg.quickReplies.forEach(function (q) { qr.appendChild(h('button', { type: 'button', text: q, onclick: function () { ui.input.value = q; send(); } })); }); box.appendChild(qr); }
      ui.msgs.appendChild(box);
    }

    /* ------------------------------------------------------------------- menu */
    function closeMenu() { if (ui.menu) { ui.menu.remove(); ui.menu = null; } }
    function toggleMenu() {
      if (ui.menu) return closeMenu();
      var items = [
        { icon: theme === 'dark' ? 'moon' : 'sun', label: t('theme') + ': ' + t({ auto: 'themeAuto', light: 'themeLight', dark: 'themeDark' }[theme]), run: function () { theme = { auto: 'light', light: 'dark', dark: 'auto' }[theme]; LS.set('supchat.theme', theme); applyTheme(); } },
        { icon: Snd.enabled() ? 'vol' : 'mute', label: Snd.enabled() ? t('soundOn') : t('soundOff'), run: function () { Snd.setEnabled(!Snd.enabled()); if (Snd.enabled()) Snd.play('incoming'); } }
      ];
      if (S.conv && S.msgs.length) {
        items.push('-', { icon: 'download', label: t('downloadTranscript'), run: function () { location.href = ep('transcript/'); } }, { icon: 'mail', label: t('emailTranscript'), run: emailTranscript });
        if (!S.closed) items.push('-', { icon: 'x', label: t('endChat'), danger: true, run: endChat });
      }
      drawMenu(items);
    }
    function drawMenu(items) {
      closeMenu(); ui.menu = h('div', { class: 'sc-menu', role: 'menu' });
      items.forEach(function (it) {
        if (it === '-') return ui.menu.appendChild(h('hr'));
        ui.menu.appendChild(h('button', { type: 'button', role: 'menuitem', class: (it.danger ? 'danger ' : '') + (it.sel ? 'sel' : ''), onclick: function (e) { e.stopPropagation(); if (!it.keep) closeMenu(); it.run(); } }, it.icon ? ic(it.icon, 'sm') : null, it.label));
      });
      panel.appendChild(ui.menu);
    }
    function langMenu() { drawMenu(langs.map(function (l) { return { label: I.META[l].native, sel: l === lang, run: function () { lang = l; LS.set('supchat.lang', l); applyLang(); rebuild(); } }; })); }
    function rebuild() { built = false; ui = {}; var keep = S.msgs.slice(); S.els.clear(); S.msgs = []; build(); keep.forEach(function (m) { addMessage(m, true); }); renderEmpty(); scrollBottom(true); syncSend(); if (S.closed) showClosed(); }
    async function emailTranscript() {
      if (!S.conv.visitor_email) return askEmail();
      try { await api(ep('transcript/email/'), { body: {} }); setStatus(t('transcriptSent')); }
      catch (e) { if (/email/i.test(e.message)) askEmail(); else setStatus(e.message, true); }
    }
    function askEmail() {
      var inp = h('input', { type: 'email', placeholder: t('typeEmail'), autocomplete: 'email' });
      var card = h('div', { class: 'sc-card' }, h('h3', { text: t('emailTranscript') }), inp,
        h('button', { class: 'sc-btn', type: 'button', text: t('send'), onclick: async function () { try { await api(ep('transcript/email/'), { body: { email: inp.value } }); card.remove(); setStatus(t('transcriptSent')); } catch (e) { setStatus(e.message, true); } } }),
        h('button', { class: 'sc-btn ghost', type: 'button', text: t('cancel'), onclick: function () { card.remove(); } }));
      ui.body.appendChild(card); inp.focus();
    }
    function endChat() {
      var card = h('div', { class: 'sc-card', role: 'alertdialog', 'aria-label': t('endChatConfirm') });
      var yes = h('button', { class: 'sc-btn', type: 'button', text: t('endChat'), onclick: async function () {
        try { await api(ep('close/'), { body: {} }); card.remove(); S.closed = true; showClosed(); } catch (e) { setStatus(e.message, true); }
      } });
      card.append(h('h3', { text: t('endChatConfirm') }), yes,
        h('button', { class: 'sc-btn ghost', type: 'button', text: t('cancel'), onclick: function () { card.remove(); ui.input.focus(); } }));
      ui.body.appendChild(card); yes.focus();
    }

    /* ---------------------------------------------------------------- session */
    async function start() {
      if (S.conv) return S.conv;
      setStatus(t('connecting'));
      try {
        var d = await api(cfg.startUrl, { body: { locale: lang } });
        S.conv = d.conversation; S.closed = S.conv.status === 'closed'; setStatus('');
        var cf = await fetch(cfg.configUrl, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).catch(function () { return {}; });
        S.online = cf.operators_online || 0; renderHeader();
        await loadMessages(); connect();
        if (cfg.prechat && !S.conv.visitor_name && !S.msgs.length && !S.conv.visitor_email) showPrechat();
        if (S.closed) showClosed();
        return S.conv;
      } catch (e) { setStatus(e.message, true); return null; }
    }
    async function loadMessages() {
      var d = await api(ep('messages/')); S.msgs = []; S.els.clear(); ui.msgs.textContent = '';
      d.messages.forEach(function (m) { addMessage(m, true); }); S.hasOlder = d.has_more;
      S.operatorSeen = d.messages.some(function (m) { return m.sender_type === 'operator'; });
      if (!S.msgs.length) renderEmpty(); renderHeader(); scrollBottom(true);
    }
    async function loadOlder() {
      if (S.loadingOlder || !S.msgs.length) return; S.loadingOlder = true;
      try {
        var d = await api(ep('messages/') + '?before=' + S.msgs[0].id), before = ui.msgs.scrollHeight, keep = S.msgs;
        S.msgs = []; S.els.clear(); ui.msgs.textContent = ''; d.messages.concat(keep).forEach(function (m) { addMessage(m, true); }); S.hasOlder = d.has_more;
        ui.msgs.style.scrollBehavior = 'auto'; ui.msgs.scrollTop = ui.msgs.scrollHeight - before;
      } catch (e) { /* ignore */ } finally { S.loadingOlder = false; }
    }
    function showPrechat() {
      var name = h('input', { type: 'text', placeholder: t('prechatName'), maxlength: 80, autocomplete: 'name' }), mail = h('input', { type: 'email', placeholder: t('prechatEmail'), autocomplete: 'email' });
      var card = h('div', { class: 'sc-card' }, h('h3', { text: t('prechatTitle') }), name, mail,
        h('button', { class: 'sc-btn', type: 'button', text: t('startChat'), onclick: async function () {
          try { var d = await api(ep('profile/'), { body: { name: name.value, email: mail.value } }); S.conv = d.conversation; card.remove(); ui.input.focus(); } catch (e) { setStatus(e.message, true); } } }));
      ui.body.appendChild(card); name.focus();
    }
    function showClosed() {
      if (!ui.body || ui.body.querySelector('.sc-card')) return;
      ui.comp.hidden = true; var card;
      var again = h('button', { class: 'sc-btn', type: 'button', text: t('newChat'), onclick: function () { card.remove(); S.conv = null; S.closed = false; S.msgs = []; S.els.clear(); ui.msgs.textContent = ''; if (es) es.close(); es = null; ui.comp.hidden = false; start(); } });
      if (S.conv && S.conv.rating == null) {
        var chosen = 0, comment = h('textarea', { placeholder: t('rateComment'), maxlength: 500 }), stars = h('div', { class: 'sc-stars', role: 'radiogroup' });
        var paint = function () { Array.prototype.forEach.call(stars.children, function (b, i) { b.className = i < chosen ? 'on' : ''; }); };
        for (var i = 1; i <= 5; i++) (function (n) { stars.appendChild(h('button', { type: 'button', role: 'radio', 'aria-label': String(n), text: '★', onclick: function () { chosen = n; paint(); } })); })(i);
        var submit = h('button', { class: 'sc-btn', type: 'button', text: t('submit'), onclick: async function () {
          if (!chosen) return; try { await api(ep('rate/'), { body: { rating: chosen, comment: comment.value } }); S.conv.rating = chosen; card.replaceChildren(h('h3', { text: t('rateThanks') }), again); } catch (e) { setStatus(e.message, true); } } });
        card = h('div', { class: 'sc-card' }, h('p', { text: t('conversationClosed') }), h('h3', { text: t('rateTitle') }), stars, comment, submit, h('button', { class: 'sc-btn ghost', type: 'button', text: t('skip'), onclick: function () { card.replaceChildren(again); } }));
      } else card = h('div', { class: 'sc-card' }, h('p', { text: t('conversationClosed') }), again);
      ui.body.appendChild(card);
    }

    /* --------------------------------------------------------------- messages */
    function addMessage(m, bulk) {
      if (S.els.has(m.id)) return;
      var empty = ui.msgs.querySelector('.sc-empty'); if (empty) empty.remove();
      var prev = S.msgs[S.msgs.length - 1], newDay = !prev || dayKey(prev.created_at) !== dayKey(m.created_at);
      if (newDay) ui.msgs.appendChild(h('div', { class: 'sc-day', text: dayLabel(m.created_at) }));
      var mine = m.sender_type === 'guest' || m.sender_type === 'user';
      var grouped = !newDay && prev && prev.sender_type === m.sender_type && (new Date(m.created_at) - new Date(prev.created_at)) < 3e5;
      var node = buildMsg(m, mine, grouped);
      var typing = ui.typingEl; if (typing && typing.parentNode) ui.msgs.insertBefore(node, typing); else ui.msgs.appendChild(node);
      S.els.set(m.id, node); S.msgs.push(m);
      if (m.sender_type === 'operator') { S.operatorSeen = true; renderHeader(); }
      if (!bulk && S.nearBottom) scrollBottom();
    }
    function dayLabel(iso) {
      var d = new Date(iso), n = new Date();
      if (dayKey(iso) === dayKey(n.toISOString())) return t('today'); if (dayKey(iso) === dayKey(new Date(Date.now() - 864e5).toISOString())) return t('yesterday');
      return d.toLocaleDateString(I.META[lang].locale, { day: 'numeric', month: 'long' });
    }
    function buildMsg(m, mine, grouped) {
      var bub = h('div', { class: 'sc-bub' });
      if (!mine && !grouped) bub.appendChild(h('div', { class: 'sc-who' }, m.sender_type === 'bot' ? (m.sender_name || cfg.botName) : (m.sender_type === 'operator' && m.sender_name ? m.sender_name : t('support')), m.sender_type === 'bot' ? h('em', { text: 'AI' }) : null));
      if (m.reply_to) bub.appendChild(h('span', { class: 'sc-quote', text: m.reply_to.text, dir: 'auto', onclick: function () { var n = S.els.get(m.reply_to.id); if (n) n.scrollIntoView({ block: 'center', behavior: 'smooth' }); } }));
      if (m.attachment) {
        if (m.attachment.is_image) bub.appendChild(h('img', { class: 'sc-img', src: m.attachment.url, alt: m.attachment.name, loading: 'lazy', onclick: function () { lightbox(m.attachment.url); }, onload: function () { if (S.nearBottom) scrollBottom(true); } }));
        else bub.appendChild(h('a', { class: 'sc-file', href: m.attachment.url + '?download=1', target: '_blank', rel: 'noopener' }, h('span', { class: 'fi' }, ic('note', 'sm')), h('span', {}, h('b', { text: m.attachment.name }), h('small', { text: fmtSize(m.attachment.size) }))));
      }
      if (m.text) bub.appendChild(h('span', { dir: 'auto', text: m.text }));
      var time = new Date(m.created_at).toLocaleTimeString(I.META[lang].locale, { hour: '2-digit', minute: '2-digit' });
      var meta = h('span', { class: 'sc-meta' }, time); if (mine) meta.appendChild(ic(m.is_read ? 'checks' : 'check', m.is_read ? 'seen' : '')); bub.appendChild(meta);
      var node = h('div', { class: 'sc-msg ' + (mine ? 'me' : 'them') + (grouped ? '' : ' gap'), tabindex: 0, onclick: function (e) { if (e.target.closest('.sc-tools')) return; node.classList.toggle('tools'); } }, bub, reactsNode(m),
        h('div', { class: 'sc-tools' },
          h('button', { type: 'button', 'aria-label': t('replyTo'), title: t('replyTo'), onclick: function () { S.reply = m; renderBar(); ui.input.focus(); } }, ic('reply', 'sm')),
          h('button', { type: 'button', 'aria-label': t('react'), title: t('react'), onclick: function (e) { reactBar(e.currentTarget, m); } }, ic('smile', 'sm'))));
      return node;
    }
    function reactsNode(m) {
      var box = h('div', { class: 'sc-reacts' });
      (m.reactions || []).forEach(function (r) { box.appendChild(h('button', { class: 'sc-react' + (r.by.indexOf('visitor') > -1 ? ' mine' : ''), type: 'button', onclick: function (e) { e.stopPropagation(); react(m.id, r.emoji); } }, r.emoji, h('span', { text: String(r.count) }))); });
      return box;
    }
    function reactBar(anchor, m) {
      ui.pop.textContent = ''; var bar = h('div', { class: 'sc-pop', style: 'display:flex;justify-content:space-around' });
      (cfg.reactions || []).forEach(function (e) { bar.appendChild(h('button', { type: 'button', style: 'font-size:22px;width:34px;height:34px', text: e, onclick: function () { ui.pop.textContent = ''; react(m.id, e); } })); });
      ui.pop.appendChild(bar);
    }
    async function react(id, emoji) { try { await api(ep('react/'), { body: { message_id: id, emoji: emoji } }); } catch (e) { setStatus(e.message, true); } }
    function lightbox(url) { var box = h('div', { class: 'sc-lightbox', onclick: function () { box.remove(); } }, h('img', { src: url, alt: '' })); root.appendChild(box); }
    function onScroll() {
      var s = ui.msgs; S.nearBottom = s.scrollHeight - s.scrollTop - s.clientHeight < 100;
      if (S.nearBottom && ui.jump) { ui.jump.remove(); ui.jump = null; } else if (!S.nearBottom && !ui.jump) { ui.jump = h('button', { class: 'sc-jump', type: 'button', 'aria-label': t('scrollDown'), onclick: function () { scrollBottom(); } }, ic('down')); ui.body.appendChild(ui.jump); }
      if (s.scrollTop < 30 && S.hasOlder) loadOlder();
    }
    function scrollBottom(instant) { var s = ui.msgs; if (!s) return; s.style.scrollBehavior = instant ? 'auto' : 'smooth'; requestAnimationFrame(function () { s.scrollTop = s.scrollHeight; S.nearBottom = true; }); }
    function showTyping(on) {
      if (!ui.msgs) return;
      if (on && !ui.typingEl) { ui.typingEl = h('div', { class: 'sc-msg them gap' }, h('div', { class: 'sc-bub' }, h('span', { class: 'sc-dots' }, h('i'), h('i'), h('i')))); ui.msgs.appendChild(ui.typingEl); if (S.nearBottom) scrollBottom(); }
      if (!on && ui.typingEl) { ui.typingEl.remove(); ui.typingEl = null; }
      if (ui.sub) ui.sub.textContent = on ? t('typing') : (S.online ? t('online') : t('offline'));
    }

    /* --------------------------------------------------------------- composer */
    function autosize() { ui.input.style.height = 'auto'; ui.input.style.height = Math.min(ui.input.scrollHeight, 110) + 'px'; }
    function syncSend() { if (ui.send) ui.send.disabled = !ui.input.value.trim() && !S.file; }
    function renderBar() {
      ui.barHost.textContent = '';
      if (S.reply) ui.barHost.appendChild(h('div', { class: 'sc-bar' }, ic('reply', 'sm'), h('span', { dir: 'auto', text: (S.reply.text || (S.reply.attachment && S.reply.attachment.name) || '').slice(0, 80) }), h('button', { class: 'sc-ib', style: 'color:inherit;width:24px;height:24px', type: 'button', 'aria-label': t('cancel'), onclick: function () { S.reply = null; renderBar(); } }, ic('x', 'xs'))));
      if (S.file) ui.barHost.appendChild(h('div', { class: 'sc-bar' }, ic('clip', 'sm'), h('span', { text: S.file.name + ' · ' + fmtSize(S.file.size) }), h('button', { class: 'sc-ib', style: 'color:inherit;width:24px;height:24px', type: 'button', 'aria-label': t('cancel'), onclick: function () { S.file = null; renderBar(); syncSend(); } }, ic('x', 'xs'))));
    }
    function pickFile(f) { if (f.size > (cfg.maxMb || 5) * 1048576) return setStatus(t('fileTooLarge'), true); S.file = f; renderBar(); syncSend(); setStatus(''); }
    function emojiPop() {
      if (ui.pop.firstChild) { ui.pop.textContent = ''; return; }
      var set = '😀 😃 😄 😁 😅 😂 🙂 😉 😊 😍 🥰 😘 😎 🤔 😐 😴 😢 😭 😡 😱 🙏 👍 👎 👏 🙌 💪 👋 ✅ ❌ ⭐ 🔥 🎉 ❤️ 💙 💡 📎 ⏰ ☕ 🚀'.split(' '), grid = h('div', { class: 'sc-emojis' });
      set.forEach(function (e) { grid.appendChild(h('button', { type: 'button', text: e, onclick: function () { var i = ui.input, a = i.selectionStart; i.value = i.value.slice(0, a) + e + i.value.slice(i.selectionEnd); i.selectionStart = i.selectionEnd = a + e.length; i.focus(); syncSend(); } })); });
      ui.pop.appendChild(h('div', { class: 'sc-pop' }, grid));
    }
    function onTyping() {
      if (!S.conv || !ui.input.value.trim()) return; var now = Date.now();
      if (now - typingSent > 3000) { typingSent = now; api(ep('typing/'), { body: { is_typing: true } }).catch(function () {}); }
      clearTimeout(typingTimer); typingTimer = setTimeout(function () { typingSent = 0; api(ep('typing/'), { body: { is_typing: false } }).catch(function () {}); }, 4000);
    }
    async function send() {
      var text = ui.input.value.trim(); if (!text && !S.file) return;
      var conv = await start(); if (!conv || S.closed) return;
      var file = S.file, reply = S.reply, tid = 'tmp' + (++tempId);
      ui.input.value = ''; autosize(); S.file = null; S.reply = null; renderBar(); syncSend(); ui.pop.textContent = '';
      var ghost = h('div', { class: 'sc-msg me gap sending', 'data-tmp': tid }, h('div', { class: 'sc-bub' }, h('span', { dir: 'auto', text: text || (file ? file.name : '') }), h('span', { class: 'sc-meta' }, t('uploading').replace('…', ''))));
      var empty = ui.msgs.querySelector('.sc-empty'); if (empty) empty.remove(); ui.msgs.appendChild(ghost); scrollBottom();
      try {
        var fd = new FormData(); fd.append('text', text); if (file) fd.append('file', file); if (reply) fd.append('reply_to', reply.id);
        var d = await api(ep('messages/'), { form: fd }); ghost.remove(); addMessage(d.message); Snd.play('outgoing'); scrollBottom();
        fire('supchat:message', d.message);
      } catch (e) {
        ghost.className = 'sc-msg me gap failed'; ghost.querySelector('.sc-meta').textContent = t('failedToSend'); setStatus(e.message, true);
        ghost.addEventListener('click', function () { ghost.remove(); ui.input.value = text; syncSend(); });
      }
    }

    /* --------------------------------------------------------------- realtime */
    function connect() {
      if (!S.conv || es) return;
      es = new EventSource(ep('events/'), { withCredentials: true });
      var on = function (n, fn) { es.addEventListener(n, function (e) { try { fn(JSON.parse(e.data)); } catch (_) { /* ignore */ } }); };
      es.onerror = function () { setStatus(t('reconnecting')); }; es.onopen = function () { setStatus(''); };
      on('message.created', function (m) {
        var mine = m.sender_type === 'guest' || m.sender_type === 'user'; showTyping(false); addMessage(m);
        if (mine) return;
        fire('supchat:message', m);
        if (isOpen()) { if (document.visibilityState === 'visible') api(ep('read/'), { body: {} }).catch(function () {}); Snd.play('incoming'); }
        else { S.unread++; badge.textContent = S.unread > 99 ? '99+' : String(S.unread); badge.hidden = false; toggle.classList.remove('sc-wiggle'); void toggle.offsetWidth; toggle.classList.add('sc-wiggle'); Snd.play('notify'); }
      });
      on('message.read', function (d) { d.message_ids.forEach(function (id) { var m = S.msgs.filter(function (x) { return x.id === id; })[0]; if (m && (m.sender_type === 'guest' || m.sender_type === 'user')) { m.is_read = true; var n = S.els.get(id), c = n && n.querySelector('.sc-meta .ic'); if (c) c.replaceWith(ic('checks', 'seen')); } }); });
      on('reaction.updated', function (d) { var m = S.msgs.filter(function (x) { return x.id === d.message_id; })[0], n = S.els.get(d.message_id); if (m && n) { m.reactions = d.reactions; n.querySelector('.sc-reacts').replaceWith(reactsNode(m)); } });
      var tm; on('typing.start', function (d) { if (d.sender_type === 'guest' || d.sender_type === 'user') return; showTyping(true); clearTimeout(tm); tm = setTimeout(function () { showTyping(false); }, 6000); });
      on('typing.stop', function (d) { if (d.sender_type === 'guest' || d.sender_type === 'user') return; showTyping(false); });
      on('conversation.closed', function () { S.closed = true; showClosed(); });
      on('operator.online', function () { S.online = Math.max(1, S.online); renderHeader(); }); on('operator.offline', function () { S.online = 0; renderHeader(); });
    }

    /* ------------------------------------------------------------- open/close */
    function isOpen() { return !panel.hasAttribute('hidden'); }
    function openPanel() {
      build(); panel.removeAttribute('hidden'); panel.classList.remove('sc-closing'); root.classList.add('sc-open'); toggle.setAttribute('aria-expanded', 'true');
      S.unread = 0; badge.hidden = true; fire('supchat:open');
      start().then(function () { if (S.conv && !S.closed) { ui.input.focus(); api(ep('read/'), { body: {} }).catch(function () {}); } });
    }
    function closePanel() {
      closeMenu(); panel.classList.add('sc-closing'); toggle.setAttribute('aria-expanded', 'false'); root.classList.remove('sc-open'); fire('supchat:close'); toggle.focus({ preventScroll: true });
      setTimeout(function () { if (toggle.getAttribute('aria-expanded') === 'false') panel.setAttribute('hidden', ''); }, 150);
    }
    toggle.addEventListener('click', function () { isOpen() && toggle.getAttribute('aria-expanded') === 'true' ? closePanel() : openPanel(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && isOpen()) { if (ui.menu) closeMenu(); else if (ui.pop && ui.pop.firstChild) ui.pop.textContent = ''; else closePanel(); } });
    window.SupchatWidget = { open: openPanel, close: closePanel };
  }

  function boot() { document.querySelectorAll('[data-supchat]').forEach(init); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
