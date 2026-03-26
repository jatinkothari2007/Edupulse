/**
 * EduPulse SPA Router
 * Intercepts sidebar nav clicks and swaps .main-content without a full page reload.
 * - Fetches the target page HTML
 * - Swaps only the <main> content area
 * - Re-executes the page-specific extra_js script block
 * - Calls onPageReady(window.currentUser) directly (no new auth listeners)
 * - Updates URL via history.pushState
 * - Handles browser back/forward with popstate
 */

(function () {
    'use strict';

    let _navigating = false;

    /* ─── Main navigate function ─────────────────────────── */
    async function navigateTo(url, addToHistory) {
        if (_navigating) return;
        if (url === window.location.pathname) return; /* same page — no-op */

        _navigating = true;

        const main = document.querySelector('.main-content');

        /* Fade out current content */
        main.style.transition = 'opacity 0.12s ease';
        main.style.opacity    = '0';

        try {
            const res = await fetch(url, {
                credentials: 'same-origin',
                headers: { 'X-SPA': '1' },
            });

            /* Server redirected to /login → let it happen */
            if (res.redirected && res.url.includes('/login')) {
                window.location.href = '/login';
                return;
            }
            if (!res.ok) throw new Error('HTTP ' + res.status);

            const html = await res.text();
            const doc  = new DOMParser().parseFromString(html, 'text/html');

            /* ── 1. Swap main content ──────────────────────── */
            const newMain = doc.querySelector('.main-content');
            if (newMain) main.innerHTML = newMain.innerHTML;

            /* ── 2. Update page <title> ───────────────────── */
            document.title = doc.title;

            /* ── 3. Push browser history ──────────────────── */
            if (addToHistory !== false) {
                history.pushState({ spa: true, url }, '', url);
            }

            /* ── 4. Update active nav highlight ──────────── */
            document.querySelectorAll('.nav-link').forEach(l => {
                l.classList.toggle('active', l.getAttribute('href') === url);
            });

            /* ── 5. Re-execute page-specific script ───────── */
            /*
             * The extra_js block is the LAST inline <script> rendered inside <body>.
             * It ONLY contains page helper functions (onPageReady, renderXxx, etc.)
             * and does NOT contain requireLogin() — that lives in base.html's own
             * DOMContentLoaded block and is NOT in extra_js.
             */
            const bodyInlineScripts = Array.from(
                doc.querySelectorAll('body script:not([src])')
            );

            /*
             * Skip the large base.html script (contains showLoader, buildSidebarNav, etc.)
             * Heuristic: page scripts are SHORT and contain 'onPageReady' or 'function load'.
             * We take the last inline script that is NOT the base.html mega-block.
             */
            const pageScript = bodyInlineScripts
                .slice()       /* don't mutate */
                .reverse()
                .find(s => {
                    const t = s.textContent.trim();
                    return (
                        s.id !== 'ep-boot' &&          /* skip base.html boot block */
                        t.length > 0 &&
                        !t.includes('buildSidebarNav') &&  /* skip base.html block */
                        !t.includes('toggleSidebar')       /* skip base.html block */
                    );
                });

            if (pageScript) {
                /*
                 * CRITICAL FIX: Run page script in an isolated scope using new Function().
                 * This prevents "let X already declared" SyntaxErrors when the same page
                 * is navigated to multiple times via SPA. The page script's onPageReady
                 * is explicitly assigned to window so the router can call it below.
                 * All other page functions (renderContacts, loadContacts, etc.) are also
                 * re-assigned to window so they remain globally accessible for onclick handlers.
                 */
                try {
                    const wrappedCode = `
                        ${pageScript.textContent}
                        /* Hoist all declared functions to window for onclick handlers */
                        if (typeof onPageReady    !== 'undefined') window.onPageReady    = onPageReady;
                        if (typeof loadContacts   !== 'undefined') window.loadContacts   = loadContacts;
                        if (typeof renderContacts !== 'undefined') window.renderContacts = renderContacts;
                        if (typeof filterContacts !== 'undefined') window.filterContacts = filterContacts;
                        if (typeof selectContact  !== 'undefined') window.selectContact  = selectContact;
                        if (typeof sendMsg        !== 'undefined') window.sendMsg        = sendMsg;
                        if (typeof loadUsers      !== 'undefined') window.loadUsers      = loadUsers;
                        if (typeof filterUsers    !== 'undefined') window.filterUsers    = filterUsers;
                        if (typeof renderUsers    !== 'undefined') window.renderUsers    = renderUsers;
                        if (typeof loadNotes      !== 'undefined') window.loadNotes      = loadNotes;
                        if (typeof renderNotes    !== 'undefined') window.renderNotes    = renderNotes;
                        if (typeof broadcast      !== 'undefined') window.broadcast      = broadcast;
                        if (typeof laRefresh      !== 'undefined') window.laRefresh      = laRefresh;
                        if (typeof laLoad         !== 'undefined') window.laLoad         = laLoad;
                        if (typeof laFilter       !== 'undefined') window.laFilter       = laFilter;
                        if (typeof laRender       !== 'undefined') window.laRender       = laRender;
                        if (typeof refreshActivity!== 'undefined') window.refreshActivity= refreshActivity;
                        if (typeof openCreateModal!== 'undefined') window.openCreateModal= openCreateModal;
                        if (typeof closeCreateModal !== 'undefined') window.closeCreateModal = closeCreateModal;
                        if (typeof deactivate     !== 'undefined') window.deactivate     = deactivate;
                        if (typeof reactivate     !== 'undefined') window.reactivate     = reactivate;
                        if (typeof resetPwd       !== 'undefined') window.resetPwd       = resetPwd;
                        if (typeof createUser     !== 'undefined') window.createUser     = createUser;
                        if (typeof recalcAll      !== 'undefined') window.recalcAll      = recalcAll;
                    `;
                    // new Function runs in global this but with its OWN variable scope
                    // so let/const don't pollute or clash with window scope
                    new Function(wrappedCode)();
                } catch (scriptErr) {
                    console.warn('[Router] page script error:', scriptErr);
                }
            }

            /* ── 6. Trigger page init ─────────────────────── */
            /* Yield one tick so the newly appended script has run */
            await new Promise(r => setTimeout(r, 0));

            if (window.currentUser && typeof onPageReady === 'function') {
                try { await onPageReady(window.currentUser); } catch (e) {
                    console.warn('[Router] onPageReady error:', e);
                }
            }

            /* ── 7. Re-init 3D tilt on new cards ─────────── */
            if (typeof window.reinitTilt === 'function') window.reinitTilt();

            /* Fade in */
            main.style.opacity = '1';

        } catch (err) {
            console.warn('[EduPulse Router] SPA navigation failed, falling back:', err);
            window.location.href = url;   /* hard navigate as fallback */
        } finally {
            _navigating = false;
        }
    }

    /* ─── Intercept sidebar nav clicks ───────────────────── */
    document.addEventListener('click', function (e) {
        const link = e.target.closest('a.nav-link');
        if (!link) return;

        const href = link.getAttribute('href');
        if (!href || href === '#' || href.startsWith('http') || href.startsWith('//')) return;

        e.preventDefault();
        navigateTo(href);
    });

    /* ─── Handle browser back / forward ──────────────────── */
    window.addEventListener('popstate', function (e) {
        if (e.state && e.state.spa) {
            navigateTo(window.location.pathname, false /* don't push again */);
        }
    });

    /* Expose for programmatic use (e.g. redirect after modal submit) */
    window.spaNavigate = navigateTo;

})();
