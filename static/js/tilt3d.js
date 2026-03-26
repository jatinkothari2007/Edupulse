/**
 * EduPulse Tilt3D — vanilla JS CSS3D tilt effect.
 */
function initTilt(selector) {
    document.querySelectorAll(selector).forEach(el => {
        if (el.dataset.tiltInit) return;
        el.dataset.tiltInit = '1';
        el.addEventListener('mousemove', e => {
            const rect    = el.getBoundingClientRect();
            const cx      = rect.left + rect.width / 2;
            const cy      = rect.top + rect.height / 2;
            const rotX    = -(e.clientY - cy) / (rect.height / 2) * 6;
            const rotY    =  (e.clientX - cx) / (rect.width  / 2) * 6;
            el.style.transform     = `perspective(1000px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale3d(1.02,1.02,1.02)`;
            el.style.transition    = 'transform 0.05s ease';
        });
        el.addEventListener('mouseleave', () => {
            el.style.transform  = 'perspective(1000px) rotateX(0) rotateY(0) scale3d(1,1,1)';
            el.style.transition = 'transform 0.5s cubic-bezier(0.23,1,0.32,1)';
        });
    });
}

// Re-init on any new elements
window.EduPulseTilt = initTilt;
