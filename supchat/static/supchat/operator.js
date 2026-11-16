/* django-supchat operator panel. Vanilla JS, no build step, no external requests.
 * All user content is inserted with textContent / text nodes, never innerHTML.
 * Re-rendering is incremental: theme and language switches never rebuild the app. */
(function () {
  'use strict';

  var I = window.SupchatI18n, Snd = window.SupchatSound;
  var NS = 'http://www.w3.org/2000/svg';
  var BASE = location.pathname.replace(/operator\/?.*$/, '');
  var OP = BASE + 'operator/';
  var LS = { get: function (k, d) { try { return localStorage.getItem(k) || d; } catch (_) { return d; } }, set: function (k, v) { try { localStorage.setItem(k, v); } catch (_) { /* ignore */ } } };

  var S = {
    boot: null, lang: 'en', theme: LS.get('supchat.op.theme', 'auto'), view: 'chats',
    f: { box: 'all', tag: null, prio: null, q: '' }, convs: [], counts: {}, hasMore: false, cursor: null, loading: true, loadingMore: false, settingsTab: 'general',
    active: null, msgs: [], notes: [], hasOlder: false, infoOpen: LS.get('supchat.op.info', '1') === '1',
    reply: null, file: null, typing: {}, analyticsDays: 7
  };
  var el = {};
  var msgEls = new Map();
  var es = null, refreshTimer = null, typingSent = 0, typingStop = null, nearBottom = true;

  /* ---------------------------------------------------------------- helpers */
  function t(k, v) { return I.t(S.lang, k, v); }
  function h(tag, props) {
    var n = document.createElement(tag), kids = Array.prototype.slice.call(arguments, 2);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
      else if (k === 'style') n.style.cssText = v;
      else if (v === true) n.setAttribute(k, '');
      else n.setAttribute(k, v);
    });
    kids.flat().forEach(function (c) { if (c != null && c !== false) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }
  function ic(name, cls) {
    var s = document.createElementNS(NS, 'svg'), u = document.createElementNS(NS, 'use');
    s.setAttribute('class', 'ic ' + (cls || '')); s.setAttribute('aria-hidden', 'true');
    u.setAttribute('href', '#sc-' + name); s.appendChild(u); return s;
  }
  function ib(icon, label, onclick, cls, pressed) {
    return h('button', { class: 'icon-btn ' + (cls || ''), type: 'button', title: label, 'aria-label': label, 'aria-pressed': pressed == null ? null : String(!!pressed), onclick: onclick }, ic(icon, icon === 'back' ? 'flip' : ''));
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function csrf() { var i = $('#csrf'); return i ? i.value : ''; }
  function toast(msg, err) {
    var n = h('div', { class: 'toast' + (err ? ' err' : ''), role: err ? 'alert' : 'status', text: msg }); $('#toasts').appendChild(n);
    setTimeout(function () { n.remove(); }, 3600);
  }
  function quiet(fn) { // run a visual switch without any transition/animation
    var r = document.documentElement; r.classList.add('no-motion'); fn();
    requestAnimationFrame(function () { requestAnimationFrame(function () { r.classList.remove('no-motion'); }); });
  }
  function locale() { return (I.META[S.lang] || I.META.en).locale; }
  function fmtTime(iso) { try { return new Date(iso).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' }); } catch (_) { return ''; } }
  function dayKey(iso) { var d = new Date(iso); return d.getFullYear() + '-' + d.getMonth() + '-' + d.getDate(); }
  function fmtDay(iso) {
    var d = new Date(iso), now = new Date();
    if (dayKey(iso) === dayKey(now.toISOString())) return t('today');
    if (dayKey(iso) === dayKey(new Date(Date.now() - 864e5).toISOString())) return t('yesterday');
    return d.toLocaleDateString(locale(), { day: 'numeric', month: 'long', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' });
  }
  function fmtShort(iso) {
    if (!iso) return '';
    var d = new Date(iso), now = new Date();
    if (dayKey(iso) === dayKey(now.toISOString())) return fmtTime(iso);
    if ((now - d) / 864e5 < 6) return d.toLocaleDateString(locale(), { weekday: 'short' });
    return d.toLocaleDateString(locale(), { day: 'numeric', month: 'short' });
  }
  function fmtFull(iso) { try { return new Date(iso).toLocaleString(locale(), { dateStyle: 'medium', timeStyle: 'short' }); } catch (_) { return ''; } }
  function fmtDur(sec) {
    if (sec == null) return '—';
    if (sec < 60) return I.num(S.lang, Math.round(sec)) + ' ' + t('seconds');
    if (sec < 3600) return I.num(S.lang, Math.round(sec / 60)) + ' ' + t('minutes');
    return I.num(S.lang, Math.round(sec / 360) / 10) + ' ' + t('hours');
  }
  function fmtSize(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }
  function color(name) { var x = 0; for (var i = 0; i < name.length; i++) x = (x * 31 + name.charCodeAt(i)) % 360; return 'hsl(' + x + ',48%,52%)'; }
  function av(name, cls, status) {
    return h('div', { class: 'av ' + (cls || ''), style: 'background:' + color(name || '?'), 'aria-hidden': 'true' }, (name || '?').trim().charAt(0) || '?', status ? h('i', { class: status }) : null);
  }
  function botAv(cls) { return h('div', { class: 'av bot ' + (cls || ''), 'aria-hidden': 'true' }, ic('bolt', 'sm')); }
  function linkify(text) {
    var out = [], re = /(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      out.push(h('a', { href: m[1], target: '_blank', rel: 'noopener noreferrer nofollow', text: m[1] }));
      last = m.index + m[1].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }
  function debounce(fn, ms) { var id; return function () { var a = arguments; clearTimeout(id); id = setTimeout(function () { fn.apply(null, a); }, ms); }; }

  async function api(path, opts) {
    opts = opts || {};
    var headers = { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' }, body;
    if (opts.form) body = opts.form;
    else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body); }
    var res = await fetch(path, { method: opts.method || (body ? 'POST' : 'GET'), headers: headers, body: body, credentials: 'same-origin' });
    var data = {};
    try { data = await res.json(); } catch (_) { /* non json */ }
    if (res.status === 401) { toast(t('sessionExpired'), true); throw new Error('auth'); }
    if (!res.ok || data.ok === false) throw new Error(data.error || t('error'));
    return data;
  }
  function fail(e) { if (e && e.message !== 'auth') toast(e.message, true); }

  /* ----------------------------------------------------- language and theme */
  function applyLang(lang) {
    S.lang = lang; LS.set('supchat.op.lang', lang);
    document.documentElement.lang = lang; document.documentElement.dir = I.META[lang].dir;
  }
  function setLang(lang) { quiet(function () { applyLang(lang); render(); }); }
  function setTheme(th) {
    quiet(function () {
      S.theme = th; LS.set('supchat.op.theme', th); document.documentElement.setAttribute('data-theme', th);
      if (el.themeBtn) el.themeBtn.replaceChildren(ic(themeIcon(), 'lg'));
    });
  }
  function isDark() { return S.theme === 'dark' || (S.theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches); }
  function themeIcon() { return isDark() ? 'moon' : 'sun'; }

  /* ----------------------------------------------------------------- popups */
  function closeLayer() { $('#layer').replaceChildren(); }
  function place(menu, anchor, above) {
    var r = anchor.getBoundingClientRect(), rtl = document.documentElement.dir === 'rtl', w = menu.offsetWidth, hgt = menu.offsetHeight;
    var top = above ? r.top - hgt - 6 : r.bottom + 6;
    if (top + hgt > innerHeight - 8) top = Math.max(8, r.top - hgt - 6);
    menu.style.top = Math.max(8, top) + 'px';
    var left = rtl ? r.right - w : r.left;
    if (anchor.closest('.rail')) left = rtl ? r.left - w - 8 : r.right + 8;
    menu.style.left = Math.max(8, Math.min(left, innerWidth - w - 8)) + 'px';
  }
  function openMenu(anchor, items, title) {
    closeLayer();
    var menu = h('div', { class: 'menu', role: 'menu' });
    if (title) menu.appendChild(h('div', { class: 'label', text: title }));
    items.forEach(function (it) {
      if (it === '-') return menu.appendChild(h('hr'));
      menu.appendChild(h('button', { type: 'button', role: 'menuitem', class: it.danger ? 'danger' : '', onclick: function () { closeLayer(); it.run(); } },
        it.icon ? ic(it.icon, 'sm') : null, it.av || null, h('span', { text: it.label }), it.sel ? ic('check', 'sm check') : null));
    });
    $('#layer').append(h('div', { class: 'scrim clear', onclick: closeLayer }), menu);
    place(menu, anchor);
    var first = menu.querySelector('button'); if (first) first.focus({ preventScroll: true });
    menu.addEventListener('keydown', function (e) {
      var bs = Array.prototype.slice.call(menu.querySelectorAll('button')), i = bs.indexOf(document.activeElement);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); bs[(i + (e.key === 'ArrowDown' ? 1 : -1) + bs.length) % bs.length].focus(); }
    });
  }
  function dialog(title, body, okLabel, danger, input) {
    return new Promise(function (resolve) {
      closeLayer();
      var done = function (v) { closeLayer(); resolve(v); };
      var inp = input ? h('input', { class: 'inp', type: input.type || 'text', placeholder: input.placeholder || '', 'aria-label': title }) : null;
      var ok = h('button', { class: 'btn ' + (danger ? 'danger solid' : 'primary'), type: 'button', text: okLabel || t('confirm'), onclick: function () { done(inp ? inp.value.trim() : true); } });
      if (inp) inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') ok.click(); });
      $('#layer').append(h('div', { class: 'scrim', onclick: function () { done(inp ? null : false); } }),
        h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title }, h('h3', { text: title }), body ? h('p', { text: body }) : null, inp,
          h('div', { class: 'acts' }, h('button', { class: 'btn', type: 'button', text: t('cancel'), onclick: function () { done(inp ? null : false); } }), ok)));
      (inp || ok).focus();
    });
  }

  /* custom, theme-aware select: a button + listbox popover (ARIA listbox pattern) */
  function selectBox(o) {
    var value = o.value;
    var labelOf = function (v) { var x = o.options.filter(function (op) { return op.value === v; })[0]; return x || { label: '—' }; };
    var face = h('span', { class: 'sel-face' });
    var btn = h('button', { class: 'sel ' + (o.cls || ''), type: 'button', 'aria-haspopup': 'listbox', 'aria-expanded': 'false', 'aria-label': o.label }, face, ic('down', 'xs sel-chev'));
    var paint = function () { var x = labelOf(value); face.replaceChildren.apply(face, [x.dot ? h('i', { class: 'tagdot', style: 'background:' + x.dot }) : null, x.icon ? ic(x.icon, 'sm') : null, h('span', { text: x.label })].filter(Boolean)); };
    var open = function () {
      closeLayer(); btn.setAttribute('aria-expanded', 'true');
      var list = h('div', { class: 'menu listbox', role: 'listbox', 'aria-label': o.label, tabindex: -1 });
      var opts = o.options.map(function (op) {
        var b = h('button', { type: 'button', role: 'option', 'aria-selected': String(op.value === value), onclick: function () { choose(op.value); } },
          op.dot ? h('i', { class: 'tagdot', style: 'background:' + op.dot }) : null, op.icon ? ic(op.icon, 'sm') : null, h('span', { text: op.label }), op.value === value ? ic('check', 'sm check') : null);
        list.appendChild(b); return b;
      });
      $('#layer').append(h('div', { class: 'scrim clear', onclick: function () { closeLayer(); btn.setAttribute('aria-expanded', 'false'); btn.focus(); } }), list);
      list.style.minWidth = Math.max(btn.offsetWidth, 160) + 'px';
      place(list, btn);
      var cur = Math.max(0, o.options.findIndex(function (op) { return op.value === value; }));
      opts[cur].focus();
      list.addEventListener('keydown', function (e) {
        var i = opts.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') { e.preventDefault(); opts[Math.min(opts.length - 1, i + 1)].focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); opts[Math.max(0, i - 1)].focus(); }
        else if (e.key === 'Home') { e.preventDefault(); opts[0].focus(); }
        else if (e.key === 'End') { e.preventDefault(); opts[opts.length - 1].focus(); }
        else if ((e.key === 'Enter' || e.key === ' ') && i > -1) { e.preventDefault(); choose(o.options[i].value); }
        else if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); closeLayer(); btn.setAttribute('aria-expanded', 'false'); btn.focus(); }
        else if (e.key.length === 1) { var k = e.key.toLowerCase(), j = o.options.findIndex(function (op, n) { return n > i && op.label.toLowerCase().indexOf(k) === 0; }); if (j < 0) j = o.options.findIndex(function (op) { return op.label.toLowerCase().indexOf(k) === 0; }); if (j > -1) opts[j].focus(); }
      });
    };
    var choose = function (v) { closeLayer(); btn.setAttribute('aria-expanded', 'false'); btn.focus(); if (v !== value) { value = v; paint(); o.onChange(v); } };
    btn.addEventListener('click', open);
    btn.addEventListener('keydown', function (e) { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); } });
    paint();
    return btn;
  }

  /* ------------------------------------------------------------ app layout */
  function convName(c) { return c.participant || t('guest'); }
  function render() {
    var app = $('#app'); app.replaceChildren(); msgEls.clear();
    app.dataset.view = S.view;
    syncLayout();
    el.rail = h('nav', { class: 'rail', 'aria-label': t('menu') }); el.nav = h('aside', { class: 'nav', 'aria-label': t('chats') });
    el.listCol = h('section', { class: 'list-col', 'aria-label': t('conversations') });
    el.main = h('main', { class: 'main' }); el.info = h('aside', { class: 'info', 'aria-label': t('details') });
    app.append(el.rail, el.nav, el.listCol, el.main, el.info);
    renderRail(); renderNav(); renderListCol(); renderMain();
  }
  function syncLayout() {
    var app = $('#app');
    app.dataset.view = S.view;
    app.classList.toggle('info-open', S.infoOpen && S.view === 'chats' && !!S.active);
    app.classList.toggle('show-chat', S.view === 'chats' && !!S.active);
  }
  function closeDrawer() { $('#app').classList.remove('nav-open'); }
  function toggleDrawer() { $('#app').classList.toggle('nav-open'); }

  function renderRail() {
    var item = function (view, icon, label) {
      return h('a', { class: 'rail-btn', href: OP + (view === 'chats' ? '' : view + '/'), 'data-view': view, title: label, 'aria-label': label, 'aria-current': S.view === view ? 'page' : 'false', onclick: function (e) { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); setView(view); } }, ic(icon, 'lg'));
    };
    el.themeBtn = h('button', { class: 'rail-btn', type: 'button', title: t('theme'), 'aria-label': t('theme'), onclick: function (e) { themeMenu(e.currentTarget); } }, ic(themeIcon(), 'lg'));
    var langBtn = h('button', { class: 'rail-btn', type: 'button', title: t('language'), 'aria-label': t('language') + ': ' + I.META[S.lang].native, onclick: function (e) { langMenu(e.currentTarget); } }, ic('globe', 'lg'), h('span', { class: 'lang', text: S.lang }));
    var sound = h('button', { class: 'rail-btn', type: 'button', title: t('sound'), 'aria-label': t('sound'), 'aria-pressed': String(Snd.enabled()), onclick: function () {
      Snd.setEnabled(!Snd.enabled()); sound.setAttribute('aria-pressed', String(Snd.enabled())); sound.replaceChildren(ic(Snd.enabled() ? 'vol' : 'mute', 'lg')); if (Snd.enabled()) Snd.play('notify');
    } }, ic(Snd.enabled() ? 'vol' : 'mute', 'lg'));
    el.rail.replaceChildren(
      h('div', { class: 'brand', title: S.boot.title, 'aria-hidden': 'true' }, ic('chat', 'lg')),
      item('chats', 'chat', t('chats')), item('analytics', 'chart', t('analytics')), item('settings', 'sliders', t('settings')),
      h('div', { class: 'grow' }), langBtn, el.themeBtn, sound,
      h('div', { class: 'me', title: S.boot.me.name }, av(S.boot.me.name, 'sm', 'on')));
  }
  function themeMenu(anchor) {
    openMenu(anchor, ['auto', 'light', 'dark'].map(function (th) {
      return { icon: th === 'dark' ? 'moon' : th === 'light' ? 'sun' : 'sliders', label: t({ auto: 'themeAuto', light: 'themeLight', dark: 'themeDark' }[th]), sel: S.theme === th, run: function () { setTheme(th); } };
    }), t('theme'));
  }
  function langMenu(anchor) {
    openMenu(anchor, (S.boot.languages || I.languages).map(function (l) { return { label: I.META[l].native, sel: l === S.lang, run: function () { setLang(l); } }; }), t('language'));
  }

  function setView(v) { go(v === 'chats' ? '' : v + '/'); }
  /* -- routing: /operator/, /operator/c/<id>/, /operator/analytics/, /operator/settings/<tab>/ -- */
  function parseRoute() {
    var rest = location.pathname.slice(OP.length).replace(/^\/+/, ''), m;
    if ((m = rest.match(/^c\/([0-9a-f-]{36})\/?$/))) return { view: 'chats', chat: m[1] };
    if (/^analytics\/?$/.test(rest)) return { view: 'analytics' };
    if ((m = rest.match(/^settings(?:\/([a-z-]+))?\/?$/))) return { view: 'settings', tab: m[1] || 'general' };
    return { view: 'chats', chat: null };
  }
  function go(path, replace) {
    var url = OP + path;
    if (url !== location.pathname) history[replace ? 'replaceState' : 'pushState']({}, '', url);
    applyRoute();
  }
  function applyRoute() {
    var r = parseRoute(), viewChanged = r.view !== S.view;
    closeLayer(); closeDrawer();
    S.view = r.view;
    if (r.view === 'settings') S.settingsTab = r.tab;
    if (viewChanged) quiet(render);
    else if (r.view !== 'chats') renderMain();
    if (r.view === 'chats') {
      if (r.chat && (!S.active || S.active.id !== r.chat)) showConversation(r.chat);
      else if (!r.chat && S.active) { S.active = null; syncLayout(); renderMain(); renderList(); }
    }
    document.querySelectorAll('.rail-btn[data-view]').forEach(function (b) { b.setAttribute('aria-current', b.dataset.view === S.view ? 'page' : 'false'); });
    if (S.boot) updateTitle();
  }
  /* -------------------------------------------------------------------- nav */
  var BOXES = [['all', 'chat', 'all'], ['mine', 'user', 'mine'], ['unassigned', 'user-plus', 'unassigned'], ['unread', 'bell', 'unread'], ['closed', 'check', 'closed']];
  function renderNav() {
    el.search = h('input', { type: 'search', placeholder: t('search'), value: S.f.q, 'aria-label': t('search'), autocomplete: 'off' });
    el.search.addEventListener('input', debounce(function () { S.f.q = el.search.value.trim(); S.convs = []; S.cursor = null; renderListHead(); loadList(); }, 250));
    el.boxNav = h('div'); el.tagNav = h('div'); el.agentNav = h('div');
    el.nav.replaceChildren(h('label', { class: 'search' }, ic('search', 'sm'), el.search),
      h('h5', { text: t('inbox') }), el.boxNav, h('h5', { text: t('priority') }),
      navItem(h('span', { class: 'dot', style: 'background:var(--danger)' }), t('highPriority'), S.f.prio === 'high', null, function () { S.f.prio = S.f.prio === 'high' ? null : 'high'; filterChanged(); }),
      h('h5', { text: t('tags') }), el.tagNav, h('h5', { text: t('agents') }), el.agentNav);
    renderBoxes(); renderTagNav(); renderAgents();
  }
  function navItem(icon, label, pressed, count, onclick, hot) {
    return h('button', { class: 'nav-item', type: 'button', 'aria-pressed': String(!!pressed), onclick: onclick }, icon, h('span', { class: 'lbl', text: label }),
      count != null ? h('span', { class: 'cnt' + (hot ? ' hot' : ''), text: I.num(S.lang, count) }) : null);
  }
  function renderBoxes() {
    if (!el.boxNav) return;
    var n = { all: S.counts.open, mine: S.counts.mine, unassigned: S.counts.unassigned, unread: S.counts.unread, closed: S.counts.closed };
    el.boxNav.replaceChildren.apply(el.boxNav, BOXES.map(function (b) {
      return navItem(ic(b[1], 'sm'), t(b[2]), S.f.box === b[0], n[b[0]] == null ? null : n[b[0]], function () { S.f.box = b[0]; filterChanged(); }, b[0] === 'unread' && n.unread > 0);
    }));
  }
  function renderTagNav() {
    if (!el.tagNav) return;
    if (!S.boot.tags.length) { el.tagNav.replaceChildren(h('div', { class: 'muted', style: 'padding:4px 8px;font-size:12.5px', text: t('noTags') })); return; }
    el.tagNav.replaceChildren.apply(el.tagNav, S.boot.tags.map(function (tg) {
      return navItem(h('span', { class: 'dot', style: 'background:' + tg.color }), tg.name, S.f.tag === tg.id, null, function () { S.f.tag = S.f.tag === tg.id ? null : tg.id; filterChanged(); });
    }));
  }
  function renderAgents() {
    if (!el.agentNav) return;
    el.agentNav.replaceChildren.apply(el.agentNav, S.boot.operators.map(function (o) {
      return h('div', { class: 'agent' }, av(o.name, 'sm', o.online ? 'on' : 'off'), h('div', {}, h('b', { text: o.name }), h('small', { text: o.online ? t('online') : t('offlineShort') })));
    }));
  }
  function filterChanged() { S.convs = []; S.cursor = null; S.hasMore = false; renderNav(); renderListHead(); loadList(); closeDrawer(); if (S.view !== 'chats') setView('chats'); }

  /* ------------------------------------------------------------------- list */
  function boxLabel() { var b = BOXES.filter(function (x) { return x[0] === S.f.box; })[0]; return S.f.q ? t('search') + ': ' + S.f.q : t(b[2]); }

  function renderListCol() {
    el.listHead = h('div', { class: 'list-head' }); el.filters = h('div', { class: 'filters' });
    el.list = h('div', { class: 'list', 'aria-label': t('conversations') });
    el.listCol.replaceChildren(el.listHead, el.filters, el.list);
    if (el.io) el.io.disconnect();
    el.io = new IntersectionObserver(function (entries) { if (entries[0].isIntersecting) loadMore(); }, { root: el.list, rootMargin: '240px 0px' });
    renderListHead(); renderList();
  }
  function renderListHead() {
    if (!el.listHead) return;
    el.listHead.replaceChildren(
      ib('menu', t('menu'), toggleDrawer, 'nav-toggle'),
      h('h2', {}, boxLabel()),
      ib('rotate', t('refresh'), function () { loadList(); }));
    var chips = [];
    if (S.f.prio) chips.push(fchip(h('span', { class: 'prio' }), t('highPriority'), function () { S.f.prio = null; filterChanged(); }));
    if (S.f.tag) {
      var tg = S.boot.tags.filter(function (x) { return x.id === S.f.tag; })[0];
      if (tg) chips.push(fchip(h('span', { class: 'tagdot', style: 'background:' + tg.color }), tg.name, function () { S.f.tag = null; filterChanged(); }));
    }
    el.filters.replaceChildren.apply(el.filters, chips);
  }
  function fchip(icon, label, onRemove) {
    return h('span', { class: 'fchip' }, icon, label, h('button', { type: 'button', 'aria-label': t('cancel') + ' ' + label, onclick: onRemove }, ic('x', 'xs')));
  }
  function listQuery() {
    var q = new URLSearchParams(), b = S.f.box;
    q.set('status', S.f.q ? 'all' : (b === 'closed' ? 'closed' : 'open'));
    if (b === 'unassigned') q.set('assigned', 'unassigned');
    if (b === 'mine') q.set('assigned', 'me');
    if (b === 'unread') q.set('unread', '1');
    if (S.f.prio) q.set('priority', S.f.prio);
    if (S.f.tag) q.set('tag', S.f.tag);
    if (S.f.q) q.set('q', S.f.q);
    return q;
  }

  async function loadList() {
    if (!S.convs.length) { S.loading = true; renderList(); }
    try {
      var d = await api(OP + 'conversations/?' + listQuery().toString());
      // merge: keep rows the operator already paged in, below the fresh first page
      var fresh = d.conversations, ids = {}, tail = [];
      fresh.forEach(function (c) { ids[c.id] = 1; });
      if (S.convs.length > fresh.length && d.has_more && fresh.length) {
        var edge = fresh[fresh.length - 1].last_message_at || '';
        tail = S.convs.filter(function (c) { return !ids[c.id] && (c.last_message_at || '') <= edge; });
      }
      S.convs = fresh.concat(tail); S.counts = d.counts; S.loading = false;
      if (!tail.length) { S.hasMore = d.has_more; S.cursor = d.next_cursor; }
      renderBoxes(); renderList(); updateTitle();
    } catch (e) { S.loading = false; fail(e); renderList(); }
  }
  async function loadMore() {
    if (S.loadingMore || !S.hasMore || !S.cursor) return;
    S.loadingMore = true; renderSentinel();
    try {
      var q = listQuery(); q.set('cursor', S.cursor);
      var d = await api(OP + 'conversations/?' + q.toString()), have = {};
      S.convs.forEach(function (c) { have[c.id] = 1; });
      var add = d.conversations.filter(function (c) { return !have[c.id]; });
      S.convs = S.convs.concat(add); S.hasMore = d.has_more; S.cursor = d.next_cursor;
      S.loadingMore = false;
      if (el.sentinel) el.sentinel.remove();
      add.forEach(function (c) { el.list.appendChild(rowFor(c)); });
      renderSentinel();
    } catch (e) { S.loadingMore = false; fail(e); renderSentinel(); }
  }
  function renderSentinel() {
    if (el.sentinel) { el.io && el.io.unobserve(el.sentinel); el.sentinel.remove(); el.sentinel = null; }
    if (!S.hasMore || !el.list) return;
    el.sentinel = h('div', { class: 'sentinel', 'aria-hidden': 'true' }, S.loadingMore ? h('div', { class: 'sk-row' }, h('div', { class: 'sk c' }), h('div', { class: 'lines' }, h('div', { class: 'sk l', style: 'width:55%' }), h('div', { class: 'sk l', style: 'width:80%' }))) : null);
    el.list.appendChild(el.sentinel);
    if (el.io) el.io.observe(el.sentinel);
  }
  function scheduleRefresh() { clearTimeout(refreshTimer); refreshTimer = setTimeout(function () { loadList(); }, 300); }
  function updateTitle() {
    var n = S.counts.unread || 0, page = S.view === 'analytics' ? t('analytics') : S.view === 'settings' ? t('settings') : (S.active ? convName(S.active) : t('chats'));
    document.title = (n ? '(' + n + ') ' : '') + page + ' · ' + S.boot.title;
  }
  function renderList() {
    if (!el.list) return;
    var scroll = el.list.scrollTop;
    if (S.loading) {
      el.list.replaceChildren.apply(el.list, [1, 2, 3, 4, 5, 6].map(function () { return h('div', { class: 'sk-row', 'aria-hidden': 'true' }, h('div', { class: 'sk c' }), h('div', { class: 'lines' }, h('div', { class: 'sk l', style: 'width:60%' }), h('div', { class: 'sk l', style: 'width:85%' }))); }));
      return;
    }
    if (!S.convs.length) {
      el.list.replaceChildren(h('div', { class: 'empty' }, h('div', { class: 'ill' }, ic('chat')), h('h3', { text: S.f.q ? t('noResults') : t('noConversations') })));
      return;
    }
    el.list.replaceChildren.apply(el.list, S.convs.map(rowFor));
    renderSentinel();
    el.list.scrollTop = scroll;
  }
  function rowFor(c) {
    var active = S.active && S.active.id === c.id, typing = S.typing[c.id];
    var tags = (c.tags || []).slice(0, 3).map(function (tg) { return h('i', { class: 'tagdot', style: 'background:' + tg.color, title: tg.name }); });
    return h('a', { class: 'row' + (c.unread_count ? ' unread' : ''), href: OP + 'c/' + c.id + '/', 'data-id': c.id, 'aria-current': active ? 'page' : null,
      onclick: function (e) { if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return; e.preventDefault(); openConversation(c.id); } },
      av(convName(c)),
      h('div', { class: 'row-body' },
        h('div', { class: 'row-top' }, h('span', { class: 'row-name', dir: 'auto', text: convName(c) }),
          c.priority === 'high' ? h('span', { class: 'prio', role: 'img', 'aria-label': t('highPriority'), title: t('highPriority') }) : null,
          h('span', { class: 'row-time', text: fmtShort(c.last_message_at) })),
        h('div', { class: 'row-bot' },
          h('span', { class: 'row-prev' + (typing ? ' typing' : ''), dir: 'auto', text: typing ? t('typing') : (c.last_message_preview || '…') }), tags,
          c.unread_count ? h('span', { class: 'badge', 'aria-label': t('unread') + ': ' + c.unread_count, text: I.num(S.lang, c.unread_count) }) : null)));
  }

  /* ----------------------------------------------------------- conversation */
  function openConversation(id) { go('c/' + id + '/'); }
  async function showConversation(id) {
    var found = S.convs.filter(function (c) { return c.id === id; })[0];
    S.active = found ? Object.assign({}, found) : { id: id, participant: '…', tags: [] };
    S.msgs = []; S.notes = []; S.reply = null; S.file = null; msgEls.clear(); S.loadingChat = true;
    if (innerWidth <= 1440) S.infoOpen = false; // overlay sizes: details open on demand
    syncLayout(); renderMain(); markActiveRow();
    try {
      var d = await api(OP + 'conversations/' + id + '/');
      if (!S.active || S.active.id !== id) return;
      S.active = d.conversation; S.hasOlder = d.has_more; S.loadingChat = false;
      S.msgs = d.messages.filter(function (m) { return !m.is_internal; }); S.notes = d.messages.filter(function (m) { return m.is_internal; });
      renderMain(); mergeIntoList(S.active); var row = el.list && el.list.querySelector('[data-id="' + id + '"]'); if (row) row.replaceWith(rowFor(S.convs.filter(function (c) { return c.id === id; })[0])); scheduleRefresh();
      updateTitle();
    } catch (e) { S.loadingChat = false; fail(e); renderMain(); }
  }
  function markActiveRow() {
    if (!el.list) return;
    el.list.querySelectorAll('.row').forEach(function (r) { if (S.active && r.dataset.id === S.active.id) r.setAttribute('aria-current', 'page'); else r.removeAttribute('aria-current'); });
  }
  function mergeIntoList(c) { S.convs = S.convs.map(function (x) { return x.id === c.id ? Object.assign({}, x, c, { unread_count: 0 }) : x; }); }
  function closeConversationView() { go(''); }

  function renderMain() {
    el.main.replaceChildren(); el.info.replaceChildren(); el.sub = null; el.scroller = null; el.jump = null;
    if (S.view === 'analytics') return renderAnalytics();
    if (S.view === 'settings') return renderSettings();
    if (!S.active) {
      el.main.appendChild(h('div', { class: 'empty' }, h('div', { class: 'ill' }, ic('chat')), h('h3', { text: t('selectConversation') }), h('p', { text: t('chooseFromList') })));
      return;
    }
    var c = S.active, closed = c.status === 'closed';
    el.sub = h('div', { class: 'sub', 'aria-live': 'polite' });
    var assignBtn = h('button', { class: 'btn', type: 'button', title: t('assignTo'), 'aria-label': t('assignTo'), onclick: function (e) { assignMenu(e.currentTarget); } }, ic('user', 'sm'), ic('down', 'xs'));
    var head = h('div', { class: 'chat-head' },
      ib('back', t('chats'), closeConversationView, 'back'),
      av(convName(c), 'sm'),
      h('div', { class: 'who' }, h('div', { class: 'name', dir: 'auto', text: convName(c) }), el.sub),
      closed ? h('button', { class: 'btn', type: 'button', 'aria-label': t('reopen'), onclick: function () { act('reopen'); } }, ic('rotate', 'sm'), h('span', { class: 'txt', text: t('reopen') }))
        : h('button', { class: 'btn dark', type: 'button', 'aria-label': t('closeConv'), onclick: function () { act('close'); } }, ic('check', 'sm'), h('span', { class: 'txt', text: t('closeConv') })),
      assignBtn,
      ib('info', t('details'), toggleInfo, '', S.infoOpen),
      ib('more', t('menu'), function (e) { chatMenu(e.currentTarget); }));
    el.scroller = h('div', { class: 'scroller', tabindex: 0, role: 'log', 'aria-label': t('messages') });
    el.stack = h('div', { class: 'stack' }); el.scroller.appendChild(el.stack);
    el.scroller.addEventListener('scroll', onScroll);
    el.main.append(head, el.scroller, closed ? closedBar() : composer());
    renderSub(); renderMessages(); renderInfo();
  }
  function renderSub() {
    if (!el.sub || !S.active) return;
    var typing = S.typing[S.active.id];
    el.sub.className = 'sub' + (typing ? ' typing' : '');
    var parts = [S.active.status === 'closed' ? t('closed') : t('open')];
    if (S.active.assigned_name) parts.push(S.active.assigned_name);
    el.sub.textContent = typing ? t('typingName', { name: convName(S.active) }) : parts.join(' · ');
  }
  function toggleInfo() {
    S.infoOpen = !S.infoOpen; LS.set('supchat.op.info', S.infoOpen ? '1' : '0'); syncLayout(); renderInfo();
    var b = el.main.querySelector('.chat-head [aria-pressed]'); if (b) b.setAttribute('aria-pressed', String(S.infoOpen));
  }
  function closedBar() {
    return h('div', { class: 'closed-bar' }, h('span', { text: t('conversationClosed') }), h('button', { class: 'btn primary sm', type: 'button', onclick: function () { act('reopen'); } }, ic('rotate', 'sm'), t('reopen')));
  }
  function chatMenu(anchor) {
    var c = S.active;
    openMenu(anchor, [
      { icon: 'download', label: t('downloadTranscript'), run: function () { location.href = OP + 'conversations/' + c.id + '/transcript/?notes=1'; } },
      { icon: 'mail', label: t('emailTranscript'), run: emailTranscript },
      '-',
      { icon: 'block', label: t('block'), danger: true, run: blockVisitor },
      { icon: 'trash', label: t('delete'), danger: true, run: deleteConversation }
    ]);
  }
  function assignMenu(anchor) {
    var c = S.active;
    var items = S.boot.operators.map(function (o) { return { av: av(o.name, 'xs', o.online ? 'on' : null), label: o.id === S.boot.me.id ? o.name + ' (' + t('you') + ')' : o.name, sel: c.assigned_operator === o.id, run: function () { assign(o.id); } }; });
    items.push('-', { icon: 'x', label: t('unassign'), run: function () { assign(null); } });
    openMenu(anchor, items, t('assignTo'));
  }

  /* --------------------------------------------------------------- messages */
  function isOut(m) { return m.sender_type === 'operator' || m.sender_type === 'bot'; }
  function sameGroup(a, b) { return a && b && a.sender_type === b.sender_type && (a.sender_user || '') === (b.sender_user || '') && dayKey(a.created_at) === dayKey(b.created_at) && Math.abs(new Date(b.created_at) - new Date(a.created_at)) < 3e5; }
  function renderMessages() {
    if (!el.stack) return;
    el.stack.replaceChildren(); msgEls.clear();
    if (S.loadingChat) {
      [52, 38, 64, 30, 48].forEach(function (w, i) { el.stack.appendChild(h('div', { class: 'sk sk-bubble', style: 'width:' + w + '%;align-self:' + (i % 2 ? 'flex-end' : 'flex-start'), 'aria-hidden': 'true' })); });
      return;
    }
    if (S.hasOlder) el.stack.appendChild(h('button', { class: 'btn ghost sm', style: 'align-self:center', type: 'button', text: t('loadMore'), onclick: loadOlder }));
    if (!S.msgs.length) el.stack.appendChild(h('div', { class: 'empty' }, h('p', { text: t('noMessages') })));
    S.msgs.forEach(function (m, i) { el.stack.appendChild(buildMessage(m, S.msgs[i - 1], S.msgs[i + 1], false)); });
    el.typingEl = null; showTypingDots(); scrollBottom(true);
  }
  function appendMessage(m) {
    if (msgEls.has(m.id) || S.msgs.some(function (x) { return x.id === m.id; })) return;
    var prev = S.msgs[S.msgs.length - 1]; S.msgs.push(m);
    var empty = el.stack.querySelector('.empty'); if (empty) empty.remove();
    if (prev && sameGroup(prev, m)) { var pn = msgEls.get(prev.id); if (pn) pn.classList.remove('last'); }
    var node = buildMessage(m, prev, null, true);
    if (el.typingEl && el.typingEl.parentNode) el.stack.insertBefore(node, el.typingEl); else el.stack.appendChild(node);
  }
  function buildMessage(m, prev, next, live) {
    var frag = document.createDocumentFragment();
    if (!prev || dayKey(prev.created_at) !== dayKey(m.created_at)) frag.appendChild(h('div', { class: 'day', text: fmtDay(m.created_at) }));
    if (m.sender_type === 'system') { frag.appendChild(h('div', { class: 'event', text: m.text })); return frag; }
    var out = isOut(m), first = !sameGroup(prev, m), last = !sameGroup(m, next);
    var bubble = h('div', { class: 'bubble' });
    if (first && m.sender_type === 'bot') bubble.appendChild(h('div', { class: 'sender', text: (m.sender_name || t('bot')) + ' · AI' }));
    else if (first && out && m.sender_user !== (S.boot.me.username || '')) bubble.appendChild(h('div', { class: 'sender', text: m.sender_name }));
    if (m.reply_to) bubble.appendChild(h('span', { class: 'quote', onclick: function () { jumpTo(m.reply_to.id); } }, h('b', { text: isOut(m.reply_to) ? t('support') : convName(S.active) }), h('span', { dir: 'auto', text: m.reply_to.text })));
    if (m.attachment) bubble.appendChild(attachmentNode(m.attachment));
    if (m.text) bubble.appendChild(h('span', { dir: 'auto' }, linkify(m.text)));
    var meta = h('span', { class: 'meta' }, fmtTime(m.created_at));
    if (out) meta.appendChild(ic(m.is_read ? 'checks' : 'check', ''));
    bubble.appendChild(meta);
    var tools = h('div', { class: 'tools' },
      h('button', { type: 'button', title: t('replyTo'), 'aria-label': t('replyTo'), onclick: function () { setReply(m); } }, ic('reply', 'sm flip')),
      h('button', { type: 'button', title: t('react'), 'aria-label': t('react'), onclick: function (e) { reactMenu(e.currentTarget, m); } }, ic('smile', 'sm')),
      m.text ? h('button', { type: 'button', title: t('copy'), 'aria-label': t('copy'), onclick: function () { copyText(m.text); } }, ic('copy', 'sm')) : null);
    var who = m.sender_type === 'bot' ? botAv('sm') : av(out ? m.sender_name : convName(S.active), 'sm');
    var node = h('div', { class: 'msg ' + (out ? 'out' : 'in') + (first ? ' first' : '') + (last ? ' last' : '') + (live ? ' live' : ''), tabindex: -1 },
      who, h('div', { class: 'bubble-wrap' }, bubble, reactionsNode(m)), tools);
    msgEls.set(m.id, node);
    frag.appendChild(node);
    return frag;
  }
  function attachmentNode(a) {
    if (a.is_image) {
      var img = h('img', { class: 'att-img', src: a.url, alt: a.name, loading: 'lazy', onclick: function () { lightbox(a.url, a.name); } });
      img.addEventListener('load', function () { if (nearBottom) scrollBottom(true); });
      return img;
    }
    return h('a', { class: 'att-file', href: a.url + '?download=1', target: '_blank', rel: 'noopener' }, h('span', { class: 'fi' }, ic('note', 'sm')), h('span', {}, h('b', { dir: 'auto', text: a.name }), h('small', { text: fmtSize(a.size) })));
  }
  function lightbox(url, alt) { closeLayer(); $('#layer').appendChild(h('div', { class: 'lightbox', role: 'dialog', 'aria-label': alt || '', onclick: closeLayer }, h('img', { src: url, alt: alt || '' }))); }
  function reactionsNode(m) {
    var mine = 'operator:' + S.boot.me.id, box = h('div', { class: 'reacts' });
    (m.reactions || []).forEach(function (r) {
      box.appendChild(h('button', { class: 'react' + (r.by.indexOf(mine) > -1 ? ' mine' : ''), type: 'button', 'aria-pressed': String(r.by.indexOf(mine) > -1), onclick: function () { react(m.id, r.emoji); } }, r.emoji, h('span', { text: String(r.count) })));
    });
    return box;
  }
  function reactMenu(anchor, m) {
    closeLayer();
    var bar = h('div', { class: 'menu emo', role: 'menu' });
    (S.boot.reactions || []).forEach(function (e) { bar.appendChild(h('button', { type: 'button', role: 'menuitem', 'aria-label': e, text: e, onclick: function () { closeLayer(); react(m.id, e); } })); });
    $('#layer').append(h('div', { class: 'scrim clear', onclick: closeLayer }), bar);
    place(bar, anchor, true);
  }
  async function react(id, emoji) { try { await api(OP + 'conversations/' + S.active.id + '/react/', { body: { message_id: id, emoji: emoji } }); } catch (e) { fail(e); } }
  function copyText(s) { if (navigator.clipboard) navigator.clipboard.writeText(s).then(function () { toast(t('copied')); }, function () {}); }
  function jumpTo(id) { var n = msgEls.get(id); if (n) { n.scrollIntoView({ block: 'center', behavior: 'smooth' }); n.focus({ preventScroll: true }); } }
  function onScroll() {
    var s = el.scroller; nearBottom = s.scrollHeight - s.scrollTop - s.clientHeight < 120;
    if (nearBottom && el.jump) { el.jump.remove(); el.jump = null; }
    else if (!nearBottom && !el.jump) { el.jump = h('button', { class: 'jump', type: 'button', 'aria-label': t('scrollDown'), title: t('scrollDown'), onclick: function () { scrollBottom(); } }, ic('down')); el.main.appendChild(el.jump); }
    if (s.scrollTop < 40 && S.hasOlder && !S.loadingOlder) loadOlder();
  }
  function scrollBottom(instant) {
    if (!el.scroller) return; var s = el.scroller;
    requestAnimationFrame(function () { s.scrollTo({ top: s.scrollHeight, behavior: instant ? 'auto' : 'smooth' }); nearBottom = true; });
  }
  async function loadOlder() {
    if (!S.msgs.length || S.loadingOlder) return; S.loadingOlder = true;
    try {
      var d = await api(OP + 'conversations/' + S.active.id + '/?before=' + S.msgs[0].id);
      var s = el.scroller, before = s.scrollHeight;
      S.msgs = d.messages.filter(function (m) { return !m.is_internal; }).concat(S.msgs); S.hasOlder = d.has_more;
      renderMessages(); s.scrollTop = s.scrollHeight - before;
    } catch (e) { fail(e); } finally { S.loadingOlder = false; }
  }
  function showTypingDots() {
    if (!el.stack || !S.active) return;
    var on = !!S.typing[S.active.id];
    if (on && !el.typingEl) { el.typingEl = h('div', { class: 'msg in first last live', 'aria-hidden': 'true' }, av(convName(S.active), 'sm'), h('div', { class: 'bubble' }, h('span', { class: 'typing-dots' }, h('i'), h('i'), h('i')))); el.stack.appendChild(el.typingEl); if (nearBottom) scrollBottom(); }
    if (!on && el.typingEl) { el.typingEl.remove(); el.typingEl = null; }
  }

  /* --------------------------------------------------------------- composer */
  function setReply(m) { S.reply = m; renderChipsIn(); if (el.input) el.input.focus(); }
  function renderChipsIn() {
    if (!el.chipsIn) return;
    var kids = [];
    if (S.reply) kids.push(h('span', { class: 'pchip' }, ic('reply', 'xs flip'), h('span', { dir: 'auto', text: (S.reply.text || (S.reply.attachment && S.reply.attachment.name) || '').slice(0, 90) }), h('button', { type: 'button', 'aria-label': t('cancel'), onclick: function () { S.reply = null; renderChipsIn(); } }, ic('x', 'xs'))));
    if (S.file) kids.push(h('span', { class: 'pchip' }, ic('clip', 'xs'), h('span', { dir: 'auto', text: S.file.name + ' · ' + fmtSize(S.file.size) }), h('button', { type: 'button', 'aria-label': t('cancel'), onclick: function () { S.file = null; renderChipsIn(); syncSend(); } }, ic('x', 'xs'))));
    el.chipsIn.replaceChildren.apply(el.chipsIn, kids);
  }
  function composer() {
    el.popup = h('div'); el.chipsIn = h('div', { class: 'chips-in' });
    el.input = h('textarea', { rows: 1, placeholder: t('typeReply'), 'aria-label': t('typeReply'), maxlength: 2000 });
    el.send = h('button', { class: 'send', type: 'button', disabled: true, onclick: send }, h('span', { text: t('send') }), ic('send', 'sm flip'));
    var fileInput = h('input', { type: 'file', hidden: true, onchange: function (e) { var f = e.target.files[0]; if (f) pickFile(f); e.target.value = ''; } });
    var bar = h('div', { class: 'comp-bar' },
      S.boot.attachments.enabled ? ib('clip', t('attach'), function () { fileInput.click(); }) : null, fileInput,
      ib('smile', t('emoji'), emojiPopup),
      ib('bolt', t('cannedResponses'), function () { el.input.value = '/'; el.input.focus(); cannedPopup(); }),
      h('div', { class: 'grow' }), el.send);
    var wrap = h('div', { class: 'composer' }, el.popup, h('div', { class: 'comp' }, el.chipsIn, el.input, bar));
    el.input.addEventListener('input', function () { autosize(); syncSend(); onTyping(); cannedPopup(); });
    el.input.addEventListener('keydown', function (e) {
      var sel = el.popup.querySelector('.opt.sel');
      if (sel && (e.key === 'Enter' || e.key === 'Tab')) { e.preventDefault(); sel.click(); return; }
      if (sel && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault(); var opts = Array.prototype.slice.call(el.popup.querySelectorAll('.opt')), i = opts.indexOf(sel);
        sel.classList.remove('sel'); opts[(i + (e.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length].classList.add('sel'); return;
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (e.isComposing || e.keyCode === 229) return;
        e.preventDefault(); if (!e.repeat) send();
      }
      if (e.key === 'Escape') { el.popup.replaceChildren(); S.reply = null; renderChipsIn(); }
    });
    el.input.addEventListener('paste', function (e) { var f = e.clipboardData && e.clipboardData.files[0]; if (f) { e.preventDefault(); pickFile(f); } });
    if (matchMedia('(hover: hover)').matches) setTimeout(function () { el.input.focus({ preventScroll: true }); }, 30);
    renderChipsIn();
    return wrap;
  }
  function autosize() { el.input.style.height = 'auto'; el.input.style.height = Math.min(el.input.scrollHeight, 180) + 'px'; }
  function syncSend() { el.send.disabled = !el.input.value.trim() && !S.file; }
  function pickFile(f) { if (f.size > (S.boot.attachments.max_mb || 5) * 1048576) return toast(t('fileTooLarge'), true); S.file = f; renderChipsIn(); syncSend(); }
  function emojiPopup() {
    if (el.popup.firstChild) { el.popup.replaceChildren(); return; }
    var set = '😀 😃 😄 😁 😆 😅 😂 🙂 😉 😊 😍 🥰 😘 😎 🤩 🤔 😐 😴 😢 😭 😡 😱 🙏 👍 👎 👏 🙌 💪 👋 ✅ ❌ ⭐ 🔥 🎉 ❤️ 💙 💡 📌 📎 ⏰ 📞 ✉️ 🔒 🚀 ☕ 👀'.split(' ');
    var grid = h('div', { class: 'emoji-grid' }); set.forEach(function (e) { grid.appendChild(h('button', { type: 'button', 'aria-label': e, text: e, onclick: function () { insertAtCursor(e); } })); });
    el.popup.replaceChildren(h('div', { class: 'popup' }, grid));
  }
  function insertAtCursor(s) { var i = el.input, a = i.selectionStart, b = i.selectionEnd; i.value = i.value.slice(0, a) + s + i.value.slice(b); i.selectionStart = i.selectionEnd = a + s.length; i.focus(); autosize(); syncSend(); }
  function cannedPopup() {
    var v = el.input.value;
    if (!/^\/\S*$/.test(v)) { if (el.popup.querySelector('.opt')) el.popup.replaceChildren(); return; }
    var q = v.slice(1).toLowerCase();
    var hits = (S.boot.canned || []).filter(function (c) { return c.shortcut.indexOf(q) === 0 || c.title.toLowerCase().indexOf(q) > -1; }).slice(0, 8);
    if (!hits.length) { el.popup.replaceChildren(h('div', { class: 'popup' }, h('div', { class: 'muted', style: 'padding:8px 10px', text: t('noResults') }))); return; }
    var box = h('div', { class: 'popup', role: 'listbox' });
    hits.forEach(function (c, i) { box.appendChild(h('button', { class: 'opt' + (i === 0 ? ' sel' : ''), type: 'button', role: 'option', onclick: function () { el.input.value = c.text; el.popup.replaceChildren(); autosize(); syncSend(); el.input.focus(); } }, h('b', { text: '/' + c.shortcut }), h('span', { dir: 'auto', text: c.text }))); });
    el.popup.replaceChildren(box);
  }
  function onTyping() {
    if (!S.active) return; var now = Date.now();
    if (now - typingSent > 3000 && el.input.value.trim() && el.input.value[0] !== '/') { typingSent = now; api(OP + 'conversations/' + S.active.id + '/typing/', { body: { is_typing: true } }).catch(function () {}); }
    clearTimeout(typingStop); typingStop = setTimeout(function () { typingSent = 0; if (S.active) api(OP + 'conversations/' + S.active.id + '/typing/', { body: { is_typing: false } }).catch(function () {}); }, 4000);
  }
  async function send() {
    var text = el.input.value.trim(); if ((!text && !S.file) || !S.active || el.send.disabled) return;
    el.send.disabled = true;
    try {
      var fd = new FormData(); fd.append('text', text); if (S.reply) fd.append('reply_to', S.reply.id); if (S.file) fd.append('file', S.file);
      var d = await api(OP + 'conversations/' + S.active.id + '/send/', { form: fd });
      el.input.value = ''; autosize(); S.reply = null; S.file = null; renderChipsIn(); syncSend(); el.popup.replaceChildren();
      appendMessage(d.message); scrollBottom(); Snd.play('outgoing');
      clearTimeout(typingStop); typingSent = 0;
    } catch (e) { fail(e); syncSend(); }
  }

  /* -------------------------------------------------------------- details */
  function attr(icon, label, value) { return h('div', { class: 'attr' }, ic(icon, 'sm'), h('span', { text: label }), value); }
  function renderInfo() {
    if (!el.info) return;
    if (!S.active || !S.infoOpen || S.view !== 'chats') { el.info.replaceChildren(); return; }
    var c = S.active;
    var subject = h('input', { class: 'field-inline', type: 'text', value: c.subject || '', maxlength: 120, placeholder: '—', 'aria-label': t('subject') });
    subject.addEventListener('change', function () { update({ subject: subject.value }); });
    var prio = selectBox({ cls: 'inline', label: t('priority'), value: c.priority, onChange: function (v) { update({ priority: v }); },
      options: [{ value: 'low', label: t('low'), dot: '#94a3b8' }, { value: 'normal', label: t('normal'), dot: '#3b82f6' }, { value: 'high', label: t('high'), dot: '#ef4444' }] });
    var lang = c.locale ? (I.META[c.locale] || { native: c.locale }).native : '—';
    var tags = h('div', { class: 'tags' });
    var have = (c.tags || []).map(function (x) { return x.id; });
    S.boot.tags.forEach(function (tg) {
      tags.appendChild(h('button', { class: 'tag', type: 'button', style: '--c:' + tg.color, 'aria-pressed': String(have.indexOf(tg.id) > -1), onclick: function () { toggleTag(tg.id); } }, h('i', { class: 'tagdot', style: 'background:' + tg.color }), tg.name));
    });
    tags.appendChild(h('button', { class: 'tag add', type: 'button', onclick: newTag }, ic('plus', 'xs'), t('addTag')));
    var noteInput = h('textarea', { rows: 2, placeholder: t('writeNote'), 'aria-label': t('writeNote'), maxlength: 2000 });
    var noteSave = h('button', { class: 'btn sm primary', type: 'button', text: t('save'), disabled: true, onclick: function () { addNote(noteInput); } });
    noteInput.addEventListener('input', function () { noteSave.disabled = !noteInput.value.trim(); });
    noteInput.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); addNote(noteInput); } });
    var notes = S.notes.slice().reverse().map(function (n) {
      return h('div', { class: 'note' }, h('div', { class: 'note-top' }, av(n.sender_name, 'xs'), h('div', {}, h('b', { text: n.sender_name }), h('small', { text: fmtFull(n.created_at) }))), h('p', { dir: 'auto', text: n.text || (n.attachment ? n.attachment.name : '') }));
    });
    var sections = [
      h('div', { class: 'info-head' }, av(convName(c), 'sm'), h('div', { class: 'who' }, h('b', { dir: 'auto', text: convName(c) }), h('small', { text: c.is_guest ? t('guest') : t('visitor') })), ib('x', t('closeChat'), toggleInfo)),
      h('div', { class: 'sect' },
        attr('mail', t('email'), h('b', { dir: 'ltr', text: c.email || '—' })),
        attr('note', t('subject'), subject),
        attr('bolt', t('priority'), prio),
        attr('globe', t('language'), h('b', { text: lang })),
        attr('chat', t('startedAt'), h('b', { text: fmtFull(c.created_at) })),
        attr('star', t('rating'), c.rating ? h('b', { class: 'stars', 'aria-label': c.rating + '/5', text: '★'.repeat(c.rating) + '☆'.repeat(5 - c.rating) }) : h('b', { class: 'muted', text: t('noRating') })),
        c.rating_comment ? h('p', { dir: 'auto', class: 'muted', style: 'margin:4px 0 0;font-size:13px', text: '“' + c.rating_comment + '”' }) : null),
      h('div', { class: 'sect' }, h('h4', { text: t('tags') }), tags)
    ];
    if (S.boot.ai.enabled) {
      sections.push(h('div', { class: 'sect' }, h('div', { class: 'line' }, h('span', {}, ic('bolt', 'sm'), ' ', c.ai_enabled ? t('aiOn') : t('aiOff')),
        h('button', { class: 'switch', type: 'button', role: 'switch', 'aria-checked': String(!!c.ai_enabled), 'aria-label': t('aiAssistant'), onclick: function () { update({ ai_enabled: !c.ai_enabled }); } }))));
    }
    sections.push(h('div', { class: 'sect' }, h('h4', { text: t('notes') }),
      h('div', { class: 'note-box' }, noteInput, h('div', { class: 'bar' }, noteSave)),
      notes.length ? h('div', { style: 'margin-top:6px' }, notes) : h('p', { class: 'muted', style: 'margin:10px 0 0;font-size:12.5px', text: t('noNotes') })));
    el.info.replaceChildren.apply(el.info, sections);
  }

  /* ---------------------------------------------------------------- actions */
  async function addNote(input) {
    var text = input.value.trim(); if (!text) return;
    try {
      var fd = new FormData(); fd.append('text', text); fd.append('internal', 'true');
      var d = await api(OP + 'conversations/' + S.active.id + '/send/', { form: fd });
      if (!S.notes.some(function (n) { return n.id === d.message.id; })) S.notes.push(d.message);
      renderInfo();
    } catch (e) { fail(e); }
  }
  async function update(fields) {
    try { var d = await api(OP + 'conversations/' + S.active.id + '/update/', { body: fields }); Object.assign(S.active, d.conversation); renderInfo(); renderSub(); scheduleRefresh(); } catch (e) { fail(e); }
  }
  async function assign(opId) {
    try {
      await api(OP + 'conversations/' + S.active.id + '/assign/', { body: { operator_id: opId } });
      S.active.assigned_operator = opId; var o = S.boot.operators.filter(function (x) { return x.id === opId; })[0];
      S.active.assigned_name = o ? o.name : null; renderSub(); scheduleRefresh(); toast(o ? t('assignTo') + ': ' + o.name : t('unassign'));
    } catch (e) { fail(e); }
  }
  async function toggleTag(id) {
    var have = (S.active.tags || []).map(function (x) { return x.id; }), next = have.indexOf(id) > -1 ? have.filter(function (x) { return x !== id; }) : have.concat([id]);
    try { var d = await api(OP + 'conversations/' + S.active.id + '/tags/', { body: { tag_ids: next } }); Object.assign(S.active, d.conversation); renderInfo(); scheduleRefresh(); } catch (e) { fail(e); }
  }
  async function newTag() {
    var name = await dialog(t('addTag'), null, t('add'), false, { placeholder: t('tags') }); if (!name) return;
    try { var d = await api(OP + 'api/tags/', { body: { name: name, color: PALETTE[S.boot.tags.length % PALETTE.length] } }); S.boot.tags.push(d.tag); renderTagNav(); await toggleTag(d.tag.id); } catch (e) { fail(e); }
  }
  async function act(kind) {
    try { await api(OP + 'conversations/' + S.active.id + '/' + kind + '/', { body: {} }); S.active.status = kind === 'close' ? 'closed' : 'open'; renderMain(); scheduleRefresh(); } catch (e) { fail(e); }
  }
  async function deleteConversation() {
    if (!await dialog(t('deleteTitle'), t('deleteBody'), t('delete'), true)) return;
    try { await api(OP + 'conversations/' + S.active.id + '/delete/', { body: {} }); closeConversationView(); scheduleRefresh(); } catch (e) { fail(e); }
  }
  async function blockVisitor() {
    if (!await dialog(t('block'), t('blockConfirm'), t('block'), true)) return;
    try { await api(OP + 'conversations/' + S.active.id + '/block/', { body: {} }); S.active.status = 'closed'; renderMain(); scheduleRefresh(); } catch (e) { fail(e); }
  }
  async function emailTranscript() {
    var email = S.active.email || await dialog(t('emailTranscript'), null, t('send'), false, { type: 'email', placeholder: t('email') }); if (!email) return;
    try { await api(OP + 'conversations/' + S.active.id + '/transcript/email/', { body: { email: email } }); toast(t('transcriptSent')); } catch (e) { fail(e); }
  }

  /* --------------------------------------------------------------- analytics */
  function chartBars(values, labels, cls) {
    var W = 560, H = 180, pad = 22, max = Math.max.apply(null, values.concat([1])), bw = (W - pad * 2) / values.length, out = '';
    for (var g = 0; g <= 3; g++) { var y = pad + (H - pad * 2) * g / 3; out += '<line class="grid" x1="' + pad + '" x2="' + (W - pad) + '" y1="' + y + '" y2="' + y + '"/>'; }
    values.forEach(function (v, i) {
      var bh = (H - pad * 2) * v / max, x = pad + i * bw + bw * 0.18;
      out += '<rect class="bar ' + (cls || '') + '" rx="3" x="' + x.toFixed(1) + '" y="' + (H - pad - bh).toFixed(1) + '" width="' + (bw * 0.64).toFixed(1) + '" height="' + bh.toFixed(1) + '"><title>' + labels[i] + ': ' + v + '</title></rect>';
      if (labels.length <= 12 || i % Math.ceil(labels.length / 10) === 0) out += '<text x="' + (x + bw * 0.32).toFixed(1) + '" y="' + (H - 5) + '" text-anchor="middle">' + labels[i] + '</text>';
    });
    return '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" preserveAspectRatio="none">' + out + '</svg>';
  }
  function chartLine(values, labels) {
    var W = 560, H = 180, pad = 22, max = Math.max.apply(null, values.concat([1])), step = (W - pad * 2) / Math.max(values.length - 1, 1);
    var pts = values.map(function (v, i) { return [pad + i * step, H - pad - (H - pad * 2) * v / max]; });
    var path = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var out = '';
    for (var g = 0; g <= 3; g++) { var y = pad + (H - pad * 2) * g / 3; out += '<line class="grid" x1="' + pad + '" x2="' + (W - pad) + '" y1="' + y + '" y2="' + y + '"/>'; }
    out += '<path class="area" d="' + path + ' L' + pts[pts.length - 1][0] + ' ' + (H - pad) + ' L' + pts[0][0] + ' ' + (H - pad) + 'Z"/><path class="ln" d="' + path + '"/>';
    labels.forEach(function (l, i) { if (labels.length <= 8 || i % Math.ceil(labels.length / 7) === 0) out += '<text x="' + pts[i][0].toFixed(1) + '" y="' + (H - 5) + '" text-anchor="middle">' + l + '</text>'; });
    return '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" preserveAspectRatio="none">' + out + '</svg>';
  }
  function pageShell(title, extra) {
    var page = h('div', { class: 'page' }), inner = h('div', { class: 'page-in' }); page.appendChild(inner); el.main.appendChild(page);
    inner.appendChild(h('div', { class: 'page-top' }, ib('menu', t('menu'), toggleDrawer, 'nav-toggle'), h('h2', { text: title }), extra || null));
    return inner;
  }
  async function renderAnalytics() {
    var seg = h('div', { class: 'seg', role: 'group' });
    [7, 30].forEach(function (d) { seg.appendChild(h('button', { type: 'button', 'aria-pressed': String(S.analyticsDays === d), text: t(d === 7 ? 'last7' : 'last30'), onclick: function () { S.analyticsDays = d; renderMain(); } })); });
    var inner = pageShell(t('analytics'), seg);
    var sk = h('div', { class: 'cards' }, [1, 2, 3, 4].map(function () { return h('div', { class: 'sk', style: 'height:96px;border-radius:14px' }); }));
    inner.appendChild(sk);
    try {
      var d = await api(OP + 'api/analytics/?days=' + S.analyticsDays); sk.remove();
      var lab = d.labels.map(function (s) { return new Date(s + 'T12:00:00').toLocaleDateString(locale(), { day: 'numeric', month: 'short' }); });
      var avg = d.rating.average ? d.rating.average.toFixed(1) : '—';
      var card = function (title, value, small) { return h('div', { class: 'card' }, h('h4', { text: title }), h('div', { class: 'stat' }, value, small ? h('small', { text: small }) : null)); };
      inner.appendChild(h('div', { class: 'cards' },
        card(t('conversations'), I.num(S.lang, d.totals.conversations)), card(t('messages'), I.num(S.lang, d.totals.messages)),
        card(t('avgRating'), avg, ' / 5 · ' + I.num(S.lang, d.rating.count)), card(t('firstResponse'), fmtDur(d.first_response_seconds)),
        card(t('open') + ' / ' + t('closed'), I.num(S.lang, d.totals.open), ' / ' + I.num(S.lang, d.totals.closed))));
      var chartCard = function (title, svg) { var c = h('div', { class: 'card' }, h('h4', { text: title })); c.insertAdjacentHTML('beforeend', svg); return c; };
      inner.appendChild(h('div', { class: 'grid2' }, chartCard(t('conversations'), chartLine(d.conversations, lab)), chartCard(t('messages'), chartBars(d.messages, lab))));
      inner.appendChild(h('div', { class: 'grid2' }, chartCard(t('busiestHours'), chartBars(d.hours, d.hours.map(function (_, i) { return String(i); }), 'bar2')), chartCard(t('ratingDist'), chartBars(d.rating.distribution, ['1★', '2★', '3★', '4★', '5★']))));
      var tg = h('div', { class: 'card' }, h('h4', { text: t('topTags') }));
      if (!d.top_tags.length) tg.appendChild(h('span', { class: 'muted', text: t('noTags') }));
      d.top_tags.forEach(function (x) { tg.appendChild(h('div', { class: 'rowx' }, h('b', {}, h('i', { class: 'tagdot', style: 'display:inline-block;margin-inline-end:8px;background:' + x.color }), x.name), h('span', { text: I.num(S.lang, x.n) }))); });
      inner.appendChild(tg);
    } catch (e) { fail(e); }
  }

  /* ---------------------------------------------------------------- settings */

  var SETTINGS_TABS = [['general', 'sliders', 'general'], ['quick-replies', 'bolt', 'cannedResponses'], ['tags', 'tag', 'tags'], ['ai', 'chat', 'aiStatus'], ['webhooks', 'link', 'webhooks'], ['blocked', 'block', 'blocked']];
  function renderSettings() {
    var tabs = SETTINGS_TABS.filter(function (x) { return x[0] !== 'webhooks' || S.boot.me.is_superuser; });
    if (!tabs.some(function (x) { return x[0] === S.settingsTab; })) S.settingsTab = 'general';
    var page = h('div', { class: 'page' }), wrap = h('div', { class: 'settings' });
    var nav = h('div', { class: 'stabs', role: 'tablist', 'aria-label': t('settings'), 'aria-orientation': 'vertical' });
    tabs.forEach(function (x) {
      var on = x[0] === S.settingsTab;
      nav.appendChild(h('a', { class: 'stab', role: 'tab', id: 'tab-' + x[0], href: OP + 'settings/' + x[0] + '/', 'aria-selected': String(on), 'aria-controls': 'panel-' + x[0], tabindex: on ? 0 : -1,
        onclick: function (e) { e.preventDefault(); go('settings/' + x[0] + '/'); } }, ic(x[1], 'sm'), h('span', { text: t(x[2]) })));
    });
    nav.addEventListener('keydown', function (e) {
      var as = Array.prototype.slice.call(nav.querySelectorAll('.stab')), i = as.indexOf(document.activeElement);
      if (['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft'].indexOf(e.key) < 0 || i < 0) return;
      e.preventDefault(); var d = (e.key === 'ArrowDown' || e.key === 'ArrowRight') ? 1 : -1; if (document.documentElement.dir === 'rtl' && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) d = -d;
      as[(i + d + as.length) % as.length].focus();
    });
    var panel = h('section', { class: 'spanel', role: 'tabpanel', id: 'panel-' + S.settingsTab, 'aria-labelledby': 'tab-' + S.settingsTab });
    wrap.append(h('div', { class: 'settings-side' }, h('div', { class: 'page-top' }, ib('menu', t('menu'), toggleDrawer, 'nav-toggle'), h('h2', { text: t('settings') })), nav), panel);
    page.appendChild(wrap); el.main.appendChild(page);
    ({ general: settingsGeneral, 'quick-replies': settingsCanned, tags: settingsTags, ai: settingsAi, webhooks: settingsWebhooks, blocked: settingsBlocked })[S.settingsTab](panel);
  }
  function sHead(panel, title, hint) { panel.appendChild(h('header', { class: 'shead' }, h('h3', { text: title }), hint ? h('p', { text: hint }) : null)); }
  function sRow(label, hint, control) { return h('div', { class: 'srow' }, h('div', { class: 'srow-l' }, h('b', { text: label }), hint ? h('small', { text: hint }) : null), h('div', { class: 'srow-c' }, control)); }
  function sEmpty(icon, text) { return h('div', { class: 'empty sm' }, h('div', { class: 'ill' }, ic(icon)), h('p', { text: text })); }
  function settingsGeneral(p) {
    sHead(p, t('general'), t('generalHint'));
    var lang = selectBox({ label: t('language'), value: S.lang, onChange: setLang, options: (S.boot.languages || I.languages).map(function (l) { return { value: l, label: I.META[l].native }; }) });
    var themeSeg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': t('theme') });
    ['auto', 'light', 'dark'].forEach(function (th) {
      themeSeg.appendChild(h('button', { type: 'button', role: 'radio', 'aria-checked': String(S.theme === th), onclick: function () { setTheme(th); themeSeg.querySelectorAll('button').forEach(function (b, i) { b.setAttribute('aria-checked', String(['auto', 'light', 'dark'][i] === th)); }); } },
        ic(th === 'dark' ? 'moon' : th === 'light' ? 'sun' : 'sliders', 'sm'), t({ auto: 'themeAuto', light: 'themeLight', dark: 'themeDark' }[th])));
    });
    var snd = h('button', { class: 'switch', type: 'button', role: 'switch', 'aria-checked': String(Snd.enabled()), 'aria-label': t('sound'), onclick: function () { Snd.setEnabled(!Snd.enabled()); snd.setAttribute('aria-checked', String(Snd.enabled())); if (Snd.enabled()) Snd.play('notify'); } });
    var perm = ('Notification' in window) ? Notification.permission : 'denied';
    var notif = perm === 'granted' ? h('span', { class: 'pill ok', text: t('enabled') }) : h('button', { class: 'btn primary', type: 'button', text: t('enable'), onclick: function () { Notification.requestPermission().then(function () { renderMain(); }); } });
    p.appendChild(h('div', { class: 'scard' }, sRow(t('language'), t('languageHint'), lang), sRow(t('theme'), null, themeSeg), sRow(t('sound'), t('soundHint'), snd), sRow(t('notifications'), t('notificationsHint'), notif)));
  }
  function settingsCanned(p) {
    sHead(p, t('cannedResponses'), t('cannedHint'));
    var list = h('div', { class: 'slist' });
    var draw = function () {
      if (!S.boot.canned.length) return list.replaceChildren(sEmpty('bolt', t('noCanned')));
      list.replaceChildren.apply(list, S.boot.canned.map(function (c) {
        return h('div', { class: 'sitem' }, h('code', { text: '/' + c.shortcut }), h('span', { class: 'grow', dir: 'auto', text: c.text }),
          ib('trash', t('delete'), function () { api(OP + 'api/canned/' + c.id + '/delete/', { body: {} }).then(function () { S.boot.canned = S.boot.canned.filter(function (x) { return x.id !== c.id; }); draw(); }).catch(fail); }));
      }));
    };
    var sc = h('input', { class: 'inp', id: 'f-sc', maxlength: 40, placeholder: 'refund', autocomplete: 'off' });
    var tx = h('textarea', { class: 'inp area', id: 'f-tx', maxlength: 2000, rows: 3, placeholder: t('text') });
    var add = h('button', { class: 'btn primary', type: 'button', text: t('add'), onclick: function () {
      api(OP + 'api/canned/', { body: { shortcut: sc.value, text: tx.value, title: sc.value } }).then(function (d) { S.boot.canned = S.boot.canned.filter(function (x) { return x.id !== d.canned.id; }).concat([d.canned]); sc.value = tx.value = ''; draw(); }).catch(fail);
    } });
    draw();
    p.append(h('div', { class: 'scard' }, list), h('div', { class: 'scard form' }, h('h4', { text: t('add') }),
      h('div', { class: 'fld' }, h('label', { for: 'f-sc', text: t('shortcut') }), h('div', { class: 'prefix' }, h('span', { text: '/' }), sc)),
      h('div', { class: 'fld' }, h('label', { for: 'f-tx', text: t('text') }), tx), h('div', { class: 'actions' }, add)));
  }
  var PALETTE = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#64748b'];
  function settingsTags(p) {
    sHead(p, t('tags'), t('tagsHint'));
    var list = h('div', { class: 'slist' });
    var draw = function () {
      if (!S.boot.tags.length) return list.replaceChildren(sEmpty('tag', t('noTags')));
      list.replaceChildren.apply(list, S.boot.tags.map(function (tg) {
        return h('div', { class: 'sitem' }, h('i', { class: 'tagdot lg', style: 'background:' + tg.color }), h('span', { class: 'grow', text: tg.name }),
          ib('trash', t('delete') + ' ' + tg.name, function () { api(OP + 'api/tags/' + tg.id + '/delete/', { body: {} }).then(function () { S.boot.tags = S.boot.tags.filter(function (x) { return x.id !== tg.id; }); draw(); renderTagNav(); }).catch(fail); }));
      }));
    };
    var picked = PALETTE[S.boot.tags.length % PALETTE.length];
    var sw = h('div', { class: 'swatches', role: 'radiogroup', 'aria-label': t('color') });
    PALETTE.forEach(function (c) { sw.appendChild(h('button', { type: 'button', role: 'radio', class: 'swatch', style: '--c:' + c, 'aria-label': c, 'aria-checked': String(c === picked), onclick: function () { picked = c; sw.querySelectorAll('.swatch').forEach(function (b) { b.setAttribute('aria-checked', String(b.getAttribute('aria-label') === c)); }); } })); });
    var name = h('input', { class: 'inp', id: 'f-tag', maxlength: 40, placeholder: 'VIP', autocomplete: 'off' });
    var add = h('button', { class: 'btn primary', type: 'button', text: t('add'), onclick: function () {
      api(OP + 'api/tags/', { body: { name: name.value, color: picked } }).then(function (d) { if (!S.boot.tags.some(function (x) { return x.id === d.tag.id; })) S.boot.tags.push(d.tag); name.value = ''; draw(); renderTagNav(); }).catch(fail);
    } });
    name.addEventListener('keydown', function (e) { if (e.key === 'Enter') add.click(); });
    draw();
    p.append(h('div', { class: 'scard' }, list), h('div', { class: 'scard form' }, h('h4', { text: t('addTag') }),
      h('div', { class: 'fld' }, h('label', { for: 'f-tag', text: t('title') }), name), h('div', { class: 'fld' }, h('label', { text: t('color') }), sw), h('div', { class: 'actions' }, add)));
  }
  function settingsAi(p) {
    sHead(p, t('aiStatus'), t('aiHint'));
    var ai = S.boot.ai;
    p.appendChild(h('div', { class: 'scard' },
      sRow(t('aiStatus'), null, h('span', { class: 'pill' + (ai.enabled ? ' ok' : ''), text: ai.enabled ? t('enabled') : t('disabled') })),
      sRow(t('provider'), null, h('b', { text: ai.enabled ? ai.provider : '—' })), sRow(t('model'), null, h('b', { dir: 'ltr', text: ai.enabled ? (ai.model || '—') : '—' }))));
    p.appendChild(h('div', { class: 'scard code' }, h('pre', { dir: 'ltr', text: 'SUPCHAT = {\n    "AI": {\n        "ENABLED": True,\n        "PROVIDER": "openai",  # or "anthropic" / "custom"\n        "API_KEY": os.environ["AI_API_KEY"],\n        "MODEL": "<model id>",\n    },\n}' })));
  }
  function settingsWebhooks(p) {
    sHead(p, t('webhooks'), t('webhooksHint'));
    var list = h('div', { class: 'slist' });
    if (!S.boot.webhooks.length) list.appendChild(sEmpty('link', t('noWebhooks')));
    S.boot.webhooks.forEach(function (w) {
      var st = h('span', { class: 'pill' + (w.last_status && w.last_status < 400 ? ' ok' : (w.last_status || w.last_error ? ' bad' : '')), text: w.last_status ? 'HTTP ' + w.last_status : (w.last_error ? t('error') : '—') });
      list.appendChild(h('div', { class: 'sitem' }, h('b', { class: 'grow', text: w.name }), h('span', { class: 'pill', text: w.kind }), st,
        h('button', { class: 'btn sm', type: 'button', text: t('test'), onclick: function () { api(OP + 'api/webhooks/' + w.id + '/test/', { body: {} }).then(function (d) { st.textContent = d.status ? 'HTTP ' + d.status : t('error'); st.className = 'pill ' + (d.ok ? 'ok' : 'bad'); toast(d.ok ? 'OK' : (d.error || t('error')), !d.ok); }).catch(fail); } })));
    });
    p.appendChild(h('div', { class: 'scard' }, list));
  }
  function settingsBlocked(p) {
    sHead(p, t('blocked'), t('blockedHint'));
    var list = h('div', { class: 'slist' });
    if (!S.boot.blocked.length) list.appendChild(sEmpty('block', t('noBlocked')));
    S.boot.blocked.forEach(function (b) {
      list.appendChild(h('div', { class: 'sitem' }, h('b', { text: b.label }), h('span', { class: 'grow muted', dir: 'auto', text: b.reason || '—' }), h('small', { class: 'muted', text: fmtShort(b.created_at) }),
        h('button', { class: 'btn sm', type: 'button', text: t('unblock'), onclick: function () { api(OP + 'api/blocked/' + b.id + '/delete/', { body: {} }).then(function () { S.boot.blocked = S.boot.blocked.filter(function (x) { return x.id !== b.id; }); renderMain(); }).catch(fail); } })));
    });
    p.appendChild(h('div', { class: 'scard' }, list));
  }
  /* ------------------------------------------------------------- realtime */
  function connect() {
    if (es) es.close();
    es = new EventSource(OP + 'api/stream/', { withCredentials: true });
    es.addEventListener('connected', function () { scheduleRefresh(); if (S.active && S.view === 'chats') resync(); });
    var on = function (name, fn) { es.addEventListener(name, function (e) { try { fn(JSON.parse(e.data)); } catch (err) { /* ignore malformed */ } }); };
    on('conversation.created', function (c) { Snd.play('notify'); toast(t('newMessage') + ': ' + convName(c)); notify(convName(c), c.last_message_preview || t('newMessage')); scheduleRefresh(); });
    on('conversation.updated', function (c) {
      if (S.active && S.active.id === c.id) { Object.assign(S.active, c, { unread_count: 0 }); renderSub(); }
      scheduleRefresh();
    });
    on('conversation.deleted', function (d) { if (S.active && S.active.id === d.conversation) closeConversationView(); scheduleRefresh(); });
    on('message.created', function (m) {
      var inbound = m.sender_type === 'guest' || m.sender_type === 'user';
      if (S.active && S.active.id === m.conversation && S.view === 'chats') {
        if (m.is_internal) { if (!S.notes.some(function (n) { return n.id === m.id; })) { S.notes.push(m); renderInfo(); } return; }
        S.typing[m.conversation] = false; showTypingDots(); renderSub();
        var was = nearBottom; appendMessage(m); if (was) scrollBottom();
        if (inbound) { Snd.play('incoming'); if (document.visibilityState === 'visible') markRead(m.conversation); else notify(convName(S.active), m.text); }
      } else if (inbound) { Snd.play('incoming'); notify(m.sender_name || t('guest'), m.text || (m.attachment ? m.attachment.name : '')); }
    });
    on('message.read', function (d) {
      if (!S.active || S.active.id !== d.conversation) return;
      d.message_ids.forEach(function (id) { var m = S.msgs.filter(function (x) { return x.id === id; })[0]; if (m) { m.is_read = true; var n = msgEls.get(id), mt = n && n.querySelector('.meta .ic'); if (mt) mt.replaceWith(ic('checks')); } });
    });
    on('reaction.updated', function (d) {
      if (!S.active || S.active.id !== d.conversation) return;
      var m = S.msgs.filter(function (x) { return x.id === d.message_id; })[0], n = m && msgEls.get(m.id);
      if (n) { m.reactions = d.reactions; n.querySelector('.reacts').replaceWith(reactionsNode(m)); }
    });
    var tm = {};
    var setTyping = function (id, on) { S.typing[id] = on; renderSub(); showTypingDots(); var c = S.convs.filter(function (x) { return x.id === id; })[0], old = c && el.list && el.list.querySelector('[data-id="' + id + '"]'); if (old) old.replaceWith(rowFor(c)); };
    on('typing.start', function (d) { if (d.sender_type !== 'guest' && d.sender_type !== 'user') return; clearTimeout(tm[d.conversation]); tm[d.conversation] = setTimeout(function () { setTyping(d.conversation, false); }, 6000); setTyping(d.conversation, true); });
    on('typing.stop', function (d) { if (d.sender_type !== 'guest' && d.sender_type !== 'user') return; setTyping(d.conversation, false); });
    on('ai.handoff', function () { toast(t('aiHandoff')); Snd.play('notify'); });
  }
  async function resync() {
    try { var d = await api(OP + 'conversations/' + S.active.id + '/'); S.msgs = d.messages.filter(function (m) { return !m.is_internal; }); S.notes = d.messages.filter(function (m) { return m.is_internal; }); S.hasOlder = d.has_more; renderMessages(); renderInfo(); } catch (e) { /* ignore */ }
  }
  function markRead(id) { fetch(BASE + 'conversations/' + id + '/read/', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: '{}' }).catch(function () {}); }
  function notify(title, body) {
    if (document.visibilityState === 'visible' || !('Notification' in window) || Notification.permission !== 'granted') return;
    try { var n = new Notification(title, { body: (body || '').slice(0, 120), tag: 'supchat' }); n.onclick = function () { window.focus(); n.close(); }; } catch (_) { /* ignore */ }
  }

  /* ----------------------------------------------------------------- start */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { if ($('#layer').firstChild) closeLayer(); else closeDrawer(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (el.search) { $('#app').classList.add('nav-open'); el.search.focus(); } }
    if (e.altKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && S.convs.length) {
      e.preventDefault(); var i = S.convs.findIndex(function (c) { return S.active && c.id === S.active.id; }), n = S.convs[Math.max(0, Math.min(S.convs.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
      if (n) openConversation(n.id);
    }
  });
  document.addEventListener('click', function (e) {
    var app = $('#app'); if (!app.classList.contains('nav-open')) return;
    if (!e.target.closest('.nav, .rail, .nav-toggle, .layer')) closeDrawer();
  });
  window.addEventListener('popstate', function () { if (S.boot) applyRoute(); });
  window.addEventListener('hashchange', function () { var m = location.hash.match(/#c=([0-9a-f-]{36})/); if (m && S.boot) go('c/' + m[1] + '/', true); });
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible' && S.active) markRead(S.active.id); });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { if (el.themeBtn) el.themeBtn.replaceChildren(ic(themeIcon(), 'lg')); });

  async function start() {
    var boot;
    try { boot = await api(OP + 'api/bootstrap/'); } catch (e) { return; }
    S.boot = boot;
    applyLang(LS.get('supchat.op.lang', null) || I.detect(null, boot.languages));
    document.documentElement.style.setProperty('--accent', boot.accent || '#3390ec');
    var legacy = location.hash.match(/#c=([0-9a-f-]{36})/); if (legacy) history.replaceState({}, '', OP + 'c/' + legacy[1] + '/');
    var r = parseRoute(); S.view = r.view; if (r.settingsTab) S.settingsTab = r.tab; if (r.tab) S.settingsTab = r.tab;
    quiet(render); applyRoute(); await loadList(); connect();
    setInterval(function () { api(OP + 'api/heartbeat/', { body: {} }).catch(function () {}); }, 60000);
  }
  start();
})();
