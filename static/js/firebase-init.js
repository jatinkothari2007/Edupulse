/**
 * EduPulse firebase-init.js
 * - Fetches config from Flask and initializes Firebase client SDK once
 * - Provides apiCall() with proper token — waits for auth state to be known
 * - Provides waitForCurrentUser() — resolves when Firebase auth state is known
 */

let _firebaseInitPromise = null;

/* Resolves to the Firebase user (or null) once onAuthStateChanged fires */
let _authStatePromise = null;
let _authStateResolve = null;
_authStatePromise = new Promise(resolve => { _authStateResolve = resolve; });

async function initFirebase() {
    if (_firebaseInitPromise) return _firebaseInitPromise;

    _firebaseInitPromise = (async () => {
        try {
            /* Already initialised on a hot reload */
            if (firebase.apps && firebase.apps.length > 0) {
                window.db   = window.db   || firebase.firestore();
                window.auth = window.auth || firebase.auth();
            } else {
                const res = await fetch('/firebase-config');
                if (!res.ok) throw new Error('Failed to fetch /firebase-config: ' + res.status);
                const cfg = await res.json();

                if (!cfg.apiKey) throw new Error('Firebase config missing apiKey — check .env');

                firebase.initializeApp(cfg);
                window.db   = firebase.firestore();
                window.auth = firebase.auth();
            }

            /* Firestore settings — avoid "long-polling" warnings */
            window.db.settings({ ignoreUndefinedProperties: true });

            /* Wire up the single auth state listener.
               This resolves _authStatePromise exactly once. */
            window.auth.onAuthStateChanged(user => {
                if (_authStateResolve) {
                    _authStateResolve(user); /* resolve on FIRST call */
                    _authStateResolve = null; /* prevent double-resolve */
                }
            });

        } catch (err) {
            console.error('[EduPulse] Firebase init failed:', err);
            /* Resolve with null so callers don't hang forever */
            if (_authStateResolve) {
                _authStateResolve(null);
                _authStateResolve = null;
            }
        }
    })();

    return _firebaseInitPromise;
}

/**
 * Returns a Promise<FirebaseUser|null> that resolves once the Firebase auth
 * state is actually known (i.e. after onAuthStateChanged fires at least once).
 * Safe to call before or after initFirebase().
 */
async function waitForCurrentUser() {
    await initFirebase();
    return _authStatePromise;
}

/**
 * Universal API call — waits for auth state, attaches Bearer token.
 * @param {string} url
 * @param {string} [method='GET']
 * @param {*}      [body=null]
 * @returns {Promise<any>} parsed JSON response
 */
async function apiCall(url, method = 'GET', body = null) {
    /* Always wait for Firebase to be initialised */
    await initFirebase();

    const user = window.auth ? window.auth.currentUser : null;
    if (!user) {
        /* Try waiting for the first auth event */
        const resolved = await _authStatePromise;
        if (!resolved) throw new Error('Not authenticated — please log in');
    }

    const currentUser = window.auth.currentUser;
    if (!currentUser) throw new Error('Not authenticated — please log in');

    const token = await currentUser.getIdToken(false);

    const opts = {
        method,
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type':  'application/json',
        },
    };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(url, opts);
    if (!res.ok) {
        let errMsg;
        try   { errMsg = (await res.json()).error || res.statusText; }
        catch { errMsg = res.statusText; }
        throw new Error(errMsg);
    }
    return res.json();
}
