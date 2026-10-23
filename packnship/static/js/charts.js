/* Theme-aware defaults for Chart.js charts on the admin dashboard and reports. */
(function () {
    function colors() {
        if (window.PNSTheme) return window.PNSTheme.colors();
        return {
            isDark: false,
            grid: '#F3F4F6',
            text: '#9CA3AF',
            tooltipBg: '#111827',
            tooltipText: '#F9FAFB',
        };
    }

    function sync(chart) {
        const theme = colors();
        const options = chart.options || {};

        if (options.plugins && options.plugins.tooltip) {
            options.plugins.tooltip.backgroundColor = theme.tooltipBg;
            if (options.plugins.tooltip.titleColor !== undefined) {
                options.plugins.tooltip.titleColor = theme.text;
            }
        }
        if (options.plugins && options.plugins.legend && options.plugins.legend.labels) {
            options.plugins.legend.labels.color = theme.text;
        }
        Object.keys(options.scales || {}).forEach((key) => {
            const scale = options.scales[key];
            if (scale.ticks) scale.ticks.color = theme.text;
            if (scale.grid && scale.grid.color) scale.grid.color = theme.grid;
        });
        (chart.data.datasets || []).forEach((dataset) => {
            if (dataset.pointBackgroundColor) {
                dataset.pointBackgroundColor = theme.isDark ? '#1E293B' : '#ffffff';
            }
        });
        chart.update('none');
    }

    window.PNSCharts = {
        colors: colors,
        sync: sync,
        bind(chart) {
            sync(chart);
            document.addEventListener('themechange', () => sync(chart));
            return chart;
        },
    };
})();
