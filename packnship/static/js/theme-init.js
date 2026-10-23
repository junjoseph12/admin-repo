/* Apply the saved theme before first paint to avoid a light-mode flash.
   Also exposes the shared theme helper used by page scripts and charts.
   Loaded synchronously in <head> on every page. */
(function () {
    try {
        if (localStorage.getItem('theme') === 'dark') {
            document.documentElement.classList.add('dark-mode');
        }
    } catch (e) {
        /* Storage unavailable (privacy mode / sandboxed iframe): stay light. */
    }

    function colors() {
        const styles = getComputedStyle(document.documentElement);
        const value = (name) => styles.getPropertyValue(name).trim();
        return {
            isDark: document.documentElement.classList.contains('dark-mode'),
            grid: value('--chart-grid'),
            text: value('--chart-text'),
            tooltipBg: value('--chart-tooltip-bg'),
            tooltipText: value('--chart-tooltip-text'),
        };
    }

    window.PNSTheme = {
        isDark: () => document.documentElement.classList.contains('dark-mode'),
        colors: colors,
    };
})();
