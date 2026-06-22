// operator.js
const i18n = {
    en: {
        closeConversation: 'Close',
        deleteConversation: 'Delete',
        confirmClose: 'Close this conversation?',
        confirmDelete: 'Are you sure you want to delete this conversation?',
        conversationClosed: 'Conversation closed',
        conversationDeleted: 'Conversation deleted',
        failedToClose: 'Failed to close',
        failedToDelete: 'Failed to delete',
        failedToSend: 'Failed to send',
        connectionError: 'Connection error',
        failedToLoad: 'Failed to load conversation',
        failedToLoadPage: 'Failed to load page',
        selectConversation: 'Select a conversation',
        chooseFromSidebar: 'Choose from the sidebar to start chatting',
        noConversations: 'No conversations yet',
        noMessages: 'No messages',
        guestIsTyping: 'Guest is typing',
        userIsTyping: 'User is typing',
        operator: 'Operator',
        user: 'User',
        guest: 'Guest',
        system: 'System',
        open: 'Open',
        closed: 'Closed',
        messages: 'messages',
        started: 'Started',
        thisConversationIsClosed: 'This conversation is closed',
        typeMessage: 'Type a message...',
        send: 'Send',
        deleting: 'Deleting...',
        delete: 'Delete',
        justNow: 'just now',
        m: 'm',
        h: 'h',
        d: 'd',
        analytics: 'Analytics',
        dashboard: 'Dashboard',
        conversations: 'Conversations',
        today: 'Today',
        total: 'Total',
        last7Days: 'Last 7 Days',
        last30Days: 'Last 30 Days',
        statusDistribution: 'Status Distribution',
        search: 'Search...',
        onlineOperators: 'Online Operators',
        darkMode: 'Dark Mode',
        lightMode: 'Light Mode',
        language: 'Language'
    },
    fa: {
        closeConversation: 'بستن',
        deleteConversation: 'حذف',
        confirmClose: 'مکالمه بسته شود؟',
        confirmDelete: 'آیا از حذف این مکالمه اطمینان دارید؟',
        conversationClosed: 'مکالمه بسته شد',
        conversationDeleted: 'مکالمه حذف شد',
        failedToClose: 'خطا در بستن',
        failedToDelete: 'خطا در حذف',
        failedToSend: 'خطا در ارسال',
        connectionError: 'خطا در اتصال',
        failedToLoad: 'خطا در بارگذاری مکالمه',
        failedToLoadPage: 'خطا در بارگذاری صفحه',
        selectConversation: 'یک مکالمه را انتخاب کنید',
        chooseFromSidebar: 'برای شروع چت، یکی را از منوی کناری انتخاب کنید',
        noConversations: 'هنوز مکالمه‌ای وجود ندارد',
        noMessages: 'پیامی وجود ندارد',
        guestIsTyping: 'مهمان در حال نوشتن است',
        userIsTyping: 'کاربر در حال نوشتن است',
        operator: 'اپراتور',
        user: 'کاربر',
        guest: 'مهمان',
        system: 'سیستم',
        open: 'باز',
        closed: 'بسته',
        messages: 'پیام',
        started: 'شروع',
        thisConversationIsClosed: 'این مکالمه بسته شده است',
        typeMessage: 'پیام خود را بنویسید...',
        send: 'ارسال',
        deleting: 'در حال حذف...',
        delete: 'حذف',
        justNow: 'لحظاتی پیش',
        m: 'دقیقه',
        h: 'ساعت',
        d: 'روز',
        analytics: 'آمار',
        dashboard: 'داشبورد',
        conversations: 'مکالمات',
        today: 'امروز',
        total: 'کل',
        last7Days: '۷ روز گذشته',
        last30Days: '۳۰ روز گذشته',
        statusDistribution: 'توزیع وضعیت',
        search: 'جستجو...',
        onlineOperators: 'اپراتورهای آنلاین',
        darkMode: 'حالت تاریک',
        lightMode: 'حالت روشن',
        language: 'زبان'
    }
};

let currentLang = localStorage.getItem('supchat-lang') || 'fa';
let currentConversationId = null;
let currentEventSource = null;
let chart7Instance = null;
let chart30Instance = null;
let chartStatusInstance = null;
let deleteTargetId = null;
let currentRoute = 'dashboard';
let typingTimeout = null;

function t(key) {
    return (i18n[currentLang] && i18n[currentLang][key]) || i18n.en[key] || key;
}

function toggleLang() {
    currentLang = currentLang === 'en' ? 'fa' : 'en';
    localStorage.setItem('supchat-lang', currentLang);
    document.documentElement.setAttribute('dir', currentLang === 'fa' ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', currentLang);
    loadRoute(currentRoute, false);
    updateUITexts();
}

function updateUITexts() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
}

function initApp() {
    initTheme();
    initRouter();
    document.documentElement.setAttribute('dir', currentLang === 'fa' ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', currentLang);
    if (ACTIVE_PAGE === 'analytics') {
        initAnalyticsCharts();
    }
    updateUITexts();
}

function initTheme() {
    const saved = localStorage.getItem('supchat-theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    } else {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    }
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('supchat-theme', next);
    updateChartsTheme();
}

function updateChartsTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? '#334155' : '#f0f2f5';
    const textColor = isDark ? '#64748b' : '#94a3b8';

    if (chart7Instance) {
        chart7Instance.options.scales.x.grid.color = gridColor;
        chart7Instance.options.scales.y.grid.color = gridColor;
        chart7Instance.options.scales.x.ticks.color = textColor;
        chart7Instance.options.scales.y.ticks.color = textColor;
        chart7Instance.update('none');
    }
    if (chart30Instance) {
        chart30Instance.options.scales.x.grid.color = gridColor;
        chart30Instance.options.scales.y.grid.color = gridColor;
        chart30Instance.options.scales.x.ticks.color = textColor;
        chart30Instance.options.scales.y.ticks.color = textColor;
        chart30Instance.update('none');
    }
    if (chartStatusInstance) {
        chartStatusInstance.options.plugins.legend.labels.color = textColor;
        chartStatusInstance.update('none');
    }
}

function initRouter() {
    window.addEventListener('popstate', handleRoute);
    handleRoute();
}

function handleRoute() {
    const path = window.location.pathname;
    let route = 'dashboard';
    if (path.includes('/analytics')) {
        route = 'analytics';
    }
    if (route !== currentRoute) {
        loadRoute(route, false);
    }
}

function navigate(event, path) {
    event.preventDefault();
    const route = path.includes('/analytics') ? 'analytics' : 'dashboard';
    if (route === currentRoute) return;
    window.history.pushState({ route }, '', path);
    loadRoute(route, true);
}

async function loadRoute(route, animate = true) {
    currentRoute = route;

    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.route === route);
    });

    const mainContent = document.getElementById('mainContent');
    if (animate) {
        mainContent.style.opacity = '0';
        mainContent.style.transform = 'translateY(8px)';
    }

    const partialUrl = route === 'analytics'
        ? '/supchat/operator/partials/analytics/'
        : '/supchat/operator/partials/dashboard/';

    try {
        const res = await fetch(partialUrl);
        const html = await res.text();
        mainContent.innerHTML = html;

        if (animate) {
            requestAnimationFrame(() => {
                mainContent.style.transition = 'opacity 0.2s, transform 0.2s';
                mainContent.style.opacity = '1';
                mainContent.style.transform = 'translateY(0)';
            });
        }

        if (route === 'analytics') {
            await loadAnalyticsData();
        }
        updateUITexts();
    } catch (err) {
        console.error('Route load error:', err);
        showToast(t('failedToLoadPage'), 'error');
    }
}

async function loadAnalyticsData() {
    try {
        const res = await fetch('/supchat/operator/analytics/data/');
        const data = await res.json();
        if (!data.ok) return;

        window.CHART_LABELS_7 = data.labels_7;
        window.CHART_DATA_7 = data.data_7;
        window.CHART_LABELS_30 = data.labels_30;
        window.CHART_DATA_30 = data.data_30;

        initAnalyticsCharts();
    } catch (err) {
        console.error('Analytics data error:', err);
    }
}

function initAnalyticsCharts() {
    if (typeof Chart === 'undefined') return;

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? '#334155' : '#f0f2f5';
    const textColor = isDark ? '#64748b' : '#94a3b8';

    const ctx7 = document.getElementById('chart7Days');
    if (ctx7 && window.CHART_LABELS_7) {
        if (chart7Instance) chart7Instance.destroy();
        chart7Instance = new Chart(ctx7, {
            type: 'line',
            data: {
                labels: window.CHART_LABELS_7,
                datasets: [{
                    label: t('conversations'),
                    data: window.CHART_DATA_7,
                    borderColor: '#4f46e5',
                    backgroundColor: 'rgba(79, 70, 229, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#4f46e5',
                    pointBorderColor: isDark ? '#1e293b' : '#fff',
                    pointBorderWidth: 2,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                }]
            },
            options: getLineChartOptions(gridColor, textColor)
        });
    }

    const ctx30 = document.getElementById('chart30Days');
    if (ctx30 && window.CHART_LABELS_30) {
        if (chart30Instance) chart30Instance.destroy();
        chart30Instance = new Chart(ctx30, {
            type: 'bar',
            data: {
                labels: window.CHART_LABELS_30,
                datasets: [{
                    label: t('conversations'),
                    data: window.CHART_DATA_30,
                    backgroundColor: 'rgba(79, 70, 229, 0.7)',
                    borderColor: '#4f46e5',
                    borderWidth: 1,
                    borderRadius: 6,
                }]
            },
            options: getBarChartOptions(gridColor, textColor)
        });
    }

    const ctxStatus = document.getElementById('chartStatus');
    if (ctxStatus) {
        if (chartStatusInstance) chartStatusInstance.destroy();
        const openCount = document.querySelector('.analytics-value')?.textContent || 0;
        chartStatusInstance = new Chart(ctxStatus, {
            type: 'doughnut',
            data: {
                labels: [t('open'), t('closed')],
                datasets: [{
                    data: [parseInt(openCount) || 0, 0],
                    backgroundColor: ['#10b981', '#3b82f6'],
                    borderColor: isDark ? '#1e293b' : '#fff',
                    borderWidth: 3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: textColor,
                            padding: 16,
                            font: { size: 12 },
                            usePointStyle: true,
                        }
                    },
                    tooltip: {
                        backgroundColor: isDark ? '#273449' : '#1a202c',
                        padding: 10,
                        cornerRadius: 6,
                    }
                },
                cutout: '65%',
            }
        });
    }
}

function getLineChartOptions(gridColor, textColor) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: document.documentElement.getAttribute('data-theme') === 'dark' ? '#273449' : '#1a202c',
                padding: 10,
                cornerRadius: 6,
                titleFont: { size: 11 },
                bodyFont: { size: 12 },
            }
        },
        scales: {
            x: {
                grid: { color: gridColor, drawBorder: false },
                ticks: { color: textColor, font: { size: 10 } },
                border: { display: false }
            },
            y: {
                beginAtZero: true,
                grid: { color: gridColor, drawBorder: false },
                ticks: {
                    color: textColor,
                    font: { size: 10 },
                    precision: 0,
                },
                border: { display: false }
            }
        },
        interaction: { intersect: false, mode: 'index' }
    };
}

function getBarChartOptions(gridColor, textColor) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: document.documentElement.getAttribute('data-theme') === 'dark' ? '#273449' : '#1a202c',
                padding: 10,
                cornerRadius: 6,
            }
        },
        scales: {
            x: {
                grid: { display: false },
                ticks: { color: textColor, font: { size: 10 } },
                border: { display: false }
            },
            y: {
                beginAtZero: true,
                grid: { color: gridColor, drawBorder: false },
                ticks: {
                    color: textColor,
                    font: { size: 10 },
                    precision: 0,
                },
                border: { display: false }
            }
        }
    };
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

function filterConversations() {
    const q = document.getElementById('searchInput').value.toLowerCase();
    document.querySelectorAll('.conv-item').forEach(el => {
        const name = (el.dataset.participant || '').toLowerCase();
        el.style.display = name.includes(q) ? '' : 'none';
    });
}

async function loadConversation(convId) {
    if (currentRoute !== 'dashboard') {
        window.history.pushState({ route: 'dashboard' }, '', '/supchat/operator/');
        await loadRoute('dashboard', false);
    }

    currentConversationId = convId;

    document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
    const activeItem = document.querySelector(`.conv-item[data-id="${convId}"]`);
    if (activeItem) activeItem.classList.add('active');

    if (window.innerWidth <= 900) {
        document.getElementById('sidebar').classList.remove('open');
    }

    try {
        const res = await fetch(`/supchat/operator/conversations/${convId}/`);
        const data = await res.json();

        if (!data.ok) {
            showToast(data.error || t('failedToLoad'), 'error');
            return;
        }

        renderChatArea(data.conversation, data.messages);
        connectSSE(convId);
    } catch (err) {
        console.error('Load error:', err);
        showToast(t('connectionError'), 'error');
    }
}

function renderChatArea(conversation, messages) {
    const chatContainer = document.getElementById('chatContainer');
    if (!chatContainer) return;

    const name = conversation.participant || 'Unknown';
    const created = new Date(conversation.created_at).toLocaleString();

    chatContainer.innerHTML = `
        <div class="chat-header">
            <div class="chat-header-info">
                <div class="conv-avatar">${name.charAt(0).toUpperCase()}</div>
                <div>
                    <h3>${escapeHtml(name)}</h3>
                    <small>${conversation.message_count} ${t('messages')} · ${t('started')} ${created}</small>
                </div>
            </div>
            <div class="chat-header-actions">
                <span class="status-chip ${conversation.status}">${conversation.status === 'open' ? t('open') : t('closed')}</span>
                ${conversation.status === 'open' ? `
                    <button class="btn btn-ghost close-btn" onclick="closeConversation('${conversation.id}')">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                        </svg>
                        ${t('closeConversation')}
                    </button>
                ` : ''}
                <button class="btn btn-icon" onclick="openDeleteModal('${conversation.id}')" title="${t('deleteConversation')}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        </div>
        <div class="chat-messages" id="chatMessages">
            ${messages.map(renderMessage).join('')}
            <div class="typing-indicator" id="typingIndicator" style="display: none;">
                <span class="typing-text"></span>
                <span class="typing-dots"><span></span><span></span><span></span></span>
            </div>
        </div>
        ${conversation.status === 'open' ? `
            <div class="chat-input-area">
                <textarea id="messageInput" rows="1" placeholder="${t('typeMessage')}"
                          onkeydown="handleKeyDown(event)" oninput="handleInput(this)"></textarea>
                <button class="btn btn-primary" onclick="sendMessage()" id="sendBtn">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                    </svg>
                    ${t('send')}
                </button>
            </div>
        ` : `
            <div class="closed-notice">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                ${t('thisConversationIsClosed')}
            </div>
        `}
    `;

    scrollToBottom();
    const input = document.getElementById('messageInput');
    if (input) input.focus();
}

function handleInput(el) {
    autoResize(el);
    if (!currentConversationId) return;
    fetch(`/supchat/operator/conversations/${currentConversationId}/typing/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': CSRF_TOKEN,
        },
        body: JSON.stringify({ is_typing: true }),
    });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        fetch(`/supchat/operator/conversations/${currentConversationId}/typing/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({ is_typing: false }),
        });
    }, 2000);
}

function renderMessage(msg) {
    const cls = `msg-${msg.sender_type}`;
    let senderType = '';

    switch (msg.sender_type) {
        case 'operator': senderType = t('operator'); break;
        case 'user': senderType = t('user'); break;
        case 'guest': senderType = t('guest'); break;
        case 'system': senderType = t('system'); break;
    }

    const time = new Date(msg.created_at).toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit'
    });

    return `
        <div class="msg ${cls}" data-id="${msg.id}">
            <div class="msg-sender">${escapeHtml(msg.sender_user)} | ${senderType}</div>
            <div class="msg-text">${escapeHtml(msg.text)}</div>
            <div class="msg-time">${time}</div>
        </div>
    `;
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    if (!text || !currentConversationId) return;

    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;

    try {
        const res = await fetch(`/supchat/operator/conversations/${currentConversationId}/send/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({ text }),
        });

        const data = await res.json();
        if (data.ok) {
            appendMessage(data.message);
            input.value = '';
            input.style.height = 'auto';
            scrollToBottom();
        } else {
            showToast(data.error || t('failedToSend'), 'error');
        }
    } catch (err) {
        showToast(t('connectionError'), 'error');
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

async function closeConversation(convId) {
    if (!confirm(t('confirmClose'))) return;

    try {
        const res = await fetch(`/supchat/operator/conversations/${convId}/close/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF_TOKEN },
        });
        const data = await res.json();
        if (data.ok) {
            showToast(t('conversationClosed'), 'success');
            loadConversation(convId);
            refreshConversationList();
        } else {
            showToast(data.error || t('failedToClose'), 'error');
        }
    } catch (err) {
        showToast(t('connectionError'), 'error');
    }
}

function openDeleteModal(convId) {
    deleteTargetId = convId;
    document.getElementById('deleteModal').classList.add('show');
    document.getElementById('confirmDeleteBtn').onclick = confirmDelete;
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.remove('show');
    deleteTargetId = null;
}

async function confirmDelete() {
    if (!deleteTargetId) return;
    const btn = document.getElementById('confirmDeleteBtn');
    btn.disabled = true;
    btn.textContent = t('deleting');

    try {
        const res = await fetch(`/supchat/operator/conversations/${deleteTargetId}/delete/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF_TOKEN },
        });
        const data = await res.json();
        if (data.ok) {
            showToast(t('conversationDeleted'), 'success');
            const el = document.querySelector(`.conv-item[data-id="${deleteTargetId}"]`);
            if (el) el.remove();
            if (currentConversationId === deleteTargetId) {
                currentConversationId = null;
                if (currentEventSource) {
                    currentEventSource.close();
                    currentEventSource = null;
                }
                const chatContainer = document.getElementById('chatContainer');
                if (chatContainer) {
                    chatContainer.innerHTML = `
                        <div class="empty-main">
                            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                            </svg>
                            <h2>${t('selectConversation')}</h2>
                            <p>${t('chooseFromSidebar')}</p>
                        </div>
                    `;
                }
            }
            closeDeleteModal();
        } else {
            showToast(data.error || t('failedToDelete'), 'error');
        }
    } catch (err) {
        showToast(t('connectionError'), 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = t('delete');
    }
}

function connectSSE(convId) {
    if (currentEventSource) {
        currentEventSource.close();
    }

    currentEventSource = new EventSource(`/supchat/operator/conversations/${convId}/events/`);

    currentEventSource.addEventListener('message.created', function(e) {
        const msg = JSON.parse(e.data);
        appendMessage(msg);
        scrollToBottom();
    });

    currentEventSource.addEventListener('conversation.closed', function() {
        loadConversation(convId);
        refreshConversationList();
    });

    currentEventSource.addEventListener('message.read', function(e) {
        const data = JSON.parse(e.data);
        data.message_ids.forEach(id => {
            const el = document.querySelector(`.msg[data-id="${id}"]`);
            if (el) el.classList.add('read');
        });
    });

    currentEventSource.addEventListener('typing.start', function(e) {
        let data = {};
        try { data = JSON.parse(e.data); } catch(_) {}
        if (data.sender_type === 'guest' || data.sender_type === 'user') {
            const indicator = document.getElementById('typingIndicator');
            if (indicator) {
                indicator.style.display = 'flex';
                const text = indicator.querySelector('.typing-text');
                if(text) text.textContent = data.sender_type === 'guest' ? t('guestIsTyping') : t('userIsTyping');
                scrollToBottom();
            }
        }
    });

    currentEventSource.addEventListener('typing.stop', function(e) {
        let data = {};
        try { data = JSON.parse(e.data); } catch(_) {}
        if (data.sender_type === 'guest' || data.sender_type === 'user') {
            const indicator = document.getElementById('typingIndicator');
            if (indicator) indicator.style.display = 'none';
        }
    });

    currentEventSource.onerror = function() {
        console.warn('SSE error, retrying...');
    };
}

function appendMessage(msg) {
    const container = document.getElementById('chatMessages');
    if (!container) return;
    if (document.querySelector(`.msg[data-id="${msg.id}"]`)) return;
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        container.insertBefore(document.createRange().createContextualFragment(renderMessage(msg)), indicator);
    } else {
        container.insertAdjacentHTML('beforeend', renderMessage(msg));
    }
}

function scrollToBottom() {
    const container = document.getElementById('chatMessages');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    let icon = '';
    if (type === 'success') {
        icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
    } else if (type === 'error') {
        icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    } else {
        icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
    }

    toast.innerHTML = `${icon}<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        toast.style.transition = 'all 0.25s';
        setTimeout(() => toast.remove(), 250);
    }, 3000);
}

async function refreshConversationList() {
    try {
        const res = await fetch('/supchat/operator/conversations/');
        const data = await res.json();
        if (!data.ok) return;

        const list = document.getElementById('conversationList');
        if (!list) return;

        if (data.conversations.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                    <p>${t('noConversations')}</p>
                </div>
            `;
            return;
        }

        list.innerHTML = data.conversations.map(conv => {
            const preview = conv.last_message_preview || t('noMessages');
            const initial = conv.participant.charAt(0).toUpperCase();
            return `
                <div class="conv-item ${conv.status === 'closed' ? 'is-closed' : ''} ${conv.id === currentConversationId ? 'active' : ''}"
                     data-id="${conv.id}"
                     data-participant="${escapeHtml(conv.participant)}"
                     onclick="loadConversation('${conv.id}')">
                    <div class="conv-avatar">${initial}</div>
                    <div class="conv-content">
                        <div class="conv-top">
                            <span class="conv-name">${escapeHtml(conv.participant)}</span>
                            <span class="conv-time">${conv.last_message_at ? timeAgo(conv.last_message_at) : ''}</span>
                        </div>
                        <div class="conv-bottom">
                            <span class="conv-preview">
                                ${conv.unread_count > 0 ? '<span class="unread-dot"></span>' : ''}
                                ${escapeHtml(preview)}
                            </span>
                            ${conv.unread_count > 0 ? `<span class="unread-badge">${conv.unread_count}</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (err) {
        console.error('Refresh error:', err);
    }
}

function timeAgo(isoString) {
    const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
    if (seconds < 60) return t('justNow');
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}${t('m')}`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}${t('h')}`;
    const days = Math.floor(hours / 24);
    return `${days}${t('d')}`;
}

setInterval(refreshConversationList, 30000);

document.addEventListener('click', function(e) {
    if (e.target.id === 'deleteModal') {
        closeDeleteModal();
    }
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeDeleteModal();
    }
});