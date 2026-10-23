# UI Revision Plan

Last updated: 2026-10-24

## Design System Rules

### Static Assets

- Global styles live in `static/css/global.css`.
- Global interactions live in `static/js/main.js`.
- Templates must load shared assets with `{% load static %}` and the `{% static %}` tag.
- Do not add inline `<style>` or `<script>` blocks for shared/reusable behavior.
- Page-specific scripts (charts, modals, filters) may remain page-specific, but must not duplicate global handlers.

### Colors

**Brand**

| Token | Value | Usage |
| --- | --- | --- |
| Brand primary | `#FF751F` | Primary actions, active states, key metrics |
| Brand dark | `#E4650F` | Hover states, gradient midpoint |
| Brand deep | `#C9540A` | Gradient end, pressed states |
| Brand muted text | `#D47A4A` | Text on soft brand backgrounds |
| Brand soft background | `#FFEEDD` | Brand badges, highlights |

**Neutrals**

| Token | Value / Tailwind | Usage |
| --- | --- | --- |
| App background | `#F4F5F7` / `#F8F9FA` | Page and content backgrounds |
| Surface | `#FFFFFF` | Cards, panels, inputs |
| Border | `gray-100` / `gray-200` | Card and input borders |
| Muted text | `gray-400` / `gray-500` | Labels, helper text |
| Secondary text | `gray-600` / `gray-700` | Body copy |
| Primary text | `gray-900` | Headings, values |
| Dark surface | `#0F172A` | Tooltips, overlays |

**Semantic**

- Success: `green-50` background, `green-100` border, `green-600` text.
- Danger: `red-50` background, `red-100` border, `red-600` / `red-700` text.
- Warning: amber tones.
- Category accents (indigo, amber, orange, rose) are allowed for stat cards only; keep them restrained.
- Do not introduce new colors without adding them to this system.

### Typography

- Base font: Tailwind `font-sans`.
- Page title: `text-3xl` / `md:text-4xl font-black tracking-tight`.
- Section title: `text-lg font-black tracking-tight text-gray-900`.
- Stat label: `text-[11px] font-black uppercase tracking-widest text-gray-400`.
- Body copy: `text-sm font-medium text-gray-600` / `text-gray-700`.
- Metric value: `text-4xl font-black tracking-tighter tabular-nums`.
- Badges: `text-[10px]` / `text-[11px] font-black uppercase tracking-wide` / `tracking-wider`.
- Keep helper text at `text-xs` or `text-[11px]`.

### Spacing and Layout

- Content shell: `max-w-[1400px] mx-auto space-y-6 pb-10`.
- Stat card padding: `p-5`.
- Panel/chart card padding: `p-6`.
- Grid gap: `gap-5` for cards, `gap-6` for larger sections.
- Sections: `rounded-3xl`; stat cards: `rounded-2xl`; inputs and buttons: `rounded-xl`.
- Stat grids: `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4`.
- Prefer clear vertical rhythm over dense decorative elements.
- Avoid crowded layouts; group related content with consistent spacing.

### Shared Components

**Cards**

- Use `bg-white border border-gray-100 shadow-sm`.
- Use `.lift` for hover elevation.
- Use `.reveal` for scroll-in visibility.
- Avoid heavy glow layers and gratuitous gradients inside cards.

**Animations**

- `.anim-fade-up`, `.anim-fade`, `.anim-scale-in`, `.anim-slide-down`.
- `.anim-pulse-glow` for live/status indicators.
- `.stagger-1` through `.stagger-6` for entrance delays.
- Animation should support hierarchy, not compete with data.

**Navigation**

- Use `.nav-item` and `.nav-active` from `global.css`.
- Active nav items use the brand background and white text.

**Buttons**

- Primary: brand gradient `from-[#FF751F] to-[#E4650F]`, darker hover, white text.
- Shape: `rounded-xl`, `py-3.5`, `px-4`, `font-black uppercase tracking-wider`.
- Include visible focus states and hover elevation.

**Form Fields**

- Background: `bg-[#F8F9FA]`.
- Border: `border-gray-200`.
- Shape: `rounded-xl`, `py-3.5`, `pl-11`, `pr-4`.
- Focus: white background, brand border, soft brand ring.
- Labels: `text-[11px] font-black uppercase tracking-wider text-gray-500`.

**Badges and Status**

- Use semantic background, border, and text colors.
- Rounded: `rounded-lg` or `rounded-full` for status pills.
- Keep status indicators small and consistent.

**Loading**

- Use the shared `.skeleton` class for skeleton loaders.
- Loading buttons should preserve their original IDs and labels.

### Implementation Rules

- Preserve all Django template logic: `{% block %}`, `{{ variables }}`, `{% url %}`, `{% csrf_token %}`, and filters.
- Preserve IDs, names, form actions, and methods used by JavaScript or backend views.
- Preserve all chart endpoints, data attributes, and counters.
- Remove page-specific CSS when an equivalent global class exists.
- When a page-specific style is truly unique, keep it scoped and minimal.
- After each batch, run:
  - `venv/bin/python manage.py check`
  - Template compilation/rendering checks
  - A quick browser review for layout and interaction regressions

## Completed Files

### Design System

- [x] `static/css/global.css`
- [x] `static/js/main.js`

### Base Templates

- [x] `web/templates/base.html`
- [x] `web/templates/admin_base.html`
- [x] `web/templates/login_base.html`

### Pages

- [x] `web/templates/pages/dashboard.html`
- [x] `web/templates/pages/login.html`
- [x] `web/templates/pages/users.html`
- [x] `web/templates/pages/deliveries.html`
- [x] `web/templates/pages/escrow_payments.html`

Completed pages now use shared global classes and have no inline `<style>` blocks. Batch 2 also consolidated `.custom-scrollbar` and the delivery tab state into `static/css/global.css`.

## Remaining Batches

### Batch 3 - Verification and Moderation

- [ ] `web/templates/pages/provider_verification.html`
- [ ] `web/templates/pages/vehicle_verification.html`
- [ ] `web/templates/pages/admin_disputes.html`
- [ ] `web/templates/pages/ratings_feedback.html`

### Batch 4 - Reporting and Configuration

- [ ] `web/templates/pages/reports.html`
- [ ] `web/templates/pages/settings.html`

### Batch 5 - Support, Shared Layouts, and Public Pages

- [ ] `web/templates/admin_fullscreen_base.html`
- [ ] `web/templates/admin_support_inbox.html`
- [ ] `web/templates/pages/landing.html`
- [ ] `web/templates/pages/generic_placeholder.html`

## Known Cleanup Opportunities

- `.custom-scrollbar` is now global. `provider_verification.html`, `vehicle_verification.html`, `admin_disputes.html`, and `ratings_feedback.html` should drop their local copies during Batch 3.
- Delivery tabs now use the shared `.tab-btn` / `.active` styles from `global.css`.
- `admin_support_inbox.html` has a large inline `<style>` and `<script>` block that should be reviewed during Batch 5.
- `admin_fullscreen_base.html` still contains an inline Tailwind config and should be aligned with the shared base/static setup.
- Page-specific animations in the remaining files should be replaced with shared utility classes wherever possible.
