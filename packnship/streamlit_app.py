import streamlit as st
import base64
import os

# ==========================================
# 1. PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="Pack-N-Ship · Enterprise Logistics",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# ⭐ YOUR APK DOWNLOAD LINK
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

def icon_img(key, size=48, fallback="✨"):
    b64 = ICONS.get(key)
    if b64:
        return f'<img src="data:image/png;base64,{b64}" style="width:{size}px;height:{size}px;object-fit:contain;" />'
    return f'<span style="font-size:{size}px;">{fallback}</span>'

# ==========================================
# 3. CUSTOM CSS
# ==========================================
css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; background: #ffffff; }
html { scroll-behavior: smooth; }

/* ---------- KEYFRAMES ---------- */
@keyframes fadeUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideInRight { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }
@keyframes slideInLeft { from { opacity: 0; transform: translateX(-40px); } to { opacity: 1; transform: translateX(0); } }
@keyframes float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-14px); } }
@keyframes floatSmall { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
@keyframes orbFloat1 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(-50px,40px) scale(1.15); } }
@keyframes orbFloat2 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(60px,-30px) scale(1.1); } }
@keyframes pulseRing { 0% { box-shadow: 0 0 0 0 rgba(255,117,31,0.7); } 70% { box-shadow: 0 0 0 12px rgba(255,117,31,0); } 100% { box-shadow: 0 0 0 0 rgba(255,117,31,0); } }
@keyframes marqueeScroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
@keyframes shimmer { 0% { transform: translateX(-100%) skewX(-20deg); } 100% { transform: translateX(300%) skewX(-20deg); } }
@keyframes gradientPan { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@keyframes spinSlow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes borderSpin {
  0% { background-position: 0% 50%; }
  100% { background-position: 200% 50%; }
}
@keyframes glowPulse {
  0%,100% { box-shadow: 0 0 30px rgba(255,117,31,0.35); }
  50% { box-shadow: 0 0 60px rgba(255,117,31,0.6); }
}

.fade-up     { animation: fadeUp 0.9s cubic-bezier(.22,1,.36,1) both; }
.fade-in     { animation: fadeIn 1.2s ease both; }
.slide-right { animation: slideInRight 1s cubic-bezier(.22,1,.36,1) both; }
.slide-left  { animation: slideInLeft 1s cubic-bezier(.22,1,.36,1) both; }
.stagger-1 { animation-delay: 0.1s; }
.stagger-2 { animation-delay: 0.25s; }
.stagger-3 { animation-delay: 0.4s; }
.stagger-4 { animation-delay: 0.55s; }
.stagger-5 { animation-delay: 0.7s; }

/* ---------- TOP NAV ---------- */
.topnav {
  position: sticky; top: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 3.5rem;
  background: rgba(255,255,255,0.88);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(0,0,0,0.05);
}
.brand { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 900; font-style: italic; letter-spacing: -1px; color: #111827; }
.brand span { color: #FF751F; }
.nav-links { display: flex; gap: 2.25rem; font-size: 14px; font-weight: 600; color: #4b5563; }
.nav-links a { color: #4b5563; text-decoration: none; transition: color 0.25s; position: relative; }
.nav-links a::after { content: ''; position: absolute; bottom: -6px; left: 0; width: 0; height: 2px; background: #FF751F; transition: width 0.3s; }
.nav-links a:hover { color: #FF751F; }
.nav-links a:hover::after { width: 100%; }
.nav-actions { display: flex; align-items: center; gap: 14px; }
.nav-login { color: #4b5563; font-size: 14px; font-weight: 700; text-decoration: none; }
.nav-login:hover { color: #FF751F; }
.nav-signup {
  background: linear-gradient(90deg,#FF751F,#E4650F);
  color: white !important; padding: 10px 22px; border-radius: 10px;
  font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;
  text-decoration: none; box-shadow: 0 4px 14px rgba(255,117,31,0.35);
  transition: transform 0.2s, box-shadow 0.2s;
}
.nav-signup:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(255,117,31,0.5); }

/* ---------- HERO ---------- */
.hero {
  position: relative;
  background: linear-gradient(135deg, #0a0a0a 0%, #1a0e00 30%, #3d1f00 60%, #FF751F 130%);
  padding: 6rem 3.5rem 8rem 3.5rem;
  overflow: hidden;
}
.hero::before {
  content: ''; position: absolute; inset: 0;
  background-image: radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px);
  background-size: 32px 32px; pointer-events: none;
}
.hero-orb-1 { position: absolute; top: -200px; right: -150px; width: 700px; height: 700px; border-radius: 50%; background: radial-gradient(circle, rgba(255,117,31,0.55) 0%, transparent 65%); filter: blur(60px); animation: orbFloat1 22s ease-in-out infinite; pointer-events: none; }
.hero-orb-2 { position: absolute; bottom: -250px; left: -200px; width: 600px; height: 600px; border-radius: 50%; background: radial-gradient(circle, rgba(255,180,80,0.35) 0%, transparent 65%); filter: blur(60px); animation: orbFloat2 26s ease-in-out infinite; pointer-events: none; }

.hero-inner { position: relative; z-index: 2; display: grid; grid-template-columns: 1.15fr 1fr; gap: 4rem; align-items: center; max-width: 1400px; margin: 0 auto; }

.hero-eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 16px;
  background: rgba(255,117,31,0.12);
  border: 1px solid rgba(255,117,31,0.4);
  border-radius: 999px;
  color: #FF751F; font-size: 11px; font-weight: 800; letter-spacing: 2.5px; text-transform: uppercase;
  margin-bottom: 1.75rem;
  position: relative;
}
.hero-eyebrow::before {
  content: ''; position: absolute; inset: -2px; border-radius: 999px;
  background: linear-gradient(90deg, transparent, rgba(255,117,31,0.6), transparent);
  background-size: 200% 100%; animation: borderSpin 3s linear infinite;
  z-index: -1; filter: blur(6px);
}
.hero-eyebrow .dot { width: 8px; height: 8px; border-radius: 50%; background: #FF751F; animation: pulseRing 2s infinite; }

.hero-title { font-size: 5rem; font-weight: 900; color: white; line-height: 0.95; letter-spacing: -3px; margin: 0 0 1.5rem 0; }
.hero-title .gradient { background: linear-gradient(90deg, #FF751F 0%, #ffb066 50%, #FF751F 100%); background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: gradientPan 4s ease infinite; }

.hero-subtitle { font-size: 1.2rem; color: rgba(255,255,255,0.82); line-height: 1.6; font-weight: 500; margin-bottom: 2.5rem; max-width: 540px; }

.hero-cta-row { display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; margin-bottom: 3rem; }
.hero-cta {
  display: inline-block;
  background: linear-gradient(90deg, #FF751F, #E4650F);
  color: white !important; font-weight: 800; padding: 18px 40px; border-radius: 12px;
  text-decoration: none; font-size: 15px; text-transform: uppercase; letter-spacing: 0.5px;
  box-shadow: 0 12px 30px rgba(255,117,31,0.45);
  transition: transform 0.25s, box-shadow 0.25s;
  position: relative; overflow: hidden;
}
.hero-cta::after { content: ''; position: absolute; top: 0; left: 0; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent); transform: translateX(-100%) skewX(-20deg); transition: transform 0.7s; }
.hero-cta:hover::after { transform: translateX(300%) skewX(-20deg); }
.hero-cta:hover { transform: translateY(-3px); box-shadow: 0 20px 45px rgba(255,117,31,0.6); }

.hero-cta-secondary { display: inline-flex; align-items: center; gap: 10px; background: rgba(255,255,255,0.08); backdrop-filter: blur(10px); border: 1.5px solid rgba(255,255,255,0.25); color: white !important; font-weight: 700; padding: 16px 32px; border-radius: 12px; text-decoration: none; font-size: 15px; transition: all 0.25s; }
.hero-cta-secondary:hover { background: rgba(255,255,255,0.15); border-color: rgba(255,117,31,0.6); transform: translateY(-3px); }

.hero-trust { display: flex; align-items: center; gap: 1.5rem; color: rgba(255,255,255,0.65); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; flex-wrap: wrap; }
.hero-trust .badge { display: flex; align-items: center; gap: 6px; }
.hero-trust svg { color: #FF751F; }

/* ---------- PHONE MOCKUP ---------- */
.hero-visual { position: relative; display: flex; justify-content: center; animation: float 6s ease-in-out infinite; }
.phone-mockup { width: 280px; height: 560px; border-radius: 42px; background: linear-gradient(135deg, #1a1a1a, #333); padding: 14px; box-shadow: 0 40px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.08), inset 0 0 40px rgba(255,117,31,0.08); position: relative; }
.phone-screen { width: 100%; height: 100%; border-radius: 30px; background: linear-gradient(160deg, #0a0a0a 0%, #1a0f00 60%, #FF751F 130%); padding: 1.5rem 1rem; position: relative; overflow: hidden; display: flex; flex-direction: column; gap: 1rem; }
.phone-screen::before { content: ''; position: absolute; top: -100px; right: -100px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(circle, rgba(255,117,31,0.5), transparent 60%); filter: blur(30px); }
.phone-notch { position: absolute; top: 8px; left: 50%; transform: translateX(-50%); width: 90px; height: 22px; background: #000; border-radius: 999px; z-index: 10; }
.mini-card { background: rgba(255,255,255,0.08); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; padding: 12px 14px; color: white; position: relative; z-index: 1; }
.mini-card .label { font-size: 9px; font-weight: 800; color: rgba(255,255,255,0.55); letter-spacing: 1.5px; text-transform: uppercase; }
.mini-card .value { font-size: 18px; font-weight: 900; color: white; margin-top: 3px; }
.mini-card .value.orange { color: #FF751F; }
.mini-card.accent { background: linear-gradient(135deg, #FF751F, #E4650F); border-color: rgba(255,255,255,0.2); }
.mini-card.accent .label { color: rgba(255,255,255,0.85); }

/* Floating chips around phone */
.float-chip {
  position: absolute;
  background: white;
  border-radius: 14px;
  padding: 10px 14px;
  box-shadow: 0 15px 40px rgba(0,0,0,0.15);
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; font-weight: 800; color: #111827;
  animation: floatSmall 5s ease-in-out infinite;
  z-index: 3;
}
.float-chip .chip-icon { width: 32px; height: 32px; border-radius: 10px; background: linear-gradient(135deg, #FF751F, #E4650F); display: flex; align-items: center; justify-content: center; color: white; font-size: 14px; }
.float-chip.left { top: 20%; left: -60px; animation-delay: 0s; }
.float-chip.right { top: 55%; right: -70px; animation-delay: 1.5s; }

/* ---------- LOGO MARQUEE ---------- */
.marquee-wrap { background: white; padding: 2.5rem 0; border-bottom: 1px solid #f3f4f6; overflow: hidden; }
.marquee-label { text-align: center; font-size: 11px; font-weight: 800; color: #9ca3af; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 1.5rem; }
.marquee { display: flex; width: fit-content; animation: marqueeScroll 30s linear infinite; }
.marquee-item { padding: 0 3.5rem; font-size: 22px; font-weight: 900; color: #9ca3af; font-style: italic; letter-spacing: -1px; white-space: nowrap; transition: color 0.3s; display: flex; align-items: center; gap: 8px; }
.marquee-item:hover { color: #FF751F; }
.marquee-item span { font-style: normal; font-weight: 700; font-size: 14px; letter-spacing: 2px; }

/* ---------- SECTIONS ---------- */
.section { padding: 6rem 3.5rem; position: relative; max-width: 1400px; margin: 0 auto; }
.section-eyebrow { display: inline-block; color: #FF751F; font-size: 11px; font-weight: 800; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 0.75rem; }
.section-title { font-size: 3rem; font-weight: 900; color: #111827; letter-spacing: -1.8px; margin: 0 0 1rem 0; line-height: 1.05; }
.section-subtitle { color: #6b7280; font-size: 1.05rem; max-width: 620px; font-weight: 500; line-height: 1.6; }
.text-center { text-align: center; }
.text-center .section-subtitle { margin-left: auto; margin-right: auto; }

/* ---------- FEATURE CARDS ---------- */
.feature-card {
  background: linear-gradient(135deg, #FF751F 0%, #E4650F 100%);
  border-radius: 24px; padding: 2.75rem 2.25rem; color: white; height: 100%;
  box-shadow: 0 12px 32px rgba(255,117,31,0.25);
  transition: transform 0.4s cubic-bezier(.22,1,.36,1), box-shadow 0.4s;
  position: relative; overflow: hidden;
}
.feature-card::before { content: ''; position: absolute; top: -80px; right: -80px; width: 200px; height: 200px; border-radius: 50%; background: rgba(255,255,255,0.1); transition: transform 0.5s; pointer-events: none; }
.feature-card::after { content: ''; position: absolute; top: 0; left: 0; width: 55%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent); transform: translateX(-150%) skewX(-20deg); transition: transform 0.85s; pointer-events: none; }
.feature-card:hover { transform: translateY(-10px) scale(1.02); box-shadow: 0 30px 60px rgba(255,117,31,0.4); }
.feature-card:hover::after { transform: translateX(300%) skewX(-20deg); }
.feature-card:hover::before { transform: scale(1.4); }
.feature-icon-box { width: 64px; height: 64px; border-radius: 16px; background: rgba(255,255,255,0.22); backdrop-filter: blur(10px); display: flex; align-items: center; justify-content: center; margin-bottom: 1.5rem; transition: transform 0.4s; }
.feature-card:hover .feature-icon-box { transform: rotate(10deg) scale(1.1); }
.feature-card h3 { color: white; font-size: 1.7rem; font-weight: 900; letter-spacing: -0.7px; margin: 0 0 0.9rem 0; position: relative; }
.feature-card p { color: rgba(255,255,255,0.92); font-size: 0.98rem; line-height: 1.6; margin: 0 0 1.75rem 0; position: relative; }
.feature-link { color: white !important; font-weight: 900; font-size: 0.85rem; text-decoration: none; text-transform: uppercase; letter-spacing: 1px; display: inline-flex; align-items: center; gap: 6px; transition: gap 0.25s; position: relative; }
.feature-link:hover { gap: 12px; }

/* ---------- HOW IT WORKS ---------- */
.how-wrap { background: linear-gradient(180deg, #fff7ed 0%, #ffffff 100%); padding: 6rem 3.5rem; }
.how-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2.5rem; max-width: 1200px; margin: 4rem auto 0 auto; }
.how-step { text-align: center; position: relative; padding: 1rem; }
.how-step .num { display: inline-flex; align-items: center; justify-content: center; width: 72px; height: 72px; border-radius: 50%; background: linear-gradient(135deg, #FF751F, #E4650F); color: white; font-size: 26px; font-weight: 900; box-shadow: 0 15px 40px rgba(255,117,31,0.4); margin-bottom: 1.5rem; position: relative; transition: transform 0.4s; }
.how-step:hover .num { transform: scale(1.1) rotate(6deg); }
.how-step .num::before { content: ''; position: absolute; inset: -8px; border-radius: 50%; border: 2px dashed rgba(255,117,31,0.3); animation: spinSlow 20s linear infinite; }
.how-step h3 { font-size: 1.4rem; font-weight: 900; color: #111827; letter-spacing: -0.5px; margin: 0 0 0.75rem 0; }
.how-step p { color: #6b7280; font-size: 0.95rem; line-height: 1.6; max-width: 320px; margin: 0 auto; }

/* ---------- STATS BAND ---------- */
.stats-band { background: #111827; padding: 5rem 3rem; border-radius: 32px; max-width: 1250px; margin: 3rem auto; position: relative; overflow: hidden; }
.stats-band::before { content: ''; position: absolute; top: -150px; left: 50%; transform: translateX(-50%); width: 700px; height: 300px; background: radial-gradient(circle, rgba(255,117,31,0.35) 0%, transparent 70%); filter: blur(40px); pointer-events: none; }
.stats-grid { position: relative; display: grid; grid-template-columns: repeat(4, 1fr); gap: 2rem; max-width: 1100px; margin: 0 auto; }
.stat-block { text-align: center; padding: 1.5rem 1rem; border-right: 1px solid rgba(255,255,255,0.08); transition: transform 0.3s; }
.stat-block:last-child { border-right: none; }
.stat-block:hover { transform: translateY(-6px); }
.stat-block .num { font-size: 3rem; font-weight: 900; color: #FF751F; letter-spacing: -1.5px; line-height: 1; margin: 0 0 0.5rem 0; }
.stat-block .label { font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.6); letter-spacing: 2px; text-transform: uppercase; margin: 0; }

/* ---------- DOWNLOAD BAND ---------- */
.download-band { background: linear-gradient(135deg, #FF751F 0%, #E4650F 50%, #B84708 100%); background-size: 200% auto; animation: gradientPan 8s ease infinite; padding: 4rem 3rem; border-radius: 32px; max-width: 1250px; margin: 3rem auto; display: flex; align-items: center; justify-content: space-between; gap: 2rem; flex-wrap: wrap; position: relative; overflow: hidden; box-shadow: 0 25px 60px rgba(255,117,31,0.35); }
.download-band::before { content: ''; position: absolute; top: 0; left: 0; width: 55%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent); transform: translateX(-150%) skewX(-20deg); animation: shimmer 4s ease-in-out infinite; animation-delay: 1s; pointer-events: none; }
.download-left { position: relative; z-index: 2; }
.download-band h3 { color: white; font-size: 2.25rem; font-weight: 900; letter-spacing: -1px; margin: 0 0 0.5rem 0; }
.download-band p { color: rgba(255,255,255,0.85); margin: 0; font-size: 1rem; }
.download-btn { position: relative; z-index: 2; display: inline-flex; align-items: center; gap: 10px; background: white; color: #FF751F !important; font-weight: 900; padding: 18px 36px; border-radius: 12px; text-decoration: none; font-size: 15px; text-transform: uppercase; letter-spacing: 0.5px; box-shadow: 0 12px 30px rgba(0,0,0,0.2); transition: transform 0.25s, box-shadow 0.25s; animation: glowPulse 3s ease-in-out infinite; }
.download-btn:hover { transform: translateY(-3px); box-shadow: 0 20px 45px rgba(0,0,0,0.3); }

/* ---------- TESTIMONIALS ---------- */
.testimonial { background: white; border: 1px solid #f3f4f6; border-radius: 20px; padding: 2rem; height: 100%; box-shadow: 0 8px 24px rgba(15,23,42,0.06); transition: transform 0.35s, box-shadow 0.35s; position: relative; }
.testimonial:hover { transform: translateY(-8px); box-shadow: 0 24px 48px rgba(15,23,42,0.12); }
.testimonial .quote-mark { font-size: 4rem; font-weight: 900; color: #FF751F; line-height: 0.5; margin-bottom: 1rem; display: block; opacity: 0.35; }
.testimonial .stars { color: #FFB800; font-size: 14px; letter-spacing: 2px; margin-bottom: 0.75rem; }
.testimonial .text { color: #374151; font-size: 1rem; line-height: 1.65; margin: 0 0 1.5rem 0; font-weight: 500; }
.testimonial .author { display: flex; align-items: center; gap: 12px; padding-top: 1.25rem; border-top: 1px solid #f3f4f6; }
.author-avatar { width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, #FF751F, #E4650F); display: flex; align-items: center; justify-content: center; color: white; font-weight: 900; font-size: 16px; }
.author-name { font-size: 0.95rem; font-weight: 800; color: #111827; margin: 0; }
.author-role { font-size: 0.8rem; color: #9ca3af; margin: 0; font-weight: 500; }

/* ---------- TRUST STRIP ---------- */
.trust { max-width: 1250px; margin: 4rem auto; padding: 3rem; background: linear-gradient(135deg, #fff7ed 0%, #FFEEDD 100%); border-radius: 28px; border: 1px solid #fed7aa; display: flex; align-items: center; gap: 2.5rem; flex-wrap: wrap; position: relative; overflow: hidden; }
.trust::before { content: ''; position: absolute; top: -80px; right: -80px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(circle, rgba(255,117,31,0.15), transparent 70%); pointer-events: none; }
.trust-icon { width: 80px; height: 80px; border-radius: 20px; background: white; display: flex; align-items: center; justify-content: center; font-size: 40px; box-shadow: 0 12px 30px rgba(255,117,31,0.25); flex-shrink: 0; position: relative; z-index: 1; }
.trust-content { position: relative; z-index: 1; flex: 1; min-width: 260px; }
.trust-content h4 { color: #111827; font-size: 1.4rem; font-weight: 900; letter-spacing: -0.5px; margin: 0 0 0.5rem 0; }
.trust-content p { color: #78350f; font-size: 1rem; margin: 0; line-height: 1.6; }

/* ---------- FINAL CTA ---------- */
.final-cta { text-align: center; padding: 7rem 2rem; background: radial-gradient(ellipse at center, #fff7ed 0%, #ffffff 70%); position: relative; overflow: hidden; }
.final-cta::before { content: ''; position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 800px; height: 400px; background: radial-gradient(circle, rgba(255,117,31,0.15), transparent 70%); filter: blur(50px); pointer-events: none; }
.final-cta h2 { position: relative; font-size: 3.5rem; font-weight: 900; color: #111827; letter-spacing: -2px; margin: 0 0 1rem 0; line-height: 1; }
.final-cta p { position: relative; color: #6b7280; font-size: 1.15rem; margin: 0 0 2.5rem 0; font-weight: 500; }

/* ---------- FOOTER ---------- */
.site-footer { background: #0a0a0a; color: rgba(255,255,255,0.6); padding: 4rem 3.5rem 2rem 3.5rem; }
.footer-grid { display: grid; grid-template-columns: 1.5fr 1fr 1fr 1fr; gap: 3rem; max-width: 1300px; margin: 0 auto 3rem auto; }
.footer-brand { font-size: 1.6rem; font-weight: 900; font-style: italic; color: white; letter-spacing: -1px; margin-bottom: 1rem; }
.footer-brand span { color: #FF751F; }
.footer-desc { font-size: 0.9rem; line-height: 1.6; max-width: 320px; margin-bottom: 1.5rem; }
.footer-col h5 { color: white; font-size: 0.8rem; font-weight: 800; letter-spacing: 2px; text-transform: uppercase; margin: 0 0 1.25rem 0; }
.footer-col ul { list-style: none; padding: 0; margin: 0; }
.footer-col ul li { margin-bottom: 0.65rem; }
.footer-col ul a { color: rgba(255,255,255,0.6); text-decoration: none; font-size: 0.9rem; transition: color 0.25s, padding-left 0.25s; }
.footer-col ul a:hover { color: #FF751F; padding-left: 6px; }
.socials { display: flex; gap: 10px; }
.social-btn { width: 40px; height: 40px; border-radius: 10px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; color: white !important; text-decoration: none; font-weight: 700; font-size: 14px; transition: all 0.25s; }
.social-btn:hover { background: #FF751F; border-color: #FF751F; transform: translateY(-3px); }
.footer-bottom { max-width: 1300px; margin: 0 auto; padding-top: 2rem; border-top: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; font-size: 0.85rem; flex-wrap: wrap; gap: 1rem; }

/* ---------- STREAMLIT BUTTON OVERRIDE ---------- */
div.stButton > button { background: linear-gradient(90deg,#FF751F,#E4650F) !important; color: white !important; border: none !important; border-radius: 12px !important; padding: 18px 48px !important; font-weight: 800 !important; font-size: 15px !important; text-transform: uppercase !important; letter-spacing: 0.5px !important; box-shadow: 0 12px 30px rgba(255,117,31,0.4) !important; transition: all 0.25s !important; }
div.stButton > button:hover { transform: translateY(-3px) !important; box-shadow: 0 20px 45px rgba(255,117,31,0.55) !important; }

/* Responsive */
@media (max-width: 900px) {
  .hero-inner { grid-template-columns: 1fr; gap: 3rem; }
  .hero-title { font-size: 3.5rem; letter-spacing: -2px; }
  .hero-visual { display: none; }
  .how-grid { grid-template-columns: 1fr; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .footer-grid { grid-template-columns: 1fr 1fr; }
  .nav-links { display: none; }
  .section { padding: 4rem 1.5rem; }
  .topnav { padding: 1rem 1.5rem; }
  .hero { padding: 4rem 1.5rem 5rem 1.5rem; }
}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# 4. TOP NAV  (NO indentation!)
# ==========================================
logo_html = icon_img("logo", 32, "📦")
nav_html = f"""<div class="topnav">
<div class="brand">{logo_html} Pack-<span>N</span>-Ship</div>
<div class="nav-links">
<a href="#features">Services</a>
<a href="#how">How It Works</a>
<a href="#security">Security</a>
<a href="#download">Download</a>
</div>
<div class="nav-actions">
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="nav-signup">Download App</a>
</div>
</div>"""
st.markdown(nav_html, unsafe_allow_html=True)

# ==========================================
# 5. HERO
# ==========================================
hero_html = f"""<div class="hero">
<div class="hero-orb-1"></div>
<div class="hero-orb-2"></div>
<div class="hero-inner">
<div class="fade-up">
<div class="hero-eyebrow"><span class="dot"></span> Pack-N-Ship: A Peer-to-Peer Express Logistics and
                                                  Moving Services Platform   
</div>
<h1 class="hero-title">Deliver<br><span class="gradient">Faster.</span></h1>
<p class="hero-subtitle">On-demand delivery for businesses and individuals — powered by blockchain-secured escrow, real-time tracking, and AI-optimized routing.</p>
<div class="hero-cta-row">
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="hero-cta">Download App →</a>
<a href="#features" class="hero-cta-secondary">▶ See Features</a>
</div>
<div class="hero-trust">
<span class="badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> No Setup Fees</span>
<span class="badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> Insured Escrow</span>
<span class="badge"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> 24/7 Support</span>
</div>
</div>
<div class="hero-visual slide-right stagger-2" style="position:relative;">
<div class="float-chip left"><div class="chip-icon">⚡</div><div>Matched in 30s</div></div>
<div class="float-chip right"><div class="chip-icon">🔒</div><div>Escrow Secured</div></div>
<div class="phone-mockup">
<div class="phone-notch"></div>
<div class="phone-screen">
<div class="mini-card accent"><div class="label">Active Delivery</div><div class="value">On the way →</div></div>
<div class="mini-card"><div class="label">Est. Arrival</div><div class="value orange">12 min</div></div>
<div class="mini-card"><div class="label">Escrow Status</div><div class="value">🔒 Secured</div></div>
<div class="mini-card"><div class="label">Tracking</div><div class="value">Live GPS</div></div>
<div style="margin-top:auto; padding:12px; background:rgba(255,255,255,0.06); border-radius:12px; text-align:center;">
<div style="font-size:10px; color:rgba(255,255,255,0.5); font-weight:800; letter-spacing:2px;">PACK-N-SHIP</div>
</div>
</div>
</div>
</div>
</div>
</div>"""
st.markdown(hero_html, unsafe_allow_html=True)

# ==========================================
# 6. LOGO MARQUEE
# ==========================================
marquee_html = """<div class="marquee-wrap">
<p class="marquee-label">Trusted by teams across the Philippines</p>
<div class="marquee">
<div class="marquee-item">● ARANETA<span>GROUP</span></div>
<div class="marquee-item">◆ MERIDIAN<span>LOGISTICS</span></div>
<div class="marquee-item">▲ PACIFIC<span>CARGO</span></div>
<div class="marquee-item">■ SM<span>RETAIL</span></div>
<div class="marquee-item">✦ MANILA<span>EXPRESS</span></div>
<div class="marquee-item">● ARANETA<span>GROUP</span></div>
<div class="marquee-item">◆ MERIDIAN<span>LOGISTICS</span></div>
<div class="marquee-item">▲ PACIFIC<span>CARGO</span></div>
<div class="marquee-item">■ SM<span>RETAIL</span></div>
<div class="marquee-item">✦ MANILA<span>EXPRESS</span></div>
</div>
</div>"""
st.markdown(marquee_html, unsafe_allow_html=True)

# ==========================================
# 7. FEATURES HEADER
# ==========================================
features_header = """<div class="section text-center" id="features">
<span class="section-eyebrow">Built for Every Need</span>
<h2 class="section-title">One platform. Endless possibilities.</h2>
<p class="section-subtitle">Whether you're shipping to a customer, sending a personal gift, or earning on the road — Pack-N-Ship is designed for you.</p>
</div>"""
st.markdown(features_header, unsafe_allow_html=True)

# ==========================================
# 8. FEATURE CARDS
# ==========================================
f1, f2, f3 = st.columns(3)

with f1:
    card = f"""<div class="feature-card fade-up stagger-1">
<div class="feature-icon-box">{icon_img("business", 32, "💼")}</div>
<h3>For Business</h3>
<p>Enterprise-grade last-mile delivery with API access, bulk shipments, SLA guarantees, and a dedicated account manager.</p>
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="feature-link">Explore Business →</a>
</div>"""
    st.markdown(card, unsafe_allow_html=True)

with f2:
    card = f"""<div class="feature-card fade-up stagger-2">
<div class="feature-icon-box">{icon_img("personal", 32, "📦")}</div>
<h3>For Personal</h3>
<p>Send documents, packages, or gifts across town in minutes. Real-time tracking, contactless handover, and full insurance.</p>
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="feature-link">Send a Package →</a>
</div>"""
    st.markdown(card, unsafe_allow_html=True)

with f3:
    card = f"""<div class="feature-card fade-up stagger-3">
<div class="feature-icon-box">{icon_img("driver", 32, "🚗")}</div>
<h3>For Drivers</h3>
<p>Earn on your schedule with instant payouts, transparent earnings, and blockchain-secured escrow payments.</p>
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="feature-link">Become a Partner →</a>
</div>"""
    st.markdown(card, unsafe_allow_html=True)

# ==========================================
# 9. HOW IT WORKS
# ==========================================
how_html = """<div class="how-wrap" id="how">
<div class="section text-center" style="padding:0;">
<span class="section-eyebrow">How It Works</span>
<h2 class="section-title">From booking to delivered — in minutes.</h2>
<p class="section-subtitle">Our intelligent matching system pairs every request with the ideal provider in under 30 seconds.</p>
</div>
<div class="how-grid">
<div class="how-step fade-up stagger-1">
<div class="num">1</div>
<h3>Book a Delivery</h3>
<p>Set your pickup and drop-off, describe your package, and we'll instantly match you with the best provider nearby.</p>
</div>
<div class="how-step fade-up stagger-2">
<div class="num">2</div>
<h3>Track in Real-Time</h3>
<p>Follow your delivery every step of the way with live GPS tracking, status updates, and direct chat with your driver.</p>
</div>
<div class="how-step fade-up stagger-3">
<div class="num">3</div>
<h3>Pay Securely</h3>
<p>Funds are held safely in blockchain-secured escrow and released only after successful delivery confirmation.</p>
</div>
</div>
</div>"""
st.markdown(how_html, unsafe_allow_html=True)

# ==========================================
# 11. DOWNLOAD BAND
# ==========================================
download_html = f"""<div class="download-band" id="download">
<div class="download-left">
<h3>📱 Get the Pack-N-Ship App</h3>
<p>Available for Android. Download the APK and start delivering in minutes.</p>
</div>
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="download-btn">
<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 15v-4H8l4-4 4 4h-3v4h-2z"/></svg>
Download APK
</a>
</div>"""
st.markdown(download_html, unsafe_allow_html=True)

# ==========================================
# 13. TRUST STRIP
# ==========================================
trust_html = """<div class="trust" id="security">
<div class="trust-icon">🔒</div>
<div class="trust-content">
<h4>Blockchain-Secured Escrow</h4>
<p>Every transaction is cryptographically protected. Funds are held safely in escrow and released only after successful delivery — protecting senders, receivers, and drivers alike.</p>
</div>
</div>"""
st.markdown(trust_html, unsafe_allow_html=True)

# ==========================================
# 14. FINAL CTA
# ==========================================
final_cta = f"""<div class="final-cta" id="cta">
<h2>Ready to move faster?</h2>
<p>Join thousands of senders and drivers already using Pack-N-Ship.</p>
<a href="{APK_DOWNLOAD_LINK}" target="_blank" class="hero-cta">Download the App →</a>
</div>"""
st.markdown(final_cta, unsafe_allow_html=True)

# ==========================================
# 15. FOOTER
# ==========================================
footer_html = """<div class="site-footer">
<div class="footer-grid">
<div>
<div class="footer-brand">Pack-<span>N</span>-Ship</div>
<p class="footer-desc">Enterprise-grade logistics for businesses and individuals. Blockchain-secured, real-time, and built for scale.</p>
<div class="socials">
<a href="#" class="social-btn">f</a>
<a href="#" class="social-btn">𝕏</a>
<a href="#" class="social-btn">in</a>
<a href="#" class="social-btn">IG</a>
</div>
</div>
<div class="footer-col"><h5>Product</h5><ul>
<li><a href="#features">Features</a></li>
<li><a href="#download">Download App</a></li>
<li><a href="#how">How It Works</a></li>
<li><a href="#">Pricing</a></li>
</ul></div>
<div class="footer-col"><h5>Company</h5><ul>
<li><a href="#">About Us</a></li>
<li><a href="#">Careers</a></li>
<li><a href="#">Press</a></li>
<li><a href="#">Contact</a></li>
</ul></div>
<div class="footer-col"><h5>Legal</h5><ul>
<li><a href="#">Terms of Service</a></li>
<li><a href="#">Privacy Policy</a></li>
<li><a href="#">Security</a></li>
<li><a href="#">Cookie Policy</a></li>
</ul></div>
</div>
<div class="footer-bottom">
<span>© 2026 Pack-N-Ship Logistics. All rights reserved.</span>
<span>Made with ❤️ in the Philippines</span>
</div>
</div>"""
st.markdown(footer_html, unsafe_allow_html=True)