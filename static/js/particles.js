/**
 * EduPulse Particles — canvas-based subtle floating dots.
 */
function initParticles(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx     = canvas.getContext('2d');
    let W, H, particles;
    const COUNT   = 60;

    function resize() {
        W = canvas.width  = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }

    function createParticle() {
        return {
            x:   Math.random() * W,
            y:   Math.random() * H,
            vx:  (Math.random() - 0.5) * 0.4,
            vy:  (Math.random() - 0.5) * 0.4,
            r:   1.5 + Math.random() * 2.5,
            a:   0.12 + Math.random() * 0.25,
        };
    }

    function init() {
        resize();
        particles = Array.from({ length: COUNT }, createParticle);
    }

    function loop() {
        ctx.clearRect(0, 0, W, H);
        const isDark = document.documentElement.classList.contains('dark');
        const clr    = isDark ? '167,139,250' : '123,47,255';

        particles.forEach(p => {
            p.x += p.vx; p.y += p.vy;
            if (p.x < 0 || p.x > W) p.vx *= -1;
            if (p.y < 0 || p.y > H) p.vy *= -1;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${clr},${p.a})`;
            ctx.fill();
        });

        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const d  = Math.sqrt(dx * dx + dy * dy);
                if (d < 140) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(${clr},${(1 - d / 140) * 0.10})`;
                    ctx.lineWidth   = 0.8;
                    ctx.stroke();
                }
            }
        }

        requestAnimationFrame(loop);
    }

    init();
    loop();
    window.addEventListener('resize', init);
}
