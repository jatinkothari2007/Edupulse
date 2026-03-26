/**
 * EduPulse Theme — light/dark toggle.
 * Uses data-theme attribute on <html> for CSS variable scoping.
 * MUST load in <head> (inline in base.html) to prevent FOUC.
 */

function _applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('edupulse-theme', theme);
    const isDark = theme === 'dark';

    const icon  = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');
    if (icon)  icon.className   = isDark ? 'fas fa-sun' : 'fas fa-moon';
    if (label) label.textContent = isDark ? 'Light' : 'Dark';

    // Update Chart.js colors if available
    if (typeof updateChartThemes === 'function') updateChartThemes(theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    _applyTheme(current === 'dark' ? 'light' : 'dark');
}

// Sync button state on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    const t = localStorage.getItem('edupulse-theme') || 'light';
    _applyTheme(t);
});
