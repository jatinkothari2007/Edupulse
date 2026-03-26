/**
 * EduPulse Notifications — real-time Firestore listener, bell shake, panel.
 */
let _notifUnsubscribe = null;
let _knownNotifIds   = new Set();

function startNotificationListener(uid) {
    if (_notifUnsubscribe) _notifUnsubscribe();
    _notifUnsubscribe = window.db
        .collection('notifications')
        .doc(uid)
        .collection('items')
        .orderBy('createdAt', 'desc')
        .limit(50)
        .onSnapshot(snapshot => {
            const notifs  = [];
            const newOnes = [];
            snapshot.forEach(doc => {
                const n = { id: doc.id, ...doc.data() };
                notifs.push(n);
                if (!n.isRead && !_knownNotifIds.has(n.id) && _knownNotifIds.size > 0) {
                    newOnes.push(n);
                }
                _knownNotifIds.add(n.id);
            });

            /* Update badge */
            const badge  = document.getElementById('notif-badge');
            const unread = notifs.filter(n => !n.isRead).length;
            if (badge) {
                if (unread > 0) {
                    badge.textContent  = unread > 9 ? '9+' : unread;
                    badge.style.display = 'flex';
                    badge.style.cssText += ';display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:white;background:#EF4444;border-radius:50%;min-width:18px;height:18px;padding:0 4px;position:absolute;top:2px;right:2px;';
                } else {
                    badge.style.display = 'none';
                }
            }

            /* Render list */
            const list = document.getElementById('notif-list');
            if (list) {
                if (!notifs.length) {
                    list.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-muted);font-size:13px"><i class="fas fa-check-circle" style="font-size:24px;display:block;margin-bottom:8px"></i>You\'re all caught up! 🎉</div>';
                } else {
                    const priorityColors = { critical:'#EF4444', high:'#F59E0B', medium:'#7B2FFF', low:'#94A3B8' };
                    list.innerHTML = notifs.map(n => `
                        <div class="notif-item ${n.isRead?'':'unread'}"
                             onclick="readNotif('${n.id}', this)"
                             style="border-left:3px solid ${priorityColors[n.priority]||'#7B2FFF'}">
                            <div class="notif-title">${n.title||'Notification'}</div>
                            <div class="notif-msg">${n.message||''}</div>
                            <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
                                ${n.createdAt ? _timeAgo(n.createdAt) : ''}
                            </div>
                        </div>`).join('');
                }
            }

            /* New notifications */
            newOnes.forEach(n => {
                _ringBell();
                _showNotifToast(n.title||'Notification', n.message||'');
                if (n.sound && typeof safePlaySound === 'function') {
                    safePlaySound(n.priority || 'medium');
                }
            });
        }, err => console.warn('[EduPulse] notif listener:', err.message));
}

function _timeAgo(ts) {
    try {
        const date = ts.toDate ? ts.toDate() : new Date(ts);
        const diff = (Date.now() - date.getTime()) / 1000;
        if (diff < 60)  return 'just now';
        if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
        return `${Math.floor(diff/86400)}d ago`;
    } catch(e) { return ''; }
}

function _ringBell() {
    if (!document.getElementById('bell-shake-kf')) {
        const s = document.createElement('style');
        s.id = 'bell-shake-kf';
        s.textContent = `@keyframes bellRing{0%,100%{transform:rotate(0)}10%,50%,90%{transform:rotate(-15deg)}20%,40%,60%,80%{transform:rotate(15deg)}} .bell-ringing{animation:bellRing 0.6s ease 2}`;
        document.head.appendChild(s);
    }
    const btn = document.getElementById('notif-bell');
    if (btn) {
        btn.classList.remove('bell-ringing');
        void btn.offsetWidth;
        btn.classList.add('bell-ringing');
        setTimeout(() => btn.classList.remove('bell-ringing'), 1300);
    }
}

function _showNotifToast(title, msg) {
    const isDark = document.documentElement.className.includes('dark');
    const bg     = isDark ? 'rgba(13,13,26,0.97)' : 'rgba(255,255,255,0.97)';
    const text   = isDark ? '#F1F0FF' : '#1E1B4B';
    const toast  = document.createElement('div');
    toast.style.cssText = `position:fixed;bottom:24px;right:24px;z-index:10001;background:${bg};color:${text};padding:16px 20px;border-radius:16px;box-shadow:0 8px 32px rgba(123,47,255,0.22);border:1px solid rgba(123,47,255,0.30);display:flex;align-items:flex-start;gap:12px;min-width:280px;max-width:360px;font-family:'Inter',sans-serif;animation:slideInToast 0.35s cubic-bezier(0.23,1,0.32,1);backdrop-filter:blur(20px)`;
    toast.innerHTML = `<div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#7B2FFF,#A78BFA);display:flex;align-items:center;justify-content:center;flex-shrink:0"><i class="fas fa-bell" style="color:#fff;font-size:15px"></i></div><div style="flex:1;min-width:0"><div style="font-weight:700;font-size:13px;margin-bottom:4px">${title}</div><div style="font-size:12px;color:var(--text-muted,#888);line-height:1.4">${msg}</div></div><button onclick="this.parentElement.remove()" style="background:none;border:none;color:var(--text-muted,#888);cursor:pointer;font-size:18px;line-height:1;padding:0;flex-shrink:0">×</button>`;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.transition='opacity 0.4s,transform 0.4s'; toast.style.opacity='0'; toast.style.transform='translateX(110%)'; setTimeout(() => toast.remove(), 400); }, 5000);
}
