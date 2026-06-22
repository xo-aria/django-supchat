// supchat.js
(function () {
  'use strict';

  const i18n = {
    en: {
      starting: 'Starting…',
      reconnecting: 'Reconnecting…',
      conversationClosed: 'Conversation closed.',
      failedToSend: 'Failed to send message.',
      messageNotSent: 'Message was not sent.',
      typing: 'Typing…',
      startConversation: 'Start a conversation',
      typeMessage: 'Type a message…',
      openChat: 'Open chat',
      closeChat: 'Close chat',
      close: 'Close',
      sendMessage: 'Send message',
      chatPanel: 'Chat panel',
      chatMessages: 'Chat messages',
      messageInput: 'Message input',
      online: 'Online',
      offline: 'Offline'
    },
    fa: {
      starting: 'در حال شروع…',
      reconnecting: 'در حال اتصال مجدد…',
      conversationClosed: 'مکالمه بسته شد.',
      failedToSend: 'خطا در ارسال پیام.',
      messageNotSent: 'پیام ارسال نشد.',
      typing: 'در حال نوشتن…',
      startConversation: 'یک مکالمه شروع کنید',
      typeMessage: 'پیام خود را بنویسید…',
      openChat: 'باز کردن چت',
      closeChat: 'بستن چت',
      close: 'بستن',
      sendMessage: 'ارسال پیام',
      chatPanel: 'پنل چت',
      chatMessages: 'پیام‌های چت',
      messageInput: 'ورودی پیام',
      online: 'آنلاین',
      offline: 'آفلاین'
    }
  };

  let currentLang = 'en';
  
  function detectLanguage() {
    const htmlLang = document.documentElement.getAttribute('lang');
    if (htmlLang && (htmlLang === 'fa' || htmlLang.startsWith('fa'))) {
      return 'fa';
    }
    
    const navLang = navigator.language || navigator.userLanguage || '';
    if (navLang.startsWith('fa')) {
      return 'fa';
    }
    
    return 'en';
  }

  function t(key) {
    return (i18n[currentLang] && i18n[currentLang][key]) || i18n.en[key] || key;
  }

  function applyTranslations(root) {
    root.querySelectorAll('[data-i18n]').forEach(function(el) {
      const key = el.getAttribute('data-i18n');
      el.textContent = t(key);
    });
    
    root.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
      const key = el.getAttribute('data-i18n-placeholder');
      el.placeholder = t(key);
    });
    
    root.querySelectorAll('[data-i18n-title]').forEach(function(el) {
      const key = el.getAttribute('data-i18n-title');
      el.title = t(key);
    });
    
    root.querySelectorAll('[data-i18n-aria-label]').forEach(function(el) {
      const key = el.getAttribute('data-i18n-aria-label');
      el.setAttribute('aria-label', t(key));
    });
  }

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

  function addMessage(root, message) {
    var box = $(root, '[data-supchat-messages]');
    if (!box) return;
    if (box.querySelector('[data-message-id="' + message.id + '"]')) return;
    
    var typingEl = box.querySelector('[data-typing-indicator]');
    if (typingEl) typingEl.remove();

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

    requestAnimationFrame(function () {
      box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
    });
  }

  function endpoint(root, conversationId, suffix) {
    var base = root.dataset.startUrl.replace(/start\/?$/, 'conversations/' + conversationId + '/');
    return base + suffix;
  }

  function bumpBadge(root) {
    var badge = $(root, '[data-supchat-badge]');
    if (!badge) return;
    var panel = $(root, '[data-supchat-panel]');
    if (panel && !panel.hasAttribute('hidden')) return;
    var count = parseInt(badge.textContent || '0', 10) + 1;
    badge.textContent = count > 99 ? '99+' : count;
    badge.removeAttribute('hidden');
  }

  function resetBadge(root) {
    var badge = $(root, '[data-supchat-badge]');
    if (badge) { badge.setAttribute('hidden', ''); badge.textContent = '0'; }
  }

  function showTyping(root) {
    var box = $(root, '[data-supchat-messages]');
    if (!box) return;
    if (box.querySelector('[data-typing-indicator]')) return;
    
    var el = document.createElement('div');
    el.className = 'supchat-message supchat-message-operator supchat-typing-bubble';
    el.dataset.typingIndicator = '1';
    
    var bubble = document.createElement('div');
    bubble.className = 'supchat-message-bubble typing-dots';
    bubble.innerHTML = '<span></span><span></span><span></span>';
    
    el.appendChild(bubble);
    box.appendChild(el);

    requestAnimationFrame(function () {
      box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
    });
  }

  function hideTyping(root) {
    var box = $(root, '[data-supchat-messages]');
    if (!box) return;
    var el = box.querySelector('[data-typing-indicator]');
    if (el) el.remove();
  }

  function init(root) {
    if (root.dataset.ready) return;
    root.dataset.ready = '1';

    currentLang = detectLanguage();
    applyTranslations(root);

    if (currentLang === 'fa') {
      root.setAttribute('dir', 'rtl');
    } else {
      root.setAttribute('dir', 'ltr');
    }

    var panel     = $(root, '[data-supchat-panel]');
    var toggle    = $(root, '[data-supchat-toggle]');
    var closeBtn  = $(root, '[data-supchat-close]');
    var minBtn    = $(root, '[data-supchat-minimize]');
    var form      = $(root, '[data-supchat-form]');
    var input     = $(root, '[data-supchat-input]');
    var sendBtn   = $(root, '.supchat-send-btn');

    var conversation = null;
    var events = null;
    var typingTimeout = null;

    function connect() {
      if (!conversation || events) return;
      events = new EventSource(endpoint(root, conversation.id, 'events/'), { withCredentials: true });

      events.addEventListener('message.created', function (e) {
        var msg = JSON.parse(e.data);
        addMessage(root, msg);
        if (msg.sender_type !== 'guest' && msg.sender_type !== 'user') {
          bumpBadge(root);
          if (!panel.hasAttribute('hidden')) {
            fetch(endpoint(root, conversation.id, 'read/'), {
              method: 'POST',
              credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(root) },
              body: '{}'
            });
          }
        }
        hideTyping(root);
      });

      events.addEventListener('typing.start', function (e) { 
        var data = {};
        try { data = JSON.parse(e.data); } catch(_) {}
        if (data.sender_type !== 'guest' && data.sender_type !== 'user') {
          showTyping(root); 
        }
      });
      
      events.addEventListener('typing.stop', function (e) { 
        var data = {};
        try { data = JSON.parse(e.data); } catch(_) {}
        if (data.sender_type !== 'guest' && data.sender_type !== 'user') {
          hideTyping(root); 
        }
      });

      events.addEventListener('conversation.closed', function () {
        setStatus(root, t('conversationClosed'));
        input.disabled = true;
        sendBtn.disabled = true;
      });

      events.addEventListener('operator.online', function () {
        var s = $(root, '[data-supchat-online]');
        if (s) s.style += 'background: var(--toast-success) !important;';
      });

      events.addEventListener('operator.offline', function () {
        var s = $(root, '[data-supchat-online]');
        if (s) s.style += 'background: var(--toast-error) !important;';
      });

      events.onerror = function () { setStatus(root, t('reconnecting')); };
      events.onopen  = function () { setStatus(root, ''); };
    }

    function loadMessages() {
      return fetch(endpoint(root, conversation.id, 'messages/'), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) data.messages.forEach(function (m) { addMessage(root, m); });
        });
    }

    function start() {
      if (conversation) { connect(); return Promise.resolve(conversation); }
      setStatus(root, t('starting'));
      return fetch(root.dataset.startUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(root) },
        body: '{}'
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || t('messageNotSent'));
          conversation = data.conversation;
          setStatus(root, '');
          connect();
          return loadMessages().then(function () { return conversation; });
        })
        .catch(function (err) { setStatus(root, err.message); });
    }

    function openPanel() {
      panel.removeAttribute('hidden');
      toggle.setAttribute('aria-expanded', 'true');
      resetBadge(root);
      start().then(function () { 
        input.focus();
        if (conversation) {
          fetch(endpoint(root, conversation.id, 'read/'), {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(root) },
            body: '{}'
          });
        }
      });
    }

    function closePanel() {
      panel.setAttribute('hidden', '');
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', function () {
      panel.hasAttribute('hidden') ? openPanel() : closePanel();
    });

    if (closeBtn) closeBtn.addEventListener('click', closePanel);

    input.addEventListener('input', function () {
      autoResize(input);
      sendBtn.disabled = !input.value.trim();
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (input.value.trim()) form.requestSubmit();
      }
    });

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
              setStatus(root, data.error || t('messageNotSent'));
            }
          })
          .catch(function () {
            setStatus(root, t('failedToSend'));
          });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-supchat]').forEach(init);
  });
})();
