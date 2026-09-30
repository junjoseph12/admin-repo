import streamlit as st
import base64
import os

# ==========================================
# 1. PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="Pack-N-Ship · Peer-to-Peer Micro-Move Logistics",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# APK DOWNLOAD LINK
# ==========================================
APK_DOWNLOAD_LINK = "https://drive.google.com/drive/folders/1ywrPTfC0-lytwTvwrK-0g3Gky9JW2IQi?usp=drive_link"

# ==========================================
# 2. ICON LOADER
# ==========================================
def get_icon_b64(path):
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except Exception:
        pass
    return None

ICON_PATHS = {
    "logo":     "web/static/images/packnship_logo.png",
    "business": "web/static/images/report_icon.png",
    "personal": "web/static/images/totaldeliveries_icon.png",
    "driver":   "web/static/images/carverification_icon.png",
}
ICONS = {k: get_icon_b64(v) for k, v in ICON_PATHS.items()}

def icon_img(key, size=48, fallback="📦"):
    b64 = ICONS.get(key)
    if b64:
        return f'<img src="data:image/png;base64,{b64}" style="width:{size}px;height:{size}px;object-fit:contain;display:block;" alt="" />'
    return f'<span style="font-size:{size}px;line-height:1;">{fallback}</span>'

# ==========================================
# 3. SURGICAL STREAMLIT RESET
# ==========================================
reset_css = """
<style>
html, body {
  margin: 0 !important;
  padding: 0 !important;
  background: #ffffff;
  overflow-x: hidden;
}

/* Hide Streamlit's chrome only */
header[data-testid="stHeader"],
[data-testid="stHeader"],
.stApp > header,
#MainMenu,
footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"],
.stAppDeployButton {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  min-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  border: none !important;
}

.block-container,
[data-testid="stAppViewContainer"] > .main .block-container {
  padding: 0 !important;
  margin: 0 !important;
  max-width: 100% !important;
}

[data-testid="stAppViewContainer"],
.stApp,
.stMain,
section.main {
  background: #ffffff !important;
  padding: 0 !important;
  margin: 0 !important;
}

[data-testid="stHorizontalBlock"] {
  gap: 1.5rem !important;
}

* { -webkit-tap-highlight-color: transparent; }
.brand, .brand *, .nav-links a, .nav-links a *, .hero-eyebrow,
.section-eyebrow, .live-pill, .live-pill *,
.nav-signup, .nav-signup * {
  -webkit-user-select: none;
  -moz-user-select: none;
  user-select: none;
}
::selection { background: rgba(255,117,31,0.3); color: inherit; }
::-moz-selection { background: rgba(255,117,31,0.3); color: inherit; }
</style>
"""
st.markdown(reset_css, unsafe_allow_html=True)

# ==========================================
# 4. MAIN CSS
# ==========================================
css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --orange-50:  #fff7ed;
  --orange-100: #ffedd5;
  --orange-200: #fed7aa;
  --orange-300: #fdba74;
  --orange-400: #ff9d54;
  --orange-500: #FF751F;
  --orange-600: #E4650F;
  --orange-700: #B84708;
  --ink-900: #0a0a0a;
  --ink-800: #111827;
  --ink-700: #1f2937;
  --ink-600: #4b5563;
  --ink-500: #6b7280;
  --ink-400: #9ca3af;
  --line: #f3f4f6;
  --line-2: #e5e7eb;
  --spring: cubic-bezier(.22,1,.36,1);
  --spring-bounce: cubic-bezier(.34,1.56,.64,1);
  --ease: cubic-bezier(.4,0,.2,1);
}

html, body, [class*="css"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-feature-settings: 'cv02','cv03','cv04','cv11';
  color: var(--ink-800);
  background: #ffffff;
}

html { scroll-behavior: smooth; scroll-padding-top: 100px; }

::-webkit-scrollbar { width: 12px; height: 12px; }
::-webkit-scrollbar-track { background: #f9fafb; }
::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, var(--orange-500), var(--orange-600));
  border-radius: 10px;
  border: 3px solid #f9fafb;
}
::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, var(--orange-600), var(--orange-700)); }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* ============ KEYFRAMES ============ */
@keyframes fadeUp { from { opacity: 0; transform: translateY(40px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideDown { from { opacity: 0; transform: translateY(-16px); } to { opacity: 1; transform: translateY(0); } }
@keyframes float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-16px); } }
@keyframes floatSmall { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
@keyframes orbFloat1 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(-60px,50px) scale(1.2); } }
@keyframes orbFloat2 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(70px,-40px) scale(1.15); } }
@keyframes orbFloat3 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(-40px,-60px) scale(1.1); } }
@keyframes pulseRing { 0% { box-shadow: 0 0 0 0 rgba(255,117,31,0.6); } 70% { box-shadow: 0 0 0 14px rgba(255,117,31,0); } 100% { box-shadow: 0 0 0 0 rgba(255,117,31,0); } }
@keyframes marqueeScroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
@keyframes shimmer { 0% { transform: translateX(-120%) skewX(-20deg); } 100% { transform: translateX(320%) skewX(-20deg); } }
@keyframes gradientPan { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes spinSlow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes spinRev { from { transform: rotate(360deg); } to { transform: rotate(0deg); } }
@keyframes glowPulse { 0%,100% { box-shadow: 0 0 30px rgba(255,117,31,0.35); } 50% { box-shadow: 0 0 60px rgba(255,117,31,0.6); } }
@keyframes livePulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.35; transform: scale(1.5); } }
@keyframes waveBar { 0%,100% { transform: scaleY(0.3); } 50% { transform: scaleY(1); } }
@keyframes navLine { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes targetPulse { 0% { box-shadow: 0 0 0 0 rgba(255,117,31,0.6); } 40% { box-shadow: 0 0 0 22px rgba(255,117,31,0); } 100% { box-shadow: 0 0 0 0 rgba(255,117,31,0); } }

/* ============ UTILITY ============ */
.fade-up { animation: fadeUp 0.9s var(--spring) both; }
.stagger-1 { animation-delay: 0.05s; }
.stagger-2 { animation-delay: 0.15s; }
.stagger-3 { animation-delay: 0.25s; }
.stagger-4 { animation-delay: 0.35s; }
.stagger-5 { animation-delay: 0.45s; }

/* ============================================================
   NAVBAR — FULL-WIDTH PREMIUM BAR
   ============================================================ */
.topnav {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 68px;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 3rem;
  background: rgba(255,255,255,0.82);
  backdrop-filter: saturate(200%) blur(20px);
  -webkit-backdrop-filter: saturate(200%) blur(20px);
  border-bottom: 1px solid rgba(0,0,0,0.055);
  animation: slideDown 0.6s var(--spring) both;
}
.topnav::after {
  content: '';
  position: absolute;
  bottom: -1px; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--orange-500) 30%, var(--orange-400) 50%, var(--orange-500) 70%, transparent);
  background-size: 200% 100%;
  opacity: 0.55;
  animation: navLine 6s ease infinite;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 19px;
  font-weight: 900;
  letter-spacing: -0.9px;
  color: var(--ink-800);
  cursor: pointer;
  text-decoration: none;
  padding: 8px 4px;
  transition: transform 0.3s var(--spring);
  flex-shrink: 0;
}
.brand:hover { transform: translateY(-1px); }
.brand .brand-logo {
  width: 32px; height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.5s var(--spring-bounce);
  flex-shrink: 0;
}
.brand:hover .brand-logo { transform: rotate(-8deg) scale(1.1); }
.brand .brand-text { white-space: nowrap; }
.brand .brand-text .n {
  color: var(--orange-500);
  transition: text-shadow 0.3s;
}
.brand:hover .brand-text .n { text-shadow: 0 0 16px rgba(255,117,31,0.6); }

.nav-links {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}
.nav-links a {
  position: relative;
  color: var(--ink-600);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 600;
  padding: 8px 14px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  transition: color 0.25s var(--ease), background 0.25s;
  white-space: nowrap;
  letter-spacing: -0.1px;
}
.nav-links a .nav-num {
  font-size: 10px;
  font-weight: 800;
  color: var(--orange-500);
  font-family: ui-monospace, monospace;
  letter-spacing: 0;
  opacity: 0.6;
  transition: opacity 0.25s;
}
.nav-links a:hover { color: var(--ink-800); background: rgba(15,23,42,0.04); }
.nav-links a:hover .nav-num { opacity: 1; }
.nav-links a::after {
  content: '';
  position: absolute;
  bottom: 3px; left: 14px; right: 14px;
  height: 1.5px;
  background: linear-gradient(90deg, var(--orange-500), var(--orange-600));
  border-radius: 2px;
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.35s var(--spring);
}
.nav-links a:hover::after { transform: scaleX(1); }

.nav-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}
.live-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 11px;
  background: rgba(16,185,129,0.1);
  border: 1px solid rgba(16,185,129,0.35);
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 800;
  color: #065f46;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  white-space: nowrap;
}
.live-pill .live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: livePulse 1.6s infinite;
}
.nav-signup {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 11px;
  font-size: 12.5px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  text-decoration: none;
  color: white !important;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  overflow: hidden;
  isolation: isolate;
  box-shadow: 0 6px 16px rgba(255,117,31,0.35), inset 0 1px 0 rgba(255,255,255,0.35);
  transition: transform 0.3s var(--spring-bounce), box-shadow 0.3s;
  white-space: nowrap;
}
.nav-signup::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 50%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent);
  transform: translateX(-150%) skewX(-20deg);
  transition: transform 0.6s;
  z-index: 1;
}
.nav-signup:hover::before { transform: translateX(260%) skewX(-20deg); }
.nav-signup > * { position: relative; z-index: 1; }
.nav-signup:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(255,117,31,0.5), inset 0 1px 0 rgba(255,255,255,0.35);
}
.nav-signup:active { transform: scale(0.96); }
.nav-signup .btn-arrow {
  display: inline-block;
  transition: transform 0.3s var(--spring);
  font-weight: 900;
}
.nav-signup:hover .btn-arrow { transform: translateX(3px); }

/* ============================================================
   HERO
   ============================================================ */
.hero {
  position: relative;
  background: linear-gradient(135deg, #050505 0%, #1a0e00 40%, #2b1600 70%, #1a0e00 100%);
  padding: 10rem 3.5rem 8rem 3.5rem;
  overflow: hidden;
  isolation: isolate;
}
.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,117,31,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,117,31,0.04) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse at 30% 40%, black 20%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse at 30% 40%, black 20%, transparent 75%);
  pointer-events: none;
}
.hero-orb-1 {
  position: absolute;
  top: -200px; right: -150px;
  width: 700px; height: 700px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,117,31,0.55) 0%, transparent 65%);
  filter: blur(80px);
  animation: orbFloat1 22s ease-in-out infinite;
  pointer-events: none;
}
.hero-orb-2 {
  position: absolute;
  bottom: -250px; left: -200px;
  width: 600px; height: 600px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,180,80,0.4) 0%, transparent 65%);
  filter: blur(80px);
  animation: orbFloat2 26s ease-in-out infinite;
  pointer-events: none;
}
.hero-orb-3 {
  position: absolute;
  top: 40%; left: 45%;
  width: 500px; height: 500px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,90,0,0.22) 0%, transparent 65%);
  filter: blur(90px);
  animation: orbFloat3 30s ease-in-out infinite;
  pointer-events: none;
}

.particles {
  position: absolute; inset: 0;
  pointer-events: none; overflow: hidden;
}
.particle {
  position: absolute;
  width: 3px; height: 3px; border-radius: 50%;
  background: rgba(255,117,31,0.65);
  box-shadow: 0 0 8px rgba(255,117,31,0.9);
  animation: floatSmall 4.5s ease-in-out infinite;
}
.particle:nth-child(1) { top: 15%; left: 12%; }
.particle:nth-child(2) { top: 25%; left: 78%; animation-delay: 0.5s; width: 4px; height: 4px; }
.particle:nth-child(3) { top: 65%; left: 22%; animation-delay: 1.2s; }
.particle:nth-child(4) { top: 80%; left: 65%; animation-delay: 0.8s; width: 5px; height: 5px; }
.particle:nth-child(5) { top: 45%; left: 90%; animation-delay: 2s; }
.particle:nth-child(6) { top: 10%; left: 45%; animation-delay: 1.5s; width: 2px; height: 2px; }
.particle:nth-child(7) { top: 88%; left: 38%; animation-delay: 0.3s; }
.particle:nth-child(8) { top: 35%; left: 5%; animation-delay: 1.8s; width: 4px; height: 4px; }
.particle:nth-child(9) { top: 72%; left: 88%; animation-delay: 2.3s; }
.particle:nth-child(10) { top: 55%; left: 55%; animation-delay: 0.7s; }
.particle:nth-child(11) { top: 5%; left: 68%; animation-delay: 1.1s; }
.particle:nth-child(12) { top: 92%; left: 15%; animation-delay: 2.6s; width: 4px; height: 4px; }

.hero-inner {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5rem;
  align-items: center;
  max-width: 1340px;
  margin: 0 auto;
}

.hero-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 9px 18px;
  background: rgba(255,117,31,0.1);
  border: 1px solid rgba(255,117,31,0.32);
  border-radius: 999px;
  color: #ffb066;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 2.4px;
  text-transform: uppercase;
  margin-bottom: 2rem;
  backdrop-filter: blur(10px);
  position: relative;
}
.hero-eyebrow .dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--orange-500);
  animation: pulseRing 2s infinite;
  box-shadow: 0 0 12px var(--orange-500);
  flex-shrink: 0;
}

.hero-title {
  font-size: clamp(2.5rem, 6vw, 5.25rem);
  font-weight: 900;
  color: white;
  line-height: 0.94;
  letter-spacing: -0.048em;
  margin: 0 0 1.75rem 0;
  text-shadow: 0 4px 40px rgba(0,0,0,0.4);
}
.hero-title .gradient {
  background: linear-gradient(90deg, #FF751F 0%, #ffb066 35%, #fff5eb 50%, #ffb066 65%, #FF751F 100%);
  background-size: 250% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: gradientPan 5s ease infinite;
  filter: drop-shadow(0 0 30px rgba(255,117,31,0.35));
}

.hero-subtitle {
  font-size: clamp(1rem, 1.4vw, 1.15rem);
  color: rgba(255,255,255,0.78);
  line-height: 1.7;
  font-weight: 500;
  margin-bottom: 2.5rem;
  max-width: 540px;
}

.hero-cta-row {
  display: flex;
  gap: 0.85rem;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 3rem;
}

.hero-cta {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  color: white !important;
  font-weight: 800;
  padding: 17px 34px;
  border-radius: 13px;
  text-decoration: none;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  overflow: hidden;
  isolation: isolate;
  box-shadow:
    0 14px 32px rgba(255,117,31,0.42),
    inset 0 1px 0 rgba(255,255,255,0.3),
    inset 0 -1px 0 rgba(0,0,0,0.1);
  transition: transform 0.3s var(--spring-bounce), box-shadow 0.3s;
}
.hero-cta::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 55%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
  transform: translateX(-150%) skewX(-20deg);
  transition: transform 0.8s;
}
.hero-cta:hover {
  transform: translateY(-3px) scale(1.015);
  box-shadow:
    0 24px 50px rgba(255,117,31,0.55),
    inset 0 1px 0 rgba(255,255,255,0.3),
    inset 0 -1px 0 rgba(0,0,0,0.1);
}
.hero-cta:hover::before { transform: translateX(320%) skewX(-20deg); }

.hero-cta-secondary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: rgba(255,255,255,0.05);
  backdrop-filter: blur(14px);
  border: 1.5px solid rgba(255,255,255,0.18);
  color: white !important;
  font-weight: 700;
  padding: 16px 28px;
  border-radius: 13px;
  text-decoration: none;
  font-size: 14px;
  transition: all 0.3s var(--spring);
}
.hero-cta-secondary:hover {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,117,31,0.6);
  transform: translateY(-3px);
}

.hero-trust {
  display: flex;
  align-items: center;
  gap: 1.6rem;
  color: rgba(255,255,255,0.6);
  font-size: 11.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.4px;
  flex-wrap: wrap;
}
.hero-trust .badge { display: flex; align-items: center; gap: 7px; }
.hero-trust svg { color: var(--orange-500); flex-shrink: 0; }

.hero-visual {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 620px;
}
.phone-orbit {
  position: absolute;
  width: 300px; height: 300px;
  border-radius: 50%;
  border: 1px dashed rgba(255,117,31,0.28);
  animation: spinSlow 32s linear infinite;
  pointer-events: none;
}
.phone-orbit::before, .phone-orbit::after {
  content: '';
  position: absolute;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--orange-500);
  box-shadow: 0 0 14px var(--orange-500);
}
.phone-orbit::before { top: -4px; left: 50%; transform: translateX(-50%); }
.phone-orbit::after { bottom: -4px; left: 50%; transform: translateX(-50%); background: #4ade80; box-shadow: 0 0 14px #4ade80; }
.phone-orbit-2 {
  position: absolute;
  width: 400px; height: 400px;
  border-radius: 50%;
  border: 1px dashed rgba(255,117,31,0.14);
  animation: spinRev 48s linear infinite;
  pointer-events: none;
}
.phone-mockup {
  width: 290px; height: 590px;
  border-radius: 48px;
  background: linear-gradient(135deg, #1f1f1f, #0a0a0a);
  padding: 14px;
  box-shadow:
    0 50px 100px rgba(0,0,0,0.6),
    0 0 0 1px rgba(255,255,255,0.08),
    0 0 0 9px rgba(0,0,0,0.5),
    inset 0 0 40px rgba(255,117,31,0.06);
  position: relative;
  animation: float 6s ease-in-out infinite;
  z-index: 2;
}
.phone-screen {
  width: 100%; height: 100%;
  border-radius: 36px;
  background: linear-gradient(160deg, #0a0a0a 0%, #1a0f00 55%, #FF751F 200%);
  padding: 1.75rem 1.1rem 1.1rem 1.1rem;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.phone-screen::before {
  content: '';
  position: absolute;
  top: -100px; right: -100px;
  width: 300px; height: 300px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,117,31,0.55), transparent 60%);
  filter: blur(40px);
}
.phone-notch {
  position: absolute;
  top: 8px; left: 50%;
  transform: translateX(-50%);
  width: 88px; height: 22px;
  background: #000;
  border-radius: 999px;
  z-index: 10;
}
.mini-card {
  background: rgba(255,255,255,0.07);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.13);
  border-radius: 14px;
  padding: 12px 14px;
  color: white;
  position: relative;
  z-index: 1;
}
.mini-card .label {
  font-size: 9px;
  font-weight: 800;
  color: rgba(255,255,255,0.55);
  letter-spacing: 1.6px;
  text-transform: uppercase;
}
.mini-card .value {
  font-size: 17px;
  font-weight: 900;
  color: white;
  margin-top: 3px;
}
.mini-card .value.orange {
  color: var(--orange-500);
  text-shadow: 0 0 12px rgba(255,117,31,0.5);
}
.mini-card.accent {
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  border-color: rgba(255,255,255,0.25);
  box-shadow: 0 8px 24px rgba(255,117,31,0.4);
}
.mini-card.accent .label { color: rgba(255,255,255,0.9); }
.mini-card .live-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #4ade80;
  margin-right: 6px;
  animation: livePulse 1.5s infinite;
  vertical-align: middle;
  box-shadow: 0 0 8px #4ade80;
}
.waveform {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: 14px;
  margin-left: 6px;
  vertical-align: middle;
}
.waveform span {
  display: inline-block;
  width: 2px; height: 100%;
  background: #4ade80;
  border-radius: 2px;
  transform-origin: bottom;
  animation: waveBar 0.9s ease-in-out infinite;
}
.waveform span:nth-child(1) { animation-delay: 0s; }
.waveform span:nth-child(2) { animation-delay: 0.1s; }
.waveform span:nth-child(3) { animation-delay: 0.2s; }
.waveform span:nth-child(4) { animation-delay: 0.3s; }
.waveform span:nth-child(5) { animation-delay: 0.4s; }

.float-chip {
  position: absolute;
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.7);
  border-radius: 15px;
  padding: 10px 15px;
  box-shadow:
    0 20px 50px rgba(0,0,0,0.25),
    0 0 0 1px rgba(255,255,255,0.9) inset;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  font-weight: 800;
  color: var(--ink-800);
  animation: floatSmall 5s ease-in-out infinite;
  z-index: 3;
  white-space: nowrap;
}
.float-chip .chip-icon {
  width: 32px; height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
  flex-shrink: 0;
  box-shadow: 0 6px 14px rgba(255,117,31,0.35);
}
.float-chip.left { top: 20%; left: -40px; }
.float-chip.right { top: 62%; right: -50px; animation-delay: 1.5s; }

/* ============================================================
   MARQUEE
   ============================================================ */
.marquee-wrap {
  background: white;
  padding: 2.5rem 0;
  border-bottom: 1px solid var(--line);
  overflow: hidden;
  position: relative;
  mask-image: linear-gradient(90deg, transparent 0%, black 12%, black 88%, transparent 100%);
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, black 12%, black 88%, transparent 100%);
}
.marquee-label {
  text-align: center;
  font-size: 10.5px;
  font-weight: 800;
  color: var(--ink-400);
  letter-spacing: 3px;
  text-transform: uppercase;
  margin-bottom: 1.5rem;
  padding: 0 1rem;
}
.marquee {
  display: flex;
  width: fit-content;
  animation: marqueeScroll 35s linear infinite;
}
.marquee:hover { animation-play-state: paused; }
.marquee-item {
  padding: 0 3rem;
  font-size: 20px;
  font-weight: 900;
  color: var(--ink-400);
  font-style: italic;
  letter-spacing: -1px;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: color 0.3s;
}
.marquee-item:hover { color: var(--orange-500); }
.marquee-item span {
  font-style: normal;
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 2px;
}

/* ============================================================
   SECTIONS
   ============================================================ */
.section {
  padding: 6rem 3.5rem;
  position: relative;
  max-width: 1400px;
  margin: 0 auto;
}
.section-eyebrow {
  display: inline-block;
  color: var(--orange-500);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 3px;
  text-transform: uppercase;
  margin-bottom: 0.75rem;
}
.section-title {
  font-size: clamp(2rem, 4vw, 3.1rem);
  font-weight: 900;
  color: var(--ink-800);
  letter-spacing: -0.045em;
  margin: 0 0 1rem 0;
  line-height: 1.05;
}
.section-subtitle {
  color: var(--ink-500);
  font-size: 1.05rem;
  max-width: 640px;
  font-weight: 500;
  line-height: 1.65;
}
.text-center { text-align: center; }
.text-center .section-subtitle { margin-left: auto; margin-right: auto; }

/* ============================================================
   FEATURE CARDS
   ============================================================ */
.feature-card {
  background: linear-gradient(140deg, #FF751F 0%, #E4650F 55%, #B84708 100%);
  border-radius: 24px;
  padding: 2.5rem 2rem;
  color: white;
  height: 100%;
  min-height: 380px;
  box-shadow:
    0 20px 50px rgba(255,117,31,0.25),
    inset 0 1px 0 rgba(255,255,255,0.2);
  transition: transform 0.5s var(--spring), box-shadow 0.5s;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.feature-card::before {
  content: '';
  position: absolute;
  top: -80px; right: -80px;
  width: 240px; height: 240px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,0.15), transparent 70%);
  transition: transform 0.6s var(--spring);
  pointer-events: none;
}
.feature-card::after {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 55%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
  transform: translateX(-150%) skewX(-20deg);
  transition: transform 0.9s;
  pointer-events: none;
}
.feature-card:hover {
  transform: translateY(-10px);
  box-shadow: 0 40px 80px rgba(255,117,31,0.42), inset 0 1px 0 rgba(255,255,255,0.3);
}
.feature-card:hover::after { transform: translateX(300%) skewX(-20deg); }
.feature-card:hover::before { transform: scale(1.4); }
.feature-icon-box {
  width: 62px; height: 62px;
  border-radius: 16px;
  background: rgba(255,255,255,0.2);
  border: 1px solid rgba(255,255,255,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1.5rem;
  transition: transform 0.5s var(--spring-bounce);
  flex-shrink: 0;
}
.feature-card:hover .feature-icon-box { transform: rotate(10deg) scale(1.1); }
.feature-card h3 {
  color: white;
  font-size: 1.65rem;
  font-weight: 900;
  letter-spacing: -0.7px;
  margin: 0 0 0.9rem 0;
}
.feature-card p {
  color: rgba(255,255,255,0.93);
  font-size: 0.95rem;
  line-height: 1.65;
  margin: 0 0 1.75rem 0;
  flex: 1;
}
.feature-link {
  color: white !important;
  font-weight: 900;
  font-size: 0.82rem;
  text-decoration: none;
  text-transform: uppercase;
  letter-spacing: 1px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: gap 0.3s var(--spring);
}
.feature-link:hover { gap: 14px; }

/* ============================================================
   HOW IT WORKS
   ============================================================ */
.how-wrap {
  background: linear-gradient(180deg, var(--orange-50) 0%, #ffffff 100%);
  padding: 6rem 3.5rem;
  position: relative;
  overflow: hidden;
}
.how-wrap::before {
  content: '';
  position: absolute;
  top: 30%; left: 50%;
  transform: translateX(-50%);
  width: 80%; height: 300px;
  background: radial-gradient(ellipse, rgba(255,117,31,0.08), transparent 70%);
  filter: blur(60px);
  pointer-events: none;
}
.how-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2rem;
  max-width: 1280px;
  margin: 4rem auto 0 auto;
  position: relative;
}
.how-grid::before {
  content: '';
  position: absolute;
  top: 36px; left: 12%; right: 12%;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--orange-300) 15%, var(--orange-300) 85%, transparent);
  z-index: 0;
}
.how-step {
  text-align: center;
  position: relative;
  padding: 1rem 0.5rem;
  z-index: 1;
}
.how-step .num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px; height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  color: white;
  font-size: 24px;
  font-weight: 900;
  box-shadow: 0 15px 40px rgba(255,117,31,0.4);
  margin-bottom: 1.5rem;
  position: relative;
  border: 4px solid white;
  transition: transform 0.4s var(--spring-bounce);
}
.how-step:hover .num { transform: scale(1.1) rotate(6deg); }
.how-step .num::before {
  content: '';
  position: absolute;
  inset: -10px;
  border-radius: 50%;
  border: 2px dashed rgba(255,117,31,0.35);
  animation: spinSlow 20s linear infinite;
}
.how-step h3 {
  font-size: 1.15rem;
  font-weight: 900;
  color: var(--ink-800);
  letter-spacing: -0.5px;
  margin: 0 0 0.7rem 0;
}
.how-step p {
  color: var(--ink-500);
  font-size: 0.88rem;
  line-height: 1.65;
  max-width: 260px;
  margin: 0 auto;
}

/* ============================================================
   STATS
   ============================================================ */
.stats-band {
  background:
    radial-gradient(ellipse at top, rgba(255,117,31,0.2), transparent 60%),
    linear-gradient(135deg, #0a0a0a, #111827);
  padding: 4rem 2rem;
  border-radius: 32px;
  max-width: 1250px;
  margin: 3rem auto;
  position: relative;
  overflow: hidden;
  box-shadow: 0 30px 80px rgba(0,0,0,0.25);
  border: 1px solid rgba(255,255,255,0.06);
}
.stats-band::before {
  content: '';
  position: absolute;
  top: -150px; left: 50%;
  transform: translateX(-50%);
  width: 700px; height: 300px;
  background: radial-gradient(circle, rgba(255,117,31,0.35) 0%, transparent 70%);
  filter: blur(50px);
  pointer-events: none;
}
.stats-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
  max-width: 1100px;
  margin: 0 auto;
}
.stat-block {
  text-align: center;
  padding: 1.5rem 1rem;
  border-right: 1px solid rgba(255,255,255,0.08);
  transition: transform 0.4s var(--spring);
}
.stat-block:last-child { border-right: none; }
.stat-block:hover { transform: translateY(-6px); }
.stat-block .num {
  font-size: clamp(2rem, 4vw, 3.2rem);
  font-weight: 900;
  background: linear-gradient(135deg, #FF751F, #ffb066);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.05em;
  line-height: 1;
  margin: 0 0 0.6rem 0;
  filter: drop-shadow(0 0 20px rgba(255,117,31,0.35));
}
.stat-block .label {
  font-size: 10.5px;
  font-weight: 800;
  color: rgba(255,255,255,0.55);
  letter-spacing: 2px;
  text-transform: uppercase;
  margin: 0;
}

/* ============================================================
   BENTO GRID
   ============================================================ */
.bento-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  grid-auto-rows: 155px;
  gap: 1.25rem;
  margin-top: 3rem;
  max-width: 1280px;
  margin-left: auto;
  margin-right: auto;
}
.bento-card {
  background: white;
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 1.75rem 1.5rem;
  box-shadow: 0 8px 28px rgba(15,23,42,0.05);
  transition: all 0.4s var(--spring);
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.bento-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--orange-500), var(--orange-600));
  transform: scaleX(0);
  transition: transform 0.4s var(--spring);
  transform-origin: left;
}
.bento-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 24px 50px rgba(255,117,31,0.13);
  border-color: var(--orange-100);
}
.bento-card:hover::before { transform: scaleX(1); }
.bento-icon {
  width: 50px; height: 50px;
  border-radius: 13px;
  background: linear-gradient(135deg, var(--orange-50), var(--orange-100));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  margin-bottom: 1rem;
  border: 1px solid rgba(255,117,31,0.1);
  flex-shrink: 0;
}
.bento-card h4 {
  font-size: 0.98rem;
  font-weight: 800;
  color: var(--ink-800);
  margin: 0 0 0.4rem 0;
  letter-spacing: -0.3px;
}
.bento-card p {
  font-size: 0.81rem;
  color: var(--ink-500);
  line-height: 1.5;
  margin: 0;
}
.bento-span-2x1 { grid-column: span 2; }
.bento-wide { grid-column: span 3; grid-row: span 1; }
.bento-tall { grid-column: span 2; grid-row: span 2; }

/* ============================================================
   ESCROW FLOW
   ============================================================ */
.escrow-flow {
  display: flex;
  align-items: stretch;
  margin-top: 3rem;
  background: white;
  border-radius: 26px;
  padding: 2.75rem 2rem;
  box-shadow: 0 20px 60px rgba(15,23,42,0.07);
  border: 1px solid var(--line);
  flex-wrap: wrap;
  position: relative;
  overflow: hidden;
}
.escrow-flow::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 4px;
  background: linear-gradient(90deg, var(--orange-500), var(--orange-300), var(--orange-500));
  background-size: 200% auto;
  animation: gradientPan 4s linear infinite;
}
.escrow-step {
  flex: 1;
  min-width: 200px;
  text-align: center;
  padding: 1rem;
  position: relative;
}
.escrow-step:not(:last-child)::after {
  content: '';
  position: absolute;
  right: -14px; top: 50%;
  transform: translateY(-50%);
  width: 28px; height: 2px;
  background: linear-gradient(90deg, var(--orange-500), transparent);
  opacity: 0.5;
}
.escrow-step .step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px; height: 54px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  color: white;
  font-size: 20px;
  font-weight: 900;
  margin-bottom: 1rem;
  box-shadow: 0 12px 30px rgba(255,117,31,0.35);
}
.escrow-step h4 {
  font-size: 1rem;
  font-weight: 800;
  color: var(--ink-800);
  margin: 0 0 0.5rem 0;
}
.escrow-step p {
  font-size: 0.85rem;
  color: var(--ink-500);
  line-height: 1.55;
  margin: 0;
}

/* ============================================================
   DELIVERY MODES
   ============================================================ */
.modes-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
  margin-top: 3rem;
}
.mode-card {
  background: white;
  border: 2px solid var(--line);
  border-radius: 24px;
  padding: 2.5rem 2rem;
  transition: all 0.45s var(--spring);
  position: relative;
  overflow: hidden;
}
.mode-card::before {
  content: '';
  position: absolute;
  top: -100px; right: -100px;
  width: 260px; height: 260px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,117,31,0.08), transparent 70%);
  transition: transform 0.6s;
  pointer-events: none;
}
.mode-card:hover {
  border-color: var(--orange-500);
  transform: translateY(-8px);
  box-shadow: 0 30px 60px rgba(255,117,31,0.16);
}
.mode-card:hover::before { transform: scale(1.5); }
.mode-card .mode-tag {
  display: inline-block;
  padding: 7px 15px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin-bottom: 1.25rem;
}
.mode-card .mode-tag.orange {
  background: var(--orange-50);
  color: var(--orange-500);
  border: 1px solid var(--orange-200);
}
.mode-card .mode-tag.dark {
  background: var(--ink-800);
  color: white;
}
.mode-card h3 {
  font-size: 1.75rem;
  font-weight: 900;
  color: var(--ink-800);
  letter-spacing: -0.8px;
  margin: 0 0 0.75rem 0;
}
.mode-card p {
  color: var(--ink-500);
  font-size: 0.95rem;
  line-height: 1.65;
  margin: 0 0 1.5rem 0;
}
.mode-card ul { list-style: none; padding: 0; margin: 0; }
.mode-card ul li {
  color: var(--ink-700);
  font-size: 0.9rem;
  padding: 0.5rem 0;
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 500;
}
.mode-card ul li::before {
  content: '✓';
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px; height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  color: white;
  font-size: 11px;
  font-weight: 900;
  flex-shrink: 0;
}

/* ============================================================
   DOWNLOAD BAND
   ============================================================ */
.download-band {
  background: linear-gradient(135deg, var(--orange-500) 0%, var(--orange-600) 40%, var(--orange-700) 70%, var(--orange-600) 100%);
  background-size: 300% auto;
  animation: gradientPan 10s ease infinite;
  padding: 3.5rem 3rem;
  border-radius: 32px;
  max-width: 1250px;
  margin: 3rem auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  flex-wrap: wrap;
  position: relative;
  overflow: hidden;
  box-shadow: 0 30px 70px rgba(255,117,31,0.38);
}
.download-band::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 55%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent);
  transform: translateX(-150%) skewX(-20deg);
  animation: shimmer 4.5s ease-in-out infinite;
  animation-delay: 1s;
  pointer-events: none;
}
.download-left { position: relative; z-index: 2; }
.download-band h3 {
  color: white;
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  font-weight: 900;
  letter-spacing: -1px;
  margin: 0 0 0.5rem 0;
}
.download-band p {
  color: rgba(255,255,255,0.92);
  margin: 0;
  font-size: 0.98rem;
}
.download-btn {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  background: white;
  color: var(--orange-600) !important;
  font-weight: 900;
  padding: 17px 32px;
  border-radius: 13px;
  text-decoration: none;
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  box-shadow: 0 15px 35px rgba(0,0,0,0.22);
  transition: transform 0.3s var(--spring-bounce);
  animation: glowPulse 3s ease-in-out infinite;
}
.download-btn:hover { transform: translateY(-4px) scale(1.02); }

/* ============================================================
   TECH STRIP
   ============================================================ */
.tech-strip {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 11px;
  margin-top: 3rem;
  max-width: 1000px;
  margin-left: auto;
  margin-right: auto;
}
.tech-pill {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 11px 19px;
  background: white;
  border: 1px solid var(--line-2);
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--ink-700);
  transition: all 0.35s var(--spring);
}
.tech-pill:hover {
  border-color: var(--orange-500);
  color: var(--orange-600);
  transform: translateY(-4px);
  box-shadow: 0 12px 30px rgba(255,117,31,0.18);
}
.tech-pill .dot-tech {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  box-shadow: 0 0 8px rgba(255,117,31,0.6);
  flex-shrink: 0;
}

/* ============================================================
   TRUST STRIP
   ============================================================ */
.trust {
  max-width: 1250px;
  margin: 4rem auto;
  padding: 3rem;
  background:
    radial-gradient(circle at 80% 20%, rgba(255,117,31,0.15), transparent 50%),
    linear-gradient(135deg, var(--orange-50) 0%, #FFEEDD 100%);
  border-radius: 30px;
  border: 1px solid var(--orange-200);
  display: flex;
  align-items: center;
  gap: 2.5rem;
  flex-wrap: wrap;
  position: relative;
  overflow: hidden;
}
.trust::before {
  content: '';
  position: absolute;
  top: -80px; right: -80px;
  width: 320px; height: 320px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,117,31,0.18), transparent 70%);
  pointer-events: none;
  animation: floatSmall 6s ease-in-out infinite;
}
.trust-icon {
  width: 80px; height: 80px;
  border-radius: 22px;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  box-shadow: 0 15px 40px rgba(255,117,31,0.25);
  flex-shrink: 0;
  position: relative;
  z-index: 1;
  transition: transform 0.4s var(--spring-bounce);
}
.trust:hover .trust-icon { transform: rotate(-8deg) scale(1.08); }
.trust-content {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 260px;
}
.trust-content h4 {
  color: var(--ink-800);
  font-size: 1.4rem;
  font-weight: 900;
  letter-spacing: -0.5px;
  margin: 0 0 0.5rem 0;
}
.trust-content p {
  color: #78350f;
  font-size: 1rem;
  margin: 0;
  line-height: 1.65;
}

/* ============================================================
   FINAL CTA
   ============================================================ */
.final-cta {
  text-align: center;
  padding: 6rem 2rem;
  background: radial-gradient(ellipse at center, var(--orange-50) 0%, #ffffff 70%);
  position: relative;
  overflow: hidden;
}
.final-cta::before {
  content: '';
  position: absolute;
  top: 0; left: 50%;
  transform: translateX(-50%);
  width: 800px; height: 400px;
  background: radial-gradient(circle, rgba(255,117,31,0.15), transparent 70%);
  filter: blur(60px);
  pointer-events: none;
  animation: orbFloat1 15s ease-in-out infinite;
}
.final-cta h2 {
  position: relative;
  font-size: clamp(2rem, 5vw, 3.75rem);
  font-weight: 900;
  color: var(--ink-800);
  letter-spacing: -0.045em;
  margin: 0 0 1rem 0;
  line-height: 1;
}
.final-cta p {
  position: relative;
  color: var(--ink-500);
  font-size: 1.15rem;
  margin: 0 0 2.5rem 0;
  font-weight: 500;
}

/* ============================================================
   FOOTER
   ============================================================ */
.site-footer {
  background:
    radial-gradient(ellipse at top, rgba(255,117,31,0.08), transparent 50%),
    #0a0a0a;
  color: rgba(255,255,255,0.6);
  padding: 4rem 3.5rem 2rem 3.5rem;
  position: relative;
  overflow: hidden;
}
.footer-grid {
  position: relative;
  display: grid;
  grid-template-columns: 1.6fr 1fr 1fr 1fr;
  gap: 3rem;
  max-width: 1280px;
  margin: 0 auto 3rem auto;
}
.footer-brand {
  font-size: 1.6rem;
  font-weight: 900;
  font-style: italic;
  color: white;
  letter-spacing: -1px;
  margin-bottom: 1rem;
}
.footer-brand span { color: var(--orange-500); }
.footer-desc {
  font-size: 0.9rem;
  line-height: 1.7;
  max-width: 320px;
  margin-bottom: 1.5rem;
}
.footer-col h5 {
  color: white;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 2px;
  text-transform: uppercase;
  margin: 0 0 1.25rem 0;
}
.footer-col ul { list-style: none; padding: 0; margin: 0; }
.footer-col ul li { margin-bottom: 0.7rem; }
.footer-col ul a {
  color: rgba(255,255,255,0.6);
  text-decoration: none;
  font-size: 0.9rem;
  transition: color 0.25s, padding-left 0.25s;
  display: inline-block;
}
.footer-col ul a:hover { color: var(--orange-500); padding-left: 6px; }
.socials { display: flex; gap: 10px; }
.social-btn {
  width: 40px; height: 40px;
  border-radius: 11px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white !important;
  text-decoration: none;
  font-weight: 700;
  font-size: 13px;
  transition: all 0.3s var(--spring-bounce);
}
.social-btn:hover {
  background: linear-gradient(135deg, var(--orange-500), var(--orange-600));
  border-color: var(--orange-500);
  transform: translateY(-4px);
  box-shadow: 0 10px 25px rgba(255,117,31,0.35);
}
.footer-bottom {
  position: relative;
  max-width: 1280px;
  margin: 0 auto;
  padding-top: 2rem;
  border-top: 1px solid rgba(255,255,255,0.08);
  display: flex;
  justify-content: space-between;
  font-size: 0.83rem;
  flex-wrap: wrap;
  gap: 1rem;
}

/* ============================================================
   RESPONSIVE
   ============================================================ */
@media (max-width: 1200px) {
  .topnav { padding: 0 2rem; }
  .nav-links { gap: 0.25rem; }
  .nav-links a { padding: 8px 10px; font-size: 13px; }
}

@media (max-width: 1024px) {
  .nav-links { display: none; }
  .live-pill { display: none; }
  .topnav { padding: 0 1.5rem; }
  .hero-inner { gap: 3rem; }
  .bento-grid { grid-template-columns: repeat(4, 1fr); }
  .bento-wide { grid-column: span 2; }
}

@media (max-width: 900px) {
  .hero { padding: 8rem 1.75rem 5rem 1.75rem; }
  .hero-inner { grid-template-columns: 1fr; gap: 2rem; }
  .hero-visual { display: none; }
  .hero-title { margin-bottom: 1.25rem; }
  .hero-subtitle { margin-bottom: 2rem; }
  .hero-cta, .hero-cta-secondary { padding: 14px 24px; font-size: 13px; }
  .hero-trust { gap: 1rem; font-size: 10.5px; }
  
  .section { padding: 4rem 1.75rem; }
  .how-wrap { padding: 4rem 1.75rem; }
  .how-grid { grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .how-grid::before { display: none; }
  .how-step .num { width: 62px; height: 62px; font-size: 20px; }
  
  .stats-band { padding: 3rem 1.5rem; border-radius: 26px; margin: 2rem 1.25rem; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 1rem; }
  .stat-block { border-right: none; padding: 1rem 0.5rem; }
  .stat-block:nth-child(1), .stat-block:nth-child(2) {
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding-bottom: 1.5rem;
  }
  .stat-block:nth-child(3), .stat-block:nth-child(4) { padding-top: 1.5rem; }
  
  .bento-grid { grid-template-columns: repeat(2, 1fr); grid-auto-rows: auto; gap: 1rem; }
  .bento-tall, .bento-wide, .bento-span-2x1 { grid-column: span 2; grid-row: span 1; }
  .bento-tall { min-height: 220px; }
  .bento-card { padding: 1.5rem 1.25rem; }
  
  .escrow-flow { flex-direction: column; padding: 2rem 1.5rem; }
  .escrow-step { min-width: 100%; padding: 1.5rem 1rem; }
  .escrow-step:not(:last-child)::after { display: none; }
  .escrow-step:not(:last-child) {
    border-bottom: 1px dashed var(--orange-100);
    padding-bottom: 2rem;
    margin-bottom: 1rem;
  }
  
  .modes-grid { grid-template-columns: 1fr; gap: 1.5rem; }
  .mode-card { padding: 2rem 1.75rem; }
  
  .download-band {
    padding: 3rem 2rem;
    border-radius: 26px;
    flex-direction: column;
    text-align: center;
    margin: 2rem 1.25rem;
  }
  
  .marquee-item { font-size: 16px; padding: 0 1.5rem; }
  .marquee-item span { font-size: 11px; }
  
  .trust { padding: 2rem 1.75rem; gap: 1.5rem; margin: 3rem 1.25rem; border-radius: 24px; }
  .trust-icon { width: 64px; height: 64px; font-size: 32px; }
  .trust-content h4 { font-size: 1.15rem; }
  
  .footer-grid { grid-template-columns: 1fr 1fr; gap: 2rem; }
  .site-footer { padding: 3rem 1.75rem 1.5rem; }
  .footer-bottom { flex-direction: column; text-align: center; }
}

@media (max-width: 640px) {
  .topnav { padding: 0 1rem; height: 62px; }
  .brand { font-size: 16px; gap: 8px; }
  .brand .brand-logo { width: 28px; height: 28px; }
  .nav-signup { padding: 9px 14px; font-size: 11px; }
  
  .hero { padding: 6.5rem 1.25rem 3.5rem 1.25rem; }
  .hero-eyebrow { font-size: 9.5px; letter-spacing: 1.8px; padding: 7px 13px; }
  .hero-title { font-size: clamp(2.1rem, 11vw, 2.85rem); }
  .hero-subtitle { font-size: 0.95rem; }
  .hero-cta-row { flex-direction: column; align-items: stretch; gap: 0.75rem; }
  .hero-cta, .hero-cta-secondary {
    width: 100%;
    justify-content: center;
    padding: 14px 20px;
    font-size: 12.5px;
  }
  .hero-trust { gap: 0.75rem; font-size: 9.5px; letter-spacing: 0.8px; }
  
  .section { padding: 3rem 1.25rem; }
  .section-title { font-size: clamp(1.7rem, 7.5vw, 2.2rem); }
  .section-subtitle { font-size: 0.93rem; }
  
  .feature-card { padding: 2rem 1.5rem; border-radius: 20px; min-height: auto; }
  .feature-icon-box { width: 56px; height: 56px; }
  .feature-card h3 { font-size: 1.4rem; }
  
  .how-wrap { padding: 3rem 1.25rem; }
  .how-grid { grid-template-columns: 1fr; gap: 2rem; margin-top: 2.5rem; }
  .how-step .num { width: 56px; height: 56px; font-size: 18px; }
  .how-step h3 { font-size: 1.05rem; }
  
  .stats-band { margin: 2rem 0.75rem; padding: 2.5rem 1.25rem; border-radius: 22px; }
  .stats-grid { grid-template-columns: 1fr; gap: 0; }
  .stat-block {
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding: 1.25rem 0.5rem;
    border-right: none !important;
  }
  .stat-block:last-child { border-bottom: none; }
  .stat-block .num { font-size: 2.2rem; }
  .stat-block .label { font-size: 10px; letter-spacing: 1.6px; }
  
  .bento-grid { grid-template-columns: 1fr; gap: 1rem; }
  .bento-tall, .bento-wide, .bento-span-2x1 { grid-column: span 1; grid-row: span 1; }
  .bento-tall { min-height: auto; }
  .bento-card { padding: 1.5rem 1.25rem; border-radius: 18px; }
  
  .escrow-flow { padding: 1.75rem 1.25rem; border-radius: 20px; }
  .escrow-step { padding: 1rem 0.5rem; }
  .escrow-step .step-num { width: 46px; height: 46px; font-size: 17px; }
  .escrow-step h4 { font-size: 0.93rem; }
  .escrow-step p { font-size: 0.78rem; }
  
  .modes-grid { gap: 1rem; }
  .mode-card { padding: 1.75rem 1.5rem; border-radius: 20px; }
  .mode-card h3 { font-size: 1.45rem; }
  .mode-card p, .mode-card ul li { font-size: 0.83rem; }
  
  .download-band { padding: 2.5rem 1.5rem; margin: 2rem 0.75rem; border-radius: 22px; }
  .download-band h3 { font-size: 1.35rem; }
  .download-band p { font-size: 0.88rem; }
  .download-btn { padding: 14px 24px; font-size: 12.5px; }
  
  .tech-strip { gap: 8px; margin-top: 2rem; }
  .tech-pill { padding: 10px 14px; font-size: 11.5px; gap: 7px; }
  
  .trust {
    padding: 1.75rem 1.25rem;
    margin: 2.5rem 0.75rem;
    border-radius: 20px;
    flex-direction: column;
    text-align: center;
  }
  .trust-icon { width: 56px; height: 56px; font-size: 28px; border-radius: 16px; }
  .trust-content h4 { font-size: 1.1rem; }
  .trust-content p { font-size: 0.9rem; }
  
  .final-cta { padding: 4rem 1.25rem; }
  .final-cta h2 { font-size: clamp(1.75rem, 8vw, 2.4rem); }
  .final-cta p { font-size: 1rem; margin-bottom: 2rem; }
  
  .marquee-item { font-size: 14px; padding: 0 1rem; }
  .marquee-item span { font-size: 10px; letter-spacing: 1.5px; }
  
  .site-footer { padding: 2.5rem 1.25rem 1.25rem; }
  .footer-grid { grid-template-columns: 1fr; gap: 2rem; }
  .footer-brand { font-size: 1.4rem; }
  .footer-bottom { font-size: 0.77rem; gap: 0.5rem; }
}

@media (max-width: 380px) {
  .brand .brand-text { font-size: 14px; }
  .nav-signup { padding: 8px 11px; font-size: 10px; }
  .hero { padding: 6rem 1rem 3rem 1rem; }
  .hero-title { font-size: 2rem; }
  .section { padding: 2.5rem 1rem; }
}

/* Button label responsive swap */
@media (max-width: 520px) {
  .nav-signup .btn-label-full {
    font-size: 0;
  }
  .nav-signup .btn-label-full::before {
    content: 'Get App';
    font-size: 11px;
  }
}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 5. NAVBAR
# ==========================================
logo_html = icon_img("logo", 28, "📦")

nav_html = (
    '<nav class="topnav">'
    '<a href="#top" class="brand">'
    f'<span class="brand-logo">{logo_html}</span>'
    '<span class="brand-text">Pack-<span class="n">N</span>-Ship</span>'
    '</a>'
    '<div class="nav-links">'
    '<a href="#features"><span class="nav-num">01</span> Who It\'s For</a>'
    '<a href="#how"><span class="nav-num">02</span> How It Works</a>'
    '<a href="#security"><span class="nav-num">03</span> Security</a>'
    '<a href="#download"><span class="nav-num">04</span> Download</a>'
    '</div>'
    '<div class="nav-actions">'
    '<span class="live-pill"><span class="live-dot"></span> Live</span>'
    f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="nav-signup">'
    '<span class="btn-label-full">Download App</span>'
    '<span class="btn-arrow">→</span>'
    '</a>'
    '</div>'
    '</nav>'
)
st.markdown(nav_html, unsafe_allow_html=True)

# ==========================================
# 6. HERO
# ==========================================
particles = "".join(['<div class="particle"></div>' for _ in range(12)])

hero_html = (
    '<section class="hero" id="top">'
    '<div class="hero-orb-1"></div>'
    '<div class="hero-orb-2"></div>'
    '<div class="hero-orb-3"></div>'
    f'<div class="particles">{particles}</div>'
    '<div class="hero-inner">'
    '<div class="fade-up">'
    '<div class="hero-eyebrow"><span class="dot"></span> Peer-to-Peer Micro-Move Logistics</div>'
    '<h1 class="hero-title">Move Smarter.<br><span class="gradient">Pay Less.</span></h1>'
    '<p class="hero-subtitle">Skip the expensive van rentals. Pack-N-Ship connects you with everyday commuters already driving your route — for micro-moves of 1 to 3 boxes, secured by blockchain escrow and algorithmic route matching.</p>'
    '<div class="hero-cta-row">'
    f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="hero-cta">Download App →</a>'
    '<a href="#features" class="hero-cta-secondary">▶ See How It Works</a>'
    '</div>'
    '<div class="hero-trust">'
    '<span class="badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> No Setup Fees</span>'
    '<span class="badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> Smart-Contract Escrow</span>'
    '<span class="badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> QR + PIN Verified</span>'
    '</div>'
    '</div>'
    '<div class="hero-visual fade-up stagger-2">'
    '<div class="phone-orbit-2"></div>'
    '<div class="phone-orbit"></div>'
    '<div class="float-chip left"><div class="chip-icon">⚡</div><div>Matched in 30s</div></div>'
    '<div class="float-chip right"><div class="chip-icon">🔒</div><div>Escrow Secured</div></div>'
    '<div class="phone-mockup">'
    '<div class="phone-notch"></div>'
    '<div class="phone-screen">'
    '<div class="mini-card accent"><div class="label">Active Delivery</div><div class="value">On the way →</div></div>'
    '<div class="mini-card"><div class="label">Est. Arrival</div><div class="value orange">12 min</div></div>'
    '<div class="mini-card"><div class="label">Escrow Status</div><div class="value">🔒 On Hold</div></div>'
    '<div class="mini-card"><div class="label">Tracking</div><div class="value"><span class="live-dot"></span>Live GPS<div class="waveform"><span></span><span></span><span></span><span></span><span></span></div></div></div>'
    '<div style="margin-top:auto; padding:12px; background:rgba(255,255,255,0.06); border-radius:12px; text-align:center; border:1px solid rgba(255,255,255,0.08);">'
    '<div style="font-size:10px; color:rgba(255,255,255,0.5); font-weight:800; letter-spacing:2px;">PACK-N-SHIP</div>'
    '</div>'
    '</div>'
    '</div>'
    '</div>'
    '</div>'
    '</section>'
)
st.markdown(hero_html, unsafe_allow_html=True)

# ==========================================
# 7. MARQUEE
# ==========================================
marquee_html = (
    '<div class="marquee-wrap">'
    '<p class="marquee-label">Built for the Cebu urban corridor — CTU Main Campus Capstone 2026</p>'
    '<div class="marquee">'
    '<div class="marquee-item">● CEBO<span>COMMUTERS</span></div>'
    '<div class="marquee-item">◆ IT PARK<span>TO AYALA</span></div>'
    '<div class="marquee-item">▲ SM CITY<span>TO COLON</span></div>'
    '<div class="marquee-item">■ TALAMBAN<span>TO DOWNTOWN</span></div>'
    '<div class="marquee-item">✦ LABANGON<span>TO MANDAUE</span></div>'
    '<div class="marquee-item">● CEBO<span>COMMUTERS</span></div>'
    '<div class="marquee-item">◆ IT PARK<span>TO AYALA</span></div>'
    '<div class="marquee-item">▲ SM CITY<span>TO COLON</span></div>'
    '<div class="marquee-item">■ TALAMBAN<span>TO DOWNTOWN</span></div>'
    '<div class="marquee-item">✦ LABANGON<span>TO MANDAUE</span></div>'
    '</div>'
    '</div>'
)
st.markdown(marquee_html, unsafe_allow_html=True)

# ==========================================
# 8. FEATURES HEADER
# ==========================================
features_header = (
    '<section class="section text-center" id="features">'
    '<span class="section-eyebrow">Built for Every Need</span>'
    '<h2 class="section-title">One platform. Three communities.</h2>'
    '<p class="section-subtitle">Whether you\'re sending a package, driving your daily route, or keeping the ecosystem safe — Pack-N-Ship is designed around you.</p>'
    '</section>'
)
st.markdown(features_header, unsafe_allow_html=True)

# ==========================================
# 9. FEATURE CARDS
# ==========================================
f1, f2, f3 = st.columns(3)

with f1:
    card = (
        '<div class="feature-card fade-up stagger-1">'
        f'<div class="feature-icon-box">{icon_img("personal", 30, "📦")}</div>'
        '<h3>For Senders</h3>'
        '<p>Students, low-income earners, and small online sellers moving 1–3 boxes. Book micro-moves at a fraction of van rental cost — with curb-side or door-to-door options.</p>'
        f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="feature-link">Send a Package →</a>'
        '</div>'
    )
    st.markdown(card, unsafe_allow_html=True)

with f2:
    card = (
        '<div class="feature-card fade-up stagger-2">'
        f'<div class="feature-icon-box">{icon_img("driver", 30, "🚗")}</div>'
        '<h3>For Providers</h3>'
        '<p>Private vehicle owners already driving Cebu\'s corridors. Post your route, accept matched deliveries, and offset fuel and toll costs — with blockchain-secured payouts to GCash or bank.</p>'
        f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="feature-link">Become a Provider →</a>'
        '</div>'
    )
    st.markdown(card, unsafe_allow_html=True)

with f3:
    card = (
        '<div class="feature-card fade-up stagger-3">'
        f'<div class="feature-icon-box">{icon_img("business", 30, "🛡️")}</div>'
        '<h3>For Trust</h3>'
        '<p>Multi-tier verification (ID, liveness selfie, OR/CR), smart-contract escrow, and immutable on-chain proofs of pickup, drop-off, and payment — anchored on blockchain.</p>'
        f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="feature-link">See the Security Layer →</a>'
        '</div>'
    )
    st.markdown(card, unsafe_allow_html=True)

# ==========================================
# 10. HOW IT WORKS
# ==========================================
how_html = (
    '<section class="how-wrap" id="how">'
    '<div class="section text-center" style="padding:0;">'
    '<span class="section-eyebrow">How It Works</span>'
    '<h2 class="section-title">From booking to handoff — in four steps.</h2>'
    '<p class="section-subtitle">Algorithmic route matching pairs every request with a provider whose existing daily path overlaps your delivery.</p>'
    '</div>'
    '<div class="how-grid">'
    '<div class="how-step fade-up stagger-1"><div class="num">1</div><h3>Book a Micro-Move</h3><p>Set pickup and drop-off, choose curb-side or door-to-door, describe your 1–3 boxes, and schedule now or later.</p></div>'
    '<div class="how-step fade-up stagger-2"><div class="num">2</div><h3>Get Route-Matched</h3><p>Our algorithm scans active provider routes and surfaces the best overlap — you see matched providers, ratings, and ETA.</p></div>'
    '<div class="how-step fade-up stagger-3"><div class="num">3</div><h3>QR / PIN Handoff</h3><p>At pickup and drop-off, both sides verify with a QR scan or a 4–6 digit PIN. Proofs are anchored on-chain.</p></div>'
    '<div class="how-step fade-up stagger-4"><div class="num">4</div><h3>Escrow Auto-Releases</h3><p>Funds were held safely in smart-contract escrow. Once drop-off is verified, payment releases automatically to the provider.</p></div>'
    '</div>'
    '</section>'
)
st.markdown(how_html, unsafe_allow_html=True)

# ==========================================
# 11. STATS BAND
# ==========================================
stats_html = (
    '<div class="stats-band">'
    '<div class="stats-grid">'
    '<div class="stat-block fade-up stagger-1"><div class="num">1–3</div><p class="label">Boxes per Micro-Move</p></div>'
    '<div class="stat-block fade-up stagger-2"><div class="num">₱0</div><p class="label">Setup &amp; Subscription Fees</p></div>'
    '<div class="stat-block fade-up stagger-3"><div class="num">2</div><p class="label">Layers of Provider Verification</p></div>'
    '<div class="stat-block fade-up stagger-4"><div class="num">100%</div><p class="label">Blockchain-Anchored Proofs</p></div>'
    '</div>'
    '</div>'
)
st.markdown(stats_html, unsafe_allow_html=True)

# ==========================================
# 12. BENTO — VERIFICATION
# ==========================================
verify_header = (
    '<section class="section text-center" id="verification" style="padding-bottom:1rem;">'
    '<span class="section-eyebrow">Multi-Tier Verification</span>'
    '<h2 class="section-title">Only real people. Real vehicles.</h2>'
    '<p class="section-subtitle">Every provider passes through a four-gate verification process before they can accept a single delivery.</p>'
    '</section>'
)
st.markdown(verify_header, unsafe_allow_html=True)

bento_html = (
    '<div style="max-width:1300px;margin:0 auto;padding:0 3.5rem;">'
    '<div class="bento-grid">'
    '<div class="bento-card bento-tall fade-up stagger-1" style="justify-content:center;align-items:flex-start;background:linear-gradient(160deg, #fff7ed, #ffffff);">'
    '<div class="bento-icon" style="width:58px;height:58px;font-size:26px;">🪪</div>'
    '<h4 style="font-size:1.15rem;">Valid Driver\'s License</h4>'
    '<p style="font-size:0.87rem;">Uploaded and manually reviewed by admin against LTO records before approval. Every provider is a real, licensed driver.</p>'
    '<div style="margin-top:auto;padding-top:1rem;display:flex;gap:6px;">'
    '<span style="padding:4px 10px;background:var(--orange-50);color:var(--orange-500);border-radius:999px;font-size:10px;font-weight:800;letter-spacing:1px;">LTO VERIFIED</span>'
    '</div>'
    '</div>'
    '<div class="bento-card bento-span-2x1 fade-up stagger-2">'
    '<div class="bento-icon">🤳</div>'
    '<h4>Liveness Selfie Check</h4>'
    '<p>A live selfie matched against the submitted ID to prevent impersonation and fraud.</p>'
    '</div>'
    '<div class="bento-card bento-span-2x1 fade-up stagger-3">'
    '<div class="bento-icon">📄</div>'
    '<h4>Vehicle OR / CR</h4>'
    '<p>Official Receipt and Certificate of Registration validated for every vehicle on the platform.</p>'
    '</div>'
    '<div class="bento-card bento-wide fade-up stagger-4" style="background:linear-gradient(135deg, #111827, #1f2937);color:white;border-color:transparent;">'
    '<div class="bento-icon" style="background:rgba(255,117,31,0.2);">⛓️</div>'
    '<h4 style="color:white;">On-Chain Approval Anchoring</h4>'
    '<p style="color:rgba(255,255,255,0.75);">Verification approvals are anchored on blockchain — tamper-proof, auditable, and permanent.</p>'
    '</div>'
    '<div class="bento-card bento-wide fade-up stagger-5" style="background:linear-gradient(135deg, #fff7ed, #FFEEDD);border-color:var(--orange-200);">'
    '<div class="bento-icon" style="background:white;">👤</div>'
    '<h4>Single Account Enforcement</h4>'
    '<p>One active account per individual. Duplicate identities are automatically flagged and blocked.</p>'
    '</div>'
    '</div>'
    '</div>'
)
st.markdown(bento_html, unsafe_allow_html=True)

# ==========================================
# 13. ESCROW FLOW
# ==========================================
escrow_header = (
    '<section class="section text-center" id="security" style="padding-bottom:1rem;">'
    '<span class="section-eyebrow">Smart-Contract Escrow</span>'
    '<h2 class="section-title">Money moves only when the box does.</h2>'
    '<p class="section-subtitle">No manual fund release. No disputes over "did it arrive?" The smart contract enforces it.</p>'
    '</section>'
)
st.markdown(escrow_header, unsafe_allow_html=True)

escrow_flow = (
    '<div style="max-width:1200px;margin:0 auto;padding:0 3.5rem;">'
    '<div class="escrow-flow">'
    '<div class="escrow-step fade-up stagger-1"><div class="step-num">1</div><h4>Sender Pays</h4><p>Payment is captured at booking and locked into smart-contract escrow.</p></div>'
    '<div class="escrow-step fade-up stagger-2"><div class="step-num">2</div><h4>Pickup Verified</h4><p>Provider scans the pickup QR or enters the PIN. Proof anchored on-chain.</p></div>'
    '<div class="escrow-step fade-up stagger-3"><div class="step-num">3</div><h4>Drop-off Verified</h4><p>Receiver scans the drop-off QR or enters the PIN. Second proof completes the handoff.</p></div>'
    '<div class="escrow-step fade-up stagger-4"><div class="step-num">4</div><h4>Auto-Release</h4><p>Smart contract detects both proofs and releases funds to the provider — instantly.</p></div>'
    '</div>'
    '</div>'
)
st.markdown(escrow_flow, unsafe_allow_html=True)

# ==========================================
# 14. DELIVERY MODES
# ==========================================
modes_header = (
    '<section class="section text-center" id="modes" style="padding-bottom:1rem;">'
    '<span class="section-eyebrow">Two Ways to Move</span>'
    '<h2 class="section-title">Pay only for the convenience you need.</h2>'
    '</section>'
)
st.markdown(modes_header, unsafe_allow_html=True)

modes_grid = (
    '<div style="max-width:1200px;margin:0 auto;padding:0 3.5rem;">'
    '<div class="modes-grid">'
    '<div class="mode-card fade-up stagger-1">'
    '<span class="mode-tag orange">Most Affordable</span>'
    '<h3>Curb-side</h3>'
    '<p>Meet the provider at an agreed roadside or accessible pickup point. The fastest, cheapest option.</p>'
    '<ul><li>Lower service fee</li><li>Quicker loading time</li><li>Perfect for 1–3 boxes</li><li>Agreed landmark pickup</li></ul>'
    '</div>'
    '<div class="mode-card fade-up stagger-2">'
    '<span class="mode-tag dark">Most Convenient</span>'
    '<h3>Door-to-Door</h3>'
    '<p>The provider collects and delivers directly from and to your specified indoor location.</p>'
    '<ul><li>Full-service pickup &amp; drop-off</li><li>In-app chat for gate access</li><li>Ideal for gifts &amp; electronics</li><li>Insured handoff at both ends</li></ul>'
    '</div>'
    '</div>'
    '</div>'
)
st.markdown(modes_grid, unsafe_allow_html=True)

# ==========================================
# 15. DOWNLOAD BAND
# ==========================================
download_html = (
    '<div class="download-band" id="download">'
    '<div class="download-left">'
    '<h3>📱 Get the Pack-N-Ship App</h3>'
    '<p>Available for Android 4.0.3 and above. Download the APK and start sending or earning in minutes.</p>'
    '</div>'
    f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="download-btn">'
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15v-4H8l4-4 4 4h-3v4h-2z"/></svg>'
    'Download APK'
    '</a>'
    '</div>'
)
st.markdown(download_html, unsafe_allow_html=True)

# ==========================================
# 16. TECH STRIP
# ==========================================
tech_header = (
    '<section class="section text-center" id="stack" style="padding-bottom:0;">'
    '<span class="section-eyebrow">Built With</span>'
    '<h2 class="section-title">Modern stack. Real infrastructure.</h2>'
    '</section>'
)
st.markdown(tech_header, unsafe_allow_html=True)

tech_strip = (
    '<div style="max-width:1200px;margin:0 auto;padding:0 3.5rem 2rem 3.5rem;">'
    '<div class="tech-strip">'
    '<span class="tech-pill"><span class="dot-tech"></span>React Native + Expo</span>'
    '<span class="tech-pill"><span class="dot-tech"></span>Django + Python</span>'
    '<span class="tech-pill"><span class="dot-tech"></span>Supabase</span>'
    '<span class="tech-pill"><span class="dot-tech"></span>PayMongo</span>'
    '<span class="tech-pill"><span class="dot-tech"></span>Google Maps</span>'
    '<span class="tech-pill"><span class="dot-tech"></span>Smart Contracts</span>'
    '<span class="tech-pill"><span class="dot-tech"></span>On-Chain Proofs</span>'
    '</div>'
    '</div>'
)
st.markdown(tech_strip, unsafe_allow_html=True)

# ==========================================
# 17. TRUST
# ==========================================
trust_html = (
    '<div class="trust">'
    '<div class="trust-icon">🔒</div>'
    '<div class="trust-content">'
    '<h4>Blockchain-Secured Escrow — Auditable by Anyone</h4>'
    '<p>Every transaction, pickup, drop-off, verification approval, and rating is anchored on-chain. Admin can audit immutable proofs at any time.</p>'
    '</div>'
    '</div>'
)
st.markdown(trust_html, unsafe_allow_html=True)

# ==========================================
# 18. FINAL CTA
# ==========================================
final_cta = (
    '<section class="final-cta" id="cta">'
    '<h2>Ready to move faster?</h2>'
    '<p>Join the Cebu community already using Pack-N-Ship to send smarter and earn on the road.</p>'
    f'<a href="{APK_DOWNLOAD_LINK}" target="_blank" rel="noopener" class="hero-cta">Download the App →</a>'
    '</section>'
)
st.markdown(final_cta, unsafe_allow_html=True)

# ==========================================
# 19. FOOTER
# ==========================================
footer_html = (
    '<div class="site-footer">'
    '<div class="footer-grid">'
    '<div>'
    '<div class="footer-brand">Pack-<span>N</span>-Ship</div>'
    '<p class="footer-desc">A Peer-to-Peer Express Logistics and Moving Services Platform. Built for the Cebu urban corridor — blockchain-secured, real-time, and community-driven.</p>'
    '<div class="socials">'
    '<a href="#" class="social-btn">f</a>'
    '<a href="#" class="social-btn">𝕏</a>'
    '<a href="#" class="social-btn">in</a>'
    '<a href="#" class="social-btn">IG</a>'
    '</div>'
    '</div>'
    '<div class="footer-col"><h5>Product</h5><ul>'
    '<li><a href="#features">Who It\'s For</a></li>'
    '<li><a href="#how">How It Works</a></li>'
    '<li><a href="#security">Escrow &amp; Security</a></li>'
    '<li><a href="#download">Download App</a></li>'
    '</ul></div>'
    '<div class="footer-col"><h5>Project</h5><ul>'
    '<li><a href="#">Capstone Manuscript</a></li>'
    '<li><a href="#">Comparative Matrix</a></li>'
    '<li><a href="#">ER Diagram</a></li>'
    '<li><a href="#">Module Assignments</a></li>'
    '</ul></div>'
    '<div class="footer-col"><h5>Researchers</h5><ul>'
    '<li><a href="#">K. Otida</a></li>'
    '<li><a href="#">M. Padriga</a></li>'
    '<li><a href="#">J. J. Pestano</a></li>'
    '<li><a href="#">R. J. Lumindas</a></li>'
    '</ul></div>'
    '</div>'
    '<div class="footer-bottom">'
    '<span>© 2026 Pack-N-Ship · Cebu Technological University — Main Campus</span>'
    '<span>Adviser: Bell S. Campanilla, PhD · Made with ❤️ in the Philippines</span>'
    '</div>'
    '</div>'
)
st.markdown(footer_html, unsafe_allow_html=True)