/**
 * EduPulse Risk Display — Animated speedometer gauge
 * Needle sweeps from 0 → score, arc fills, counter ticks up.
 * Score + label displayed BELOW the gauge.
 */

function renderRiskGauge(containerId, score, level) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const colors     = { LOW: '#10B981', MEDIUM: '#F59E0B', HIGH: '#EF4444' };
    const color      = colors[level] || '#94A3B8';
    const qualLabels = { LOW: '✅ Low Risk', MEDIUM: '⚠️ Medium Risk', HIGH: '🚨 High Risk' };
    const arcLen     = Math.PI * 90;   // half-circle circumference

    // Unique IDs per container to allow multiple gauges on one page
    const gradId     = `gauge-grad-${containerId}`;
    const needleId   = `gauge-needle-${containerId}`;
    const arcFillId  = `gauge-arc-fill-${containerId}`;
    const scoreNumId = `gauge-score-${containerId}`;

    container.innerHTML = `
        <div style="width:240px;margin:0 auto;text-align:center">
            <svg viewBox="0 0 220 130" width="220" height="130" style="overflow:visible">
                <defs>
                    <linearGradient id="${gradId}" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%"   stop-color="#10B981"/>
                        <stop offset="50%"  stop-color="#F59E0B"/>
                        <stop offset="100%" stop-color="#EF4444"/>
                    </linearGradient>
                    <filter id="gauge-glow-${containerId}">
                        <feGaussianBlur stdDeviation="3" result="blur"/>
                        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                    </filter>
                </defs>

                <!-- Track arc (background) -->
                <path d="M 20 110 A 90 90 0 0 1 200 110"
                      stroke="rgba(148,163,184,0.15)" stroke-width="14" fill="none" stroke-linecap="round"/>

                <!-- Tick marks -->
                ${[0,25,50,75,100].map(v => {
                    const a = (v / 100) * Math.PI;
                    const r1 = 97, r2 = 105;
                    return `<line
                        x1="${110 - r1 * Math.cos(a)}" y1="${110 - r1 * Math.sin(a)}"
                        x2="${110 - r2 * Math.cos(a)}" y2="${110 - r2 * Math.sin(a)}"
                        stroke="rgba(148,163,184,0.4)" stroke-width="1.5"/>`;
                }).join('')}

                <!-- Colored fill arc (animated via dasharray) -->
                <path id="${arcFillId}"
                      d="M 20 110 A 90 90 0 0 1 200 110"
                      stroke="url(#${gradId})" stroke-width="12" fill="none" stroke-linecap="round"
                      stroke-dasharray="0 ${arcLen}"
                      style="filter:url(#gauge-glow-${containerId});transition:none"/>

                <!-- Needle (rotated via transform) -->
                <g id="${needleId}" style="transform-origin:110px 110px;transform:rotate(-180deg)">
                    <line x1="110" y1="110" x2="110" y2="36"
                          stroke="${color}" stroke-width="2.5" stroke-linecap="round"
                          style="filter:url(#gauge-glow-${containerId})"/>
                </g>

                <!-- Center hub -->
                <circle cx="110" cy="110" r="8" fill="${color}" style="filter:url(#gauge-glow-${containerId})"/>
                <circle cx="110" cy="110" r="4" fill="var(--card-bg,#1a1a2e)"/>

                <!-- LOW / MED / HIGH labels -->
                <text x="16"  y="128" font-size="9" fill="#10B981" font-family="Inter,sans-serif" font-weight="600">LOW</text>
                <text x="110" y="128" text-anchor="middle" font-size="9" fill="#F59E0B" font-family="Inter,sans-serif" font-weight="600">MED</text>
                <text x="204" y="128" text-anchor="end" font-size="9" fill="#EF4444" font-family="Inter,sans-serif" font-weight="600">HIGH</text>
            </svg>

            <!-- Score + label BELOW the gauge -->
            <div style="margin-top:6px">
                <div id="${scoreNumId}" style="font-size:40px;font-weight:900;color:${color};
                     font-family:'Space Grotesk',sans-serif;line-height:1;
                     text-shadow:0 0 20px ${color}40;transition:color 0.5s">0</div>
                <div style="font-size:14px;font-weight:700;color:${color};margin-top:4px;
                     letter-spacing:0.5px">${qualLabels[level] || level}</div>
            </div>
        </div>`;

    // ── Animation ─────────────────────────────────────────────────────────
    const needle   = document.getElementById(needleId);
    const arcFill  = document.getElementById(arcFillId);
    const scoreEl  = document.getElementById(scoreNumId);

    const DURATION  = 1400;   // ms
    const EASE      = t => t < 0.5 ? 2*t*t : -1+(4-2*t)*t;  // ease-in-out
    let   startTime = null;

    function frame(ts) {
        if (!startTime) startTime = ts;
        const elapsed = ts - startTime;
        const rawT    = Math.min(elapsed / DURATION, 1);
        const t       = EASE(rawT);
        const cur     = score * t;

        // Rotate needle: -180deg (0) → 0deg (100)
        const deg = -180 + (cur / 100) * 180;
        needle.style.transform = `rotate(${deg}deg)`;

        // Fill arc
        const filled = (cur / 100) * arcLen;
        arcFill.setAttribute('stroke-dasharray', `${filled} ${arcLen}`);

        // Count up score number
        scoreEl.textContent = cur.toFixed(cur >= 10 ? 1 : 1);

        if (rawT < 1) {
            requestAnimationFrame(frame);
        } else {
            scoreEl.textContent = score;
        }
    }

    // Small delay so DOM is fully painted before animation starts
    setTimeout(() => requestAnimationFrame(frame), 80);
}
