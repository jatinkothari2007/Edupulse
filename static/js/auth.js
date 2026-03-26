/**
 * EduPulse auth.js — thin compatibility shim.
 * The unified auth system now lives in cache.js (_bootAuth / waitForAuth).
 * This file preserves the requireLogin() API used by older page scripts,
 * and the signOut() convenience function.
 */

/**
 * requireLogin() — redirect to '/' if no authenticated user.
 * Used by page scripts that don't rely on waitForAuth().
 * SAFE to call multiple times; waits for the auth promise to resolve.
 */
function requireLogin() {
    waitForAuth().then(user => {
        if (!user) window.location.href = '/';
    });
}

/**
 * signOut() — signs out and redirects.
 */
async function signOut() {
    try {
        await firebase.auth().signOut();
        window.location.href = '/';
    } catch (e) {
        showToast('Logout failed: ' + e.message, 'error');
    }
}
