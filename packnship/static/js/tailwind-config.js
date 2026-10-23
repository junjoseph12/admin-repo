/* Shared Tailwind Play CDN configuration.
   Load immediately after https://cdn.tailwindcss.com on every page. */
tailwind.config = {
    darkMode: ['selector', '.dark-mode'],
    theme: {
        extend: {
            colors: {
                brand: {
                    DEFAULT: '#FF751F',
                    dark: '#E4650F',
                },
            },
        },
    },
};
