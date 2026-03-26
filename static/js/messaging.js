/**
 * EduPulse Messaging JS (shared helper) — AES helpers and conversation starters.
 * The main messaging UI logic is in messaging.html.
 */
const MSG_KEY = 'EduPulse2026SecureKey';

function encryptMessage(text) {
    return CryptoJS.AES.encrypt(text, MSG_KEY).toString();
}

function decryptMessage(cipher) {
    try {
        const bytes = CryptoJS.AES.decrypt(cipher, MSG_KEY);
        return bytes.toString(CryptoJS.enc.Utf8) || '[encrypted]';
    } catch (_) { return '[encrypted]'; }
}
