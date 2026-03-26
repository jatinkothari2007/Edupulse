/**
 * EduPulse Weekly Engagement Heatmap
 * Renders a 7×24 (day × hour) grid using canvas/div.
 */
async function renderHeatmap(containerId, grid) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const DAYS  = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const HOURS = ['12am','2am','4am','6am','8am','10am','12pm','2pm','4pm','6pm','8pm','10pm'];

    // Find max for scaling
    let maxVal = 1;
    for (let d = 0; d < 7; d++)
        for (let h = 0; h < 24; h++)
            if ((grid[d]||[])[h] > maxVal) maxVal = grid[d][h];

    const cellSize = 20;
    const gap      = 2;
    const labelW   = 36;
    const labelH   = 20;

    container.style.overflowX = 'auto';
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.style.cssText = `display:inline-block;font-family:'Inter',sans-serif;font-size:11px`;

    // Hour labels (top)
    const hourRow = document.createElement('div');
    hourRow.style.cssText = `display:flex;margin-left:${labelW}px;margin-bottom:4px`;
    HOURS.forEach((h, idx) => {
        const lbl = document.createElement('div');
        lbl.style.cssText = `width:${(cellSize+gap)*2}px;text-align:center;color:var(--text-muted);font-size:10px`;
        lbl.textContent = h;
        hourRow.appendChild(lbl);
    });
    wrap.appendChild(hourRow);

    // Grid rows
    for (let d = 0; d < 7; d++) {
        const row = document.createElement('div');
        row.style.cssText = `display:flex;align-items:center;margin-bottom:${gap}px`;

        const dayLbl = document.createElement('div');
        dayLbl.style.cssText = `width:${labelW}px;color:var(--text-secondary);font-size:11px;font-weight:600`;
        dayLbl.textContent = DAYS[d];
        row.appendChild(dayLbl);

        for (let h = 0; h < 24; h++) {
            const val      = (grid[d]||[])[h] || 0;
            const ratio    = val / maxVal;
            const cell     = document.createElement('div');
            const opacity  = val === 0 ? 0.06 : 0.15 + ratio * 0.75;
            cell.style.cssText = `width:${cellSize}px;height:${cellSize}px;border-radius:4px;margin-right:${gap}px;cursor:pointer;transition:transform 0.1s;background:rgba(123,47,255,${opacity.toFixed(2)});`;
            cell.title = `${DAYS[d]} ${h}:00 — ${val} activit${val===1?'y':'ies'}`;
            cell.addEventListener('mouseenter', () => cell.style.transform = 'scale(1.3)');
            cell.addEventListener('mouseleave', () => cell.style.transform = 'scale(1)');
            row.appendChild(cell);
        }
        wrap.appendChild(row);
    }

    // Legend
    const legend = document.createElement('div');
    legend.style.cssText = `display:flex;align-items:center;gap:8px;margin-top:12px;margin-left:${labelW}px`;
    legend.innerHTML = `<span style="color:var(--text-muted);font-size:11px">Less</span>`;
    [0.06, 0.25, 0.50, 0.75, 0.95].forEach(op => {
        const box = document.createElement('div');
        box.style.cssText = `width:14px;height:14px;border-radius:3px;background:rgba(123,47,255,${op})`;
        legend.appendChild(box);
    });
    legend.innerHTML += `<span style="color:var(--text-muted);font-size:11px">More</span>`;
    wrap.appendChild(legend);

    container.appendChild(wrap);
}

async function loadAndRenderHeatmap(containerId) {
    try {
        const data = await apiCall('/api/student/engagement/heatmap');
        renderHeatmap(containerId, data.grid || []);
    } catch(e) {
        const el = document.getElementById(containerId);
        if (el) el.innerHTML = '<p style="color:var(--text-muted);font-size:13px">No activity data yet.</p>';
    }
}
