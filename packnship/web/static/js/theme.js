/* =========================================================
   Pack-N-Ship — Theme manager
   - Applies saved theme or system preference on load
   - Toggles via data-theme on <html>
   - Persists to localStorage
   - Emits `themechange` event for other scripts
   ========================================================= */
(function () {
    'use strict';

    const STORAGE_KEY = 'pns-theme';
    const root = document.documentElement;

    function getStored() {
        try { return localStorage.getItem(STORAGE_KEY); }
        catch (e) { return null; }
    }
    function setStored(value) {
        try { localStorage.setItem(STORAGE_KEY, value); } catch (e) {}
    }
    function systemPrefersDark() {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    function applyTheme(theme, animate) {
        if (animate) {
            root.classList.add('theme-transition');
            window.setTimeout(() => root.classList.remove('theme-transition'), 250);
        }
        root.setAttribute('data-theme', theme);
        updateToggleUI(theme);
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
    }

    function updateToggleUI(theme) {
        const btn = document.getElementById('themeToggle');
        if (!btn) return;
        const isDark = theme === 'dark';
        btn.setAttribute('aria-pressed', String(isDark));
        btn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
        btn.setAttribute('title',      isDark ? 'Switch to light mode' : 'Switch to dark mode');
    }

    function resolveInitialTheme() {
        const stored = getStored();
        if (stored === 'light' || stored === 'dark') return stored;
        return systemPrefersDark() ? 'dark' : 'light';
    }

    // Apply ASAP to avoid flash of wrong theme
    applyTheme(resolveInitialTheme(), false);

    // Wire toggle when DOM is ready
    document.addEventListener('DOMContentLoaded', function () {
        const btn = document.getElementById('themeToggle');
        if (btn) {
            updateToggleUI(root.getAttribute('data-theme') || 'light');
            btn.addEventListener('click', function () {
                const current = root.getAttribute('data-theme') || 'light';
                const next = current === 'dark' ? 'light' : 'dark';
                setStored(next);
                applyTheme(next, true);
            });
        }

        // If the user has never explicitly chosen, follow system changes live.
        if (window.matchMedia) {
            const mq = window.matchMedia('(prefers-color-scheme: dark)');
            const onChange = function (e) {
                if (getStored()) return;
                applyTheme(e.matches ? 'dark' : 'light', true);
            };
            if (mq.addEventListener) mq.addEventListener('change', onChange);
            else if (mq.addListener) mq.addListener(onChange);
        }
    });
})();