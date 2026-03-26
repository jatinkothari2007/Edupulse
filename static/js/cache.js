/**
 * EduPulse cache.js — global utilities.
 * Loaded AFTER firebase-init.js. Relies on initFirebase(), apiCall(),
 * and waitForCurrentUser() being defined by firebase-init.js.
 */

/* ══════════════════════════════════════════════════════
   API CACHE (simple TTL cache for GET responses)
   ══════════════════════════════════════════════════════ */
const _apiCache = {};

async function cachedApiCall(url, method = 'GET', body = null, ttl = 60) {
    const key = method + ':' + url + (body ? JSON.stringify(body) : '');
    const now = Date.now();
    if (method === 'GET' && _apiCache[key] && now - _apiCache[key].ts < ttl * 1000) {
        return _apiCache[key].data;
    }
    const result = await apiCall(url, method, body);
    if (method === 'GET') _apiCache[key] = { data: result, ts: now };
    return result;
}

function clearCache(pattern) {
    Object.keys(_apiCache).forEach(k => {
        if (!pattern || k.includes(pattern)) delete _apiCache[k];
    });
}

/* ══════════════════════════════════════════════════════
   AUTH GUARD — single promise, backed by firebase-init.js
   ══════════════════════════════════════════════════════ */

/* Internal resolved user stored after first auth + Firestore load */
let _epUser        = null;
let _epUserResolvers = [];
let _epUserPromise   = null;

/**
 * Returns a Promise<epUser|null>.
 * epUser = { uid, name, role, ... } (from Firestore users collection)
 * Resolves once, immediately if already resolved.
 */
function waitForAuth() {
    if (_epUserPromise) return _epUserPromise;
    _epUserPromise = new Promise(resolve => {
        if (_epUser !== null) { resolve(_epUser); return; }
        _epUserResolvers.push(resolve);
    });
    return _epUserPromise;
}

function _resolveEpUser(user) {
    _epUser = user;
    _epUserResolvers.forEach(fn => fn(user));
    _epUserResolvers = [];
}

/* Called once by DOMContentLoaded after initFirebase() completes */
async function _bootAuth() {
    try {
        /* waitForCurrentUser() in firebase-init.js awaits the first
           onAuthStateChanged event — so this never races */
        const fireUser = await waitForCurrentUser();

        if (!fireUser) {
            _resolveEpUser(null);
            return;
        }

        /* Load full user profile from Firestore */
        const snap = await window.db.collection('users').doc(fireUser.uid).get();

        if (!snap.exists) {
            await firebase.auth().signOut();
            _resolveEpUser(null);
            return;
        }

        const data = snap.data();

        if (data.active === false) {
            showToast('Your account has been deactivated. Contact admin.', 'error');
            await firebase.auth().signOut();
            _resolveEpUser(null);
            return;
        }

        const user = { uid: fireUser.uid, ...data };
        window.currentUser = user;   /* ← required by SPA router to call onPageReady */
        _resolveEpUser(user);

        /* Populate sidebar now that we have user data */
        _populateSidebar(user);
        _buildNav(user.role);


        /** Track login time + count for ALL users (best-effort, non-blocking) */
        window.db.collection('users').doc(fireUser.uid).update({
            lastLogin  : firebase.firestore.FieldValue.serverTimestamp(),
            loginCount : firebase.firestore.FieldValue.increment(1),
        }).catch(function(){});   /* silently ignore — never block login */

        /** Invalidate the Login Activity page cache so stats refresh on next visit */
        try { sessionStorage.removeItem('ep_la_v1'); } catch(e) {}

        /** Log student login engagement (best-effort) */
        if (user.role === 'student') {
            apiCall('/api/student/engagement/login', 'POST').catch(() => {});
        }



    } catch (err) {
        console.warn('[EduPulse] _bootAuth error:', err.message);
        _resolveEpUser(null);
    }
}

function handleLogout() {
    firebase.auth().signOut()
        .then(() => { window.location.href = '/'; })
        .catch(e => showToast('Logout failed: ' + e.message, 'error'));
}

function getCurrentUser() { return _epUser; }

/* ══════════════════════════════════════════════════════
   SIDEBAR — navigation builder
   ══════════════════════════════════════════════════════ */
const NAV_MAP = {
    admin: [
        { href:'/dashboard/admin',              icon:'fa-tachometer-alt', label:'Dashboard' },
        { href:'/pages/admin/users',            icon:'fa-users',          label:'Manage Users' },
        { href:'/pages/admin/login-activity',   icon:'fa-clock',          label:'Login Activity' },
        { href:'/pages/messaging',              icon:'fa-comments',        label:'Messages' },
        { href:'/pages/notifications',          icon:'fa-bell',            label:'Notifications' },
    ],


    faculty_advisor: [
        { href:'/dashboard/faculty',               icon:'fa-tachometer-alt',       label:'Dashboard' },
        { href:'/pages/faculty/classes',           icon:'fa-chalkboard',           label:'Classes' },
        { href:'/pages/faculty/risk-scores',       icon:'fa-exclamation-triangle', label:'Risk Scores' },
        { href:'/pages/faculty/quiz-manage',       icon:'fa-clipboard-list',       label:'Pulse Quiz' },
        { href:'/pages/faculty/counsellor-assign', icon:'fa-user-check',           label:'Assign Counsellor' },
        { href:'/pages/messaging',                 icon:'fa-comments',             label:'Messages' },
        { href:'/pages/notifications',             icon:'fa-bell',                 label:'Notifications' },
    ],
    subject_teacher: [
        { href:'/dashboard/teacher',         icon:'fa-tachometer-alt', label:'Dashboard' },
        { href:'/pages/teacher/classes',     icon:'fa-chalkboard',     label:'My Classes' },
        { href:'/pages/teacher/attendance',  icon:'fa-calendar-check', label:'Attendance' },
        { href:'/pages/teacher/assignments', icon:'fa-tasks',          label:'Assignments' },
        { href:'/pages/teacher/marks',       icon:'fa-star',           label:'Marks' },
        { href:'/pages/teacher/notes',       icon:'fa-sticky-note',    label:'Notes' },
        { href:'/pages/messaging',           icon:'fa-comments',       label:'Messages' },
        { href:'/pages/notifications',       icon:'fa-bell',           label:'Notifications' },
    ],
    counsellor: [
        { href:'/dashboard/counsellor',          icon:'fa-tachometer-alt', label:'Dashboard' },
        { href:'/pages/counsellor/students',     icon:'fa-users',          label:'My Students' },
        { href:'/pages/counsellor/sessions',     icon:'fa-video',          label:'Sessions' },
        { href:'/pages/counsellor/cases',        icon:'fa-folder-open',    label:'Cases' },
        { href:'/pages/messaging',               icon:'fa-comments',       label:'Messages' },
        { href:'/pages/notifications',           icon:'fa-bell',           label:'Notifications' },
    ],
    student: [
        { href:'/dashboard/student',           icon:'fa-tachometer-alt',       label:'Dashboard' },
        { href:'/pages/student/marks',         icon:'fa-star',                 label:'My Marks' },
        { href:'/pages/student/attendance',    icon:'fa-calendar-check',       label:'Attendance' },
        { href:'/pages/student/assignments',   icon:'fa-tasks',                label:'Assignments' },
        { href:'/pages/student/notes',         icon:'fa-sticky-note',          label:'Notes' },
        { href:'/pages/student/quiz',          icon:'fa-clipboard-list',       label:'Pulse Quiz' },
        { href:'/pages/student/risk',          icon:'fa-exclamation-triangle', label:'Risk Score' },
        { href:'/pages/student/mood',          icon:'fa-smile',                label:'Mood Check-In' },
        { href:'/pages/student/videocall',     icon:'fa-video',                label:'Video Call' },
        { href:'/pages/messaging',             icon:'fa-comments',             label:'Messages' },
        { href:'/pages/notifications',         icon:'fa-bell',                 label:'Notifications' },
    ],
};

const ROLE_LABELS = {
    admin:           'Admin',
    faculty_advisor: 'Faculty Advisor',
    subject_teacher: 'Subject Teacher',
    counsellor:      'Counsellor',
    student:         'Student',
};

function _buildNav(role) {
    const links = NAV_MAP[role];
    if (!links) return;
    const path = window.location.pathname;
    const nav  = document.getElementById('sidebar-nav');
    if (!nav)  return;
    nav.innerHTML = links.map(l => `
        <a class="nav-link${l.href === path ? ' active' : ''}" href="${l.href}">
            <i class="fas ${l.icon}"></i>${l.label}
        </a>`).join('');
}

function _populateSidebar(user) {
    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v || ''; };
    setTxt('sidebar-user-name', user.name);
    setTxt('sidebar-user-role', ROLE_LABELS[user.role] || user.role);
    setTxt('sidebar-user-id',   user.customId || '');

    const subjEl = document.getElementById('sidebar-subject-label');
    if (subjEl) {
        if (user.subject) { subjEl.textContent = user.subject; subjEl.style.display = ''; }
        else              { subjEl.style.display = 'none'; }
    }

    const av = document.getElementById('user-avatar');
    if (av) {
        const initials = (user.name || 'U').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
        av.textContent = initials;
    }
}

/* Mobile sidebar toggle */
function toggleSidebar() {
    const sidebar  = document.getElementById('sidebar');
    const overlay  = document.getElementById('sidebar-overlay');
    if (sidebar)  sidebar.classList.toggle('open');
    if (overlay)  overlay.classList.toggle('hidden');
}

/* ══════════════════════════════════════════════════════
   NOTIFICATION PANEL
   ══════════════════════════════════════════════════════ */
function toggleNotifPanel() {
    const panel = document.getElementById('notif-panel');
    if (panel) panel.classList.toggle('hidden');
}

document.addEventListener('click', e => {
    const panel = document.getElementById('notif-panel');
    if (!panel) return;
    if (!panel.contains(e.target) && !e.target.closest('#notif-bell')) {
        panel.classList.add('hidden');
    }
}, true);

async function markAllRead() {
    try {
        await apiCall('/api/notifications/read-all', 'PUT');
        const badge = document.getElementById('notif-badge');
        if (badge) badge.classList.add('hidden');
        document.querySelectorAll('.notif-item.unread').forEach(el => el.classList.remove('unread'));
    } catch (_) {}
}

function listenNotifications(uid) {
    if (typeof startNotificationListener === 'function') {
        startNotificationListener(uid);
    }
}

/* ══════════════════════════════════════════════════════
   GLOBAL LOADER
   ══════════════════════════════════════════════════════ */
function showLoader(msg) {
    const el   = document.getElementById('global-loader');
    if (!el)   return;
    const span = el.querySelector('span');
    if (span)  span.textContent = msg || 'Loading…';
    el.classList.remove('hidden');
}

function hideLoader() {
    const el = document.getElementById('global-loader');
    if (el)   el.classList.add('hidden');
}

/* ══════════════════════════════════════════════════════
   TOAST NOTIFICATIONS
   ══════════════════════════════════════════════════════ */
function showToast(message, type = 'info') {
    const isDark  = document.documentElement.getAttribute('data-theme') !== 'light';
    const bg      = isDark ? 'rgba(13,13,26,0.97)' : 'rgba(255,255,255,0.97)';
    const textClr = isDark ? '#F1F0FF' : '#1E1B4B';
    const colors  = { success:'#10B981', error:'#EF4444', warning:'#F59E0B', info:'#7B2FFF' };
    const icons   = { success:'fa-check-circle', error:'fa-times-circle', warning:'fa-exclamation-circle', info:'fa-info-circle' };
    const accent  = colors[type] || colors.info;
    const icon    = icons[type]  || icons.info;

    if (!document.getElementById('toast-kf')) {
        const s = document.createElement('style'); s.id = 'toast-kf';
        s.textContent = '@keyframes slideInToast{from{transform:translateX(110%);opacity:0}to{transform:translateX(0);opacity:1}}';
        document.head.appendChild(s);
    }

    const existing = document.querySelectorAll('.ep-toast');
    const offset   = existing.length * 68;
    const toast    = document.createElement('div');
    toast.className = 'ep-toast';
    toast.style.cssText = `position:fixed;bottom:${20+offset}px;right:20px;z-index:10000;background:${bg};color:${textClr};padding:14px 20px;border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.18);border:1px solid ${isDark?'rgba(255,255,255,0.10)':'rgba(167,139,250,0.25)'};display:flex;align-items:center;gap:10px;font-family:'Inter',sans-serif;font-size:14px;font-weight:500;max-width:340px;word-break:break-word;animation:slideInToast 0.35s cubic-bezier(0.23,1,0.32,1);backdrop-filter:blur(16px)`;
    toast.innerHTML = `<i class="fas ${icon}" style="color:${accent};font-size:16px;flex-shrink:0"></i><span>${message}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.transition = 'opacity 0.4s,transform 0.4s';
        toast.style.opacity    = '0';
        toast.style.transform  = 'translateX(110%)';
        setTimeout(() => toast.remove(), 400);
    }, 3500);
}

/* ══════════════════════════════════════════════════════
   MODAL HELPERS
   ══════════════════════════════════════════════════════ */
function openModal(id) {
    const m = document.getElementById(id);
    if (m) { m.style.display = 'flex'; document.body.style.overflow = 'hidden'; }
}
function closeModal(id) {
    const m = document.getElementById(id);
    if (m) { m.style.display = 'none'; document.body.style.overflow = ''; }
}
document.addEventListener('click', e => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
        document.body.style.overflow = '';
    }
});

/* ══════════════════════════════════════════════════════
   SOUND TOGGLE
   ══════════════════════════════════════════════════════ */
function toggleSound() {
    window._soundEnabled = !window._soundEnabled;
    const icon = document.getElementById('sound-icon');
    if (icon) icon.className = window._soundEnabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
}

/* ══════════════════════════════════════════════════════
   REPORT HELPER
   ══════════════════════════════════════════════════════ */
async function openReport(url) {
    try {
        const user = firebase.auth().currentUser;
        if (!user) { showToast('Please log in first', 'error'); return; }
        showToast('Preparing report…', 'info');
        const token = await user.getIdToken(true);
        const sep   = url.includes('?') ? '&' : '?';
        window.open(`${url}${sep}token=${encodeURIComponent(token)}`, '_blank');
    } catch (e) { showToast('Failed: ' + e.message, 'error'); }
}

/* ══════════════════════════════════════════════════════
   BOOT — runs after DOM is ready
   ══════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
    /* 1. Initialize Firebase (fetches config from Flask) */
    await initFirebase();

    /* 2. Start particle canvas if available */
    if (typeof initParticles === 'function') initParticles('particle-canvas');

    /* 3. Apply saved theme */
    if (typeof _applyTheme === 'function') {
        _applyTheme(localStorage.getItem('edupulse-theme') || 'light');
    }

    /* 4. Boot auth — populates sidebar, resolves waitForAuth() */
    _bootAuth();
});
