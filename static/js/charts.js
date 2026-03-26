/**
 * EduPulse Charts — Chart.js global defaults + chart wrappers
 */

/* ── Global Chart.js defaults ──────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
    if (!window.Chart) return;

    Chart.defaults.responsive             = true;
    Chart.defaults.maintainAspectRatio   = true;

    const _getVar = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

    Chart.defaults.color       = _getVar('--text-secondary') || 'rgba(30,27,75,0.65)';
    Chart.defaults.borderColor = _getVar('--divider')         || 'rgba(167,139,250,0.15)';

    Chart.defaults.plugins.legend.labels.font        = { size: 12 };
    Chart.defaults.plugins.tooltip.backgroundColor   = _getVar('--modal-bg')        || 'rgba(255,255,255,0.95)';
    Chart.defaults.plugins.tooltip.titleColor        = _getVar('--text-primary')    || '#1E1B4B';
    Chart.defaults.plugins.tooltip.bodyColor         = _getVar('--text-secondary')  || 'rgba(30,27,75,0.65)';
    Chart.defaults.plugins.tooltip.cornerRadius      = 10;
    Chart.defaults.plugins.tooltip.padding           = 12;
    Chart.defaults.plugins.tooltip.borderWidth       = 1;
    Chart.defaults.plugins.tooltip.borderColor       = _getVar('--glass-border')    || 'rgba(167,139,250,0.20)';
});

function updateChartThemes(theme) {
    if (!window.Chart) return;
    const isDark    = theme === 'dark';
    const textColor = isDark ? 'rgba(241,240,255,0.70)' : 'rgba(30,27,75,0.65)';
    const gridColor = isDark ? 'rgba(255,255,255,0.07)' : 'rgba(167,139,250,0.13)';

    Chart.defaults.color       = textColor;
    Chart.defaults.borderColor = gridColor;

    Object.values(Chart.instances || {}).forEach(chart => {
        if (!chart) return;
        if (chart.options.scales) {
            Object.values(chart.options.scales).forEach(scale => {
                if (scale.ticks) scale.ticks.color = textColor;
                if (scale.grid)  scale.grid.color  = gridColor;
            });
        }
        if (chart.options.plugins?.legend?.labels) {
            chart.options.plugins.legend.labels.color = textColor;
        }
        chart.update('none');
    });
}

const _CHART_INSTANCES = {};

function _destroyChart(id) {
    if (_CHART_INSTANCES[id]) {
        _CHART_INSTANCES[id].destroy();
        delete _CHART_INSTANCES[id];
    }
}

function _isDark() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
}

function _baseFont() {
    return { family: "'Inter', sans-serif", size: 12, color: _isDark() ? '#A9A6C6' : '#7B7591' };
}

function _gridColor() { return _isDark() ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'; }

function renderBarChart(canvasId, labels, data, label='Value', color='#7B2FFF', extraOpts={}) {
    _destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    _CHART_INSTANCES[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label,
                data,
                backgroundColor: labels.map(() => color + '99'),
                borderColor: color,
                borderWidth: 2,
                borderRadius: 8,
                borderSkipped: false,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: _gridColor() }, ticks: { font: _baseFont(), color: _isDark()?'#A9A6C6':'#7B7591' } },
                y: { beginAtZero: true, grid: { color: _gridColor() }, ticks: { font: _baseFont(), color: _isDark()?'#A9A6C6':'#7B7591' } }
            },
            ...extraOpts
        }
    });
}

function renderLineChart(canvasId, labels, data, label='Value', color='#7B2FFF', extraOpts={}) {
    _destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, color + '40');
    gradient.addColorStop(1, color + '00');
    _CHART_INSTANCES[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label,
                data,
                borderColor: color,
                backgroundColor: gradient,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: color,
                pointRadius: 4,
                pointHoverRadius: 6,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: _gridColor() }, ticks: { font: _baseFont(), color: _isDark()?'#A9A6C6':'#7B7591' } },
                y: { grid: { color: _gridColor() }, ticks: { font: _baseFont(), color: _isDark()?'#A9A6C6':'#7B7591' } }
            },
            ...extraOpts
        }
    });
}

function renderDoughnutChart(canvasId, labels, data, colors=['#7B2FFF','#F59E0B','#EF4444','#10B981','#3B82F6']) {
    _destroyChart(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    _CHART_INSTANCES[canvasId] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors.map((c, i) => c + (i === 0 ? 'cc' : 'aa')),
                borderColor: colors,
                borderWidth: 2,
                hoverOffset: 8,
            }]
        },
        options: {
            responsive: true,
            cutout: '68%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { font: _baseFont(), color: _isDark()?'#A9A6C6':'#7B7591', boxWidth: 12, padding: 16 }
                }
            }
        }
    });
}
