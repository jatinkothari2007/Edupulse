/**
 * EduPulse Notification Sound — Web Audio API (no external audio files)
 */
const _AudioCtx = window.AudioContext || window.webkitAudioContext;
let _audioCtx   = null;

function _getAudioCtx() {
    if (!_audioCtx) _audioCtx = new _AudioCtx();
    return _audioCtx;
}

function playNotificationSound(type) {
    try {
        const ctx = _getAudioCtx();
        const sounds = {
            low: () => {
                const osc = ctx.createOscillator(), gain = ctx.createGain();
                osc.connect(gain); gain.connect(ctx.destination);
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + 0.3);
                gain.gain.setValueAtTime(0.3, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
                osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.4);
            },
            medium: () => {
                [0, 0.25].forEach((delay, i) => {
                    const osc = ctx.createOscillator(), gain = ctx.createGain();
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.frequency.setValueAtTime(i === 0 ? 880 : 1100, ctx.currentTime + delay);
                    gain.gain.setValueAtTime(0.3, ctx.currentTime + delay);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.3);
                    osc.start(ctx.currentTime + delay); osc.stop(ctx.currentTime + delay + 0.3);
                });
            },
            high: () => {
                [0, 0.2, 0.4].forEach(delay => {
                    const osc = ctx.createOscillator(), gain = ctx.createGain();
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.frequency.setValueAtTime(1200, ctx.currentTime + delay);
                    osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + delay + 0.25);
                    gain.gain.setValueAtTime(0.4, ctx.currentTime + delay);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.3);
                    osc.start(ctx.currentTime + delay); osc.stop(ctx.currentTime + delay + 0.3);
                });
            },
            critical: () => {
                [0, 0.15, 0.30, 0.45].forEach(delay => {
                    const osc = ctx.createOscillator(), gain = ctx.createGain();
                    osc.type = 'square';
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.frequency.setValueAtTime(440, ctx.currentTime + delay);
                    gain.gain.setValueAtTime(0.15, ctx.currentTime + delay);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + 0.12);
                    osc.start(ctx.currentTime + delay); osc.stop(ctx.currentTime + delay + 0.12);
                });
            },
        };
        if (sounds[type]) sounds[type]();
    } catch(e) { /* Audio not available */ }
}

function isSoundEnabled() {
    return localStorage.getItem('edupulse-sound') !== 'false';
}

function toggleSound() {
    const current = isSoundEnabled();
    localStorage.setItem('edupulse-sound', !current);
    _updateSoundBtn(!current);
}

function _updateSoundBtn(enabled) {
    const icon = document.getElementById('sound-icon');
    if (!icon) return;
    icon.className = enabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
    const btn = document.getElementById('sound-toggle-btn');
    if (btn) btn.title = enabled ? 'Sound On' : 'Sound Off';
}

function safePlaySound(priority) {
    if (isSoundEnabled()) {
        // Resume ctx if suspended (required by browser policy)
        if (_audioCtx && _audioCtx.state === 'suspended') _audioCtx.resume();
        playNotificationSound(priority);
    }
}

// Init sound btn state on load
document.addEventListener('DOMContentLoaded', () => _updateSoundBtn(isSoundEnabled()));
