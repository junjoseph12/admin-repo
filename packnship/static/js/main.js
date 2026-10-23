// Profile Dropdown Toggle
function toggleProfileMenu(e) {
    e.stopPropagation();
    const menu = document.getElementById('profileDropdownMenu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    const wrap = document.getElementById('profileDropdownWrap');
    const menu = document.getElementById('profileDropdownMenu');
    if (wrap && menu && !wrap.contains(e.target)) {
        menu.classList.add('hidden');
    }
});

// ---------- Theme helpers ----------
function getThemeColors() {
    return window.PNSTheme ? window.PNSTheme.colors() : {};
}

function readSavedTheme() {
    try {
        return localStorage.getItem('theme');
    } catch (e) {
        return null;
    }
}

function saveTheme(theme) {
    try {
        localStorage.setItem('theme', theme);
    } catch (e) {
        /* Storage unavailable: keep the in-page theme only. */
    }
}

function applyTheme(isDark) {
    const root = document.documentElement;
    const themeToggle = document.getElementById('themeToggle');
    const themeIconSun = document.getElementById('themeIconSun');
    const themeIconMoon = document.getElementById('themeIconMoon');

    root.classList.toggle('dark-mode', isDark);

    if (themeIconSun) themeIconSun.classList.toggle('hidden', isDark);
    if (themeIconMoon) themeIconMoon.classList.toggle('hidden', !isDark);
    if (themeToggle) {
        themeToggle.setAttribute('aria-pressed', isDark ? 'true' : 'false');
        themeToggle.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    }
}

// Theme toggle functionality
function initThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    const isDark = document.documentElement.classList.contains('dark-mode') ||
        readSavedTheme() === 'dark';

    applyTheme(isDark);

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const nextIsDark = !document.documentElement.classList.contains('dark-mode');
            applyTheme(nextIsDark);
            saveTheme(nextIsDark ? 'dark' : 'light');
            document.dispatchEvent(new CustomEvent('themechange', {
                detail: getThemeColors(),
            }));
        });
    }
}

// ---------- Scroll-reveal: any element with .reveal animates in when visible ----------
document.addEventListener('DOMContentLoaded', () => {
    initThemeToggle();

    const io = new IntersectionObserver((entries) => {
        entries.forEach(e => {
            if (e.isIntersecting) {
                e.target.classList.add('is-visible');
                io.unobserve(e.target);
            }
        });
    }, { threshold: 0.1 });
    document.querySelectorAll('.reveal').forEach(el => io.observe(el));
});
