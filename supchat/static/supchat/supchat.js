(function () {
  'use strict';

  /* ── Helpers ─────────────────────────────────────────── */

  function csrfToken(root) {
    var input = root.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function $(root, sel) { return root.querySelector(sel); }

  function setStatus(root, text) {
    var el = $(root, '[data-supchat-status]');
    if (el) el.textContent = text || '';
  }

  function formatTime(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (_) { return ''; }
  }

  function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 100) + 'px';
  }

  /* ── Message Rendering ───────────────────────────────── */

  function addMessage(root, message) {
    var box = $(root, '[data-supchat-messages]');
    if (box.querySelector('[data-message-id="' + message.id + '"]')) return;

    // Hide empty state
    var empty = $(root, '[data-supchat-empty]');
    if (empty) empty.setAttribute('hidden', '');

    var el = document.createElement('div');
    el.className = 'supchat-message supchat-message-' + message.sender_type;
    el.dataset.messageId = message.id;

    var bubble = document.createElement('div');
    bubble.className = 'supchat-message-bubble';
    bubble.textContent = message.text;

    var time = document.createElement('time');
    time.className = 'supchat-message-time';
    time.dateTime = message.created_at || '';
    time.textContent = formatTime(message.created_at);

    el.appendChild(bubble);
    el.appendChild(time);
    box.appendChild(el);

    // Smooth scroll
    requestAnimationFrame(function () {
      box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
    });
  }

  /* ── Endpoint Builder ────────────────────────────────── */

  function endpoint(root, conversationId, suffix) {
    var base = root.dataset.startUrl.replace(/start\/?$/, 'conversations/' + conversationId + '/');
    return base + suffix;
  }

  /* ── Badge Counter ───────────────────────────────────── */

  function bumpBadge(root) {
    var badge = $(root, '[data-supchat-badge]');
    if (!badge) return;
    var panel = $(root, '[data-supchat-panel]');
    if (panel && !panel.hasAttribute('hidden')) return; // panel is open
    var count = parseInt(badge.textContent || '0', 10) + 1;
    badge.textContent = count > 99 ? '99+' : count;
    badge.removeAttribute('hidden');
  }

  function resetBadge(root) {
    var badge = $(root, '[data-supchat-badge]');
    if (badge) { badge.setAttribute('hidden', ''); badge.textContent = '0'; }
  }

  /* ── Typing Indicator ────────────────────────────────── */

  function showTyping(root) {
    var el = $(root, '[data-supchat-typing]');
    if (el) el.removeAttribute('hidden');
  }

  function hideTyping(root) {
    var el = $(root, '[data-supchat-typing]');
    if (el) el.setAttribute('hidden', '');
  }

  /* ── Main Init ───────────────────────────────────────── */

  function init(root) {
    if (root.dataset.ready) return;
    root.dataset.ready = '1';

    var panel     = $(root, '[data-supchat-panel]');
    var toggle    = $(root, '[data-supchat-toggle]');
    var closeBtn  = $(root, '[data-supchat-close]');
    var minBtn    = $(root, '[data-supchat-minimize]');
    var form      = $(root, '[data-supchat-form]');
    var input     = $(root, '[data-supchat-input]');
    var sendBtn   = $(root, '.supchat-send-btn');

    var conversation = null;
    var events = null;

    /* ── SSE Connection ── */
    function connect() {
      if (!conversation || events) return;
      events = new EventSource(endpoint(root, conversation.id, 'events/'), { withCredentials: true });

      events.addEventListener('message.created', function (e) {
        var msg = JSON.parse(e.data);
        addMessage(root, msg);
        if (msg.sender_type !== 'guest' && msg.sender_type !== 'user') {
          bumpBadge(root);
        }
        hideTyping(root);
      });

      events.addEventListener('typing.start', function () { showTyping(root); });
      events.addEventListener('typing.stop',  function () { hideTyping(root); });

      events.addEventListener('conversation.closed', function () {
        setStatus(root, 'Conversation closed.');
        input.disabled = true;
        sendBtn.disabled = true;
      });

      events.addEventListener('operator.online', function () {
        var s = $(root, '[data-supchat-online]');
        if (s) s.innerHTML = '<span class="supchat-dot"></span>Online';
      });

      events.addEventListener('operator.offline', function () {
        var s = $(root, '[data-supchat-online]');
        if (s) s.innerHTML = '<span class="supchat-dot" style="background:#f59e0b"></span>Away';
      });

      events.onerror = function () { setStatus(root, 'Reconnecting…'); };
      events.onopen  = function () { setStatus(root, ''); };
    }

    /* ── Load History ── */
    function loadMessages() {
      return fetch(endpoint(root, conversation.id, 'messages/'), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) data.messages.forEach(function (m) { addMessage(root, m); });
        });
    }

    /* ── Start / Resume Conversation ── */
    function start() {
      if (conversation) { connect(); return Promise.resolve(conversation); }
      setStatus(root, 'Starting…');
      return fetch(root.dataset.startUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(root) },
        body: '{}'
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || 'Could not start chat.');
          conversation = data.conversation;
          setStatus(root, '');
          connect();
          return loadMessages().then(function () { return conversation; });
        })
        .catch(function (err) { setStatus(root, err.message); });
    }

    /* ── Panel Toggle ── */
    function openPanel() {
      panel.removeAttribute('hidden');
      toggle.setAttribute('aria-expanded', 'true');
      resetBadge(root);
      start().then(function () { input.focus(); });
    }

    function closePanel() {
      panel.setAttribute('hidden', '');
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', function () {
      panel.hasAttribute('hidden') ? openPanel() : closePanel();
    });

    if (closeBtn) closeBtn.addEventListener('click', closePanel);

    /* ── Auto-resize Textarea ── */
    input.addEventListener('input', function () {
      autoResize(input);
      sendBtn.disabled = !input.value.trim();
    });

    /* ── Enter to send, Shift+Enter for newline ── */
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (input.value.trim()) form.requestSubmit();
      }
    });

    /* ── Send Message ── */
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var text = input.value.trim();
      if (!text) return;

      start().then(function () {
        if (!conversation) return;
        input.value = '';
        autoResize(input);
        sendBtn.disabled = true;

        return fetch(endpoint(root, conversation.id, 'messages/'), {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(root) },
          body: JSON.stringify({ text: text })
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.ok) {
              addMessage(root, data.message);
            } else {
              setStatus(root, data.error || 'Message was not sent.');
            }
          })
          .catch(function () {
            setStatus(root, 'Failed to send message.');
          });
      });
    });
  }

  /* ── Bootstrap ── */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-supchat]').forEach(init);
  });
})();