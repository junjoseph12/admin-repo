import streamlit as st
import base64
import os

# ==========================================
# 1. PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="Pack-N-Ship",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==========================================
# 2. HELPER: Convert image to base64 (so we can style it nicely)
# ==========================================
def get_image_base64(path):
    """Safely load an image and return base64 string, or None if not found."""
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    except Exception:
        return None
    return None

# Preload all the icons we need (adjust paths if needed)
ICON_PATHS = {
    "users":       "web/static/images/totaluser_icon.png",
    "deliveries":  "web/static/images/totaldeliveries_icon.png",
    "revenue":     "web/static/images/totalrevenue_icon.png",
    "pending":     "web/static/images/totalpendingdeliveries_icon.png",
    "car":         "web/static/images/carverification_icon.png",
    "feedback":    "web/static/images/feedbackanddispute_icon.png",
    "reports":     "web/static/images/report_icon.png",
}

ICONS = {k: get_image_base64(v) for k, v in ICON_PATHS.items()}

def icon_html(key, size=56):
    """Return an <img> tag if the icon exists, else a fallback emoji."""
    b64 = ICONS.get(key)
    if b64:
        return f'<img src="data:image/png;base64,{b64}" style="width:{size}px; height:{size}px; object-fit:contain;" />'
    # Fallbacks if the file isn't found
    fallback = {"users":"👥","deliveries":"📦","revenue":"💰","pending":"⏳",
                "car":"🚗","feedback":"⭐","reports":"📊"}
    return f'<div style="font-size:{size}px;">{fallback.get(key,"✨")}</div>'

# ==========================================
# 3. CUSTOM CSS — Lalamove-style design
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Hide default Streamlit chrome for a cleaner look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; max-width: 100% !important; }

    /* Hero gradient background */
    .hero-wrapper {
        background: linear-gradient(120deg, #1a1a1a 0%, #3d1f00 40%, #FF751F 100%);
        padding: 4rem 3rem 5rem 3rem;
        border-radius: 0;
        position: relative;
        overflow: hidden;
    }
    .hero-wrapper::after {
        content: '';
        position: absolute;
        bottom: -50%; right: -10%;
        width: 700px; height: 700px;
        background: radial-gradient(circle, rgba(255,117,31,0.35) 0%, transparent 70%);
        border-radius: 50%;
        pointer-events: none;
    }

    .hero-title {
        font-size: 4.5rem;
        font-weight: 900;
        color: white;
        line-height: 1;
        margin: 0 0 1rem 0;
        letter-spacing: -2px;
    }
    .hero-subtitle {
        font-size: 1.3rem;
        color: rgba(255,255,255,0.85);
        max-width: 600px;
        margin-bottom: 2rem;
        line-height: 1.5;
        font-weight: 500;
    }

    /* Primary CTA button */
    .cta-btn {
        display: inline-block;
        background: linear-gradient(90deg, #FF751F, #E4650F);
        color: white !important;
        font-weight: 800;
        padding: 16px 40px;
        border-radius: 8px;
        text-decoration: none;
        font-size: 1.05rem;
        box-shadow: 0 8px 24px rgba(255,117,31,0.4);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .cta-btn:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 32px rgba(255,117,31,0.55);
        color: white !important;
    }

    /* Section header */
    .section-header {
        text-align: center;
        font-size: 2.5rem;
        font-weight: 900;
        color: #1a1a1a;
        margin: 4rem 0 1rem 0;
        letter-spacing: -1px;
    }
    .section-subheader {
        text-align: center;
        color: #6b7280;
        font-size: 1.05rem;
        margin-bottom: 3rem;
    }

    /* Feature card (bottom orange cards like Lalamove) */
    .feature-card {
        background: linear-gradient(135deg, #FF751F 0%, #E4650F 100%);
        border-radius: 16px;
        padding: 2.5rem 2rem;
        color: white;
        height: 100%;
        box-shadow: 0 10px 30px rgba(255,117,31,0.25);
        transition: transform 0.25s;
    }
    .feature-card:hover {
        transform: translateY(-8px);
    }
    .feature-card h3 {
        color: white;
        font-size: 1.5rem;
        font-weight: 800;
        margin: 1rem 0 0.75rem 0;
    }
    .feature-card p {
        color: rgba(255,255,255,0.9);
        font-size: 0.95rem;
        line-height: 1.5;
        margin-bottom: 1.5rem;
    }
    .feature-link {
        color: white !important;
        font-weight: 800;
        font-size: 0.9rem;
        text-decoration: none;
        display: inline-block;
    }

    /* Stats band (light) */
    .stats-band {
        background: #f8f9fa;
        padding: 4rem 2rem;
        border-radius: 24px;
        margin: 4rem 0;
    }
    .stat-item {
        text-align: center;
        padding: 1.5rem;
    }
    .stat-value {
        font-size: 2.75rem;
        font-weight: 900;
        color: #FF751F;
        margin: 0.75rem 0 0.25rem 0;
        letter-spacing: -1px;
    }
    .stat-label {
        font-size: 0.85rem;
        font-weight: 700;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin: 0;
    }

    /* Trust strip */
    .trust-strip {
        background: #1a1a1a;
        padding: 2rem;
        border-radius: 16px;
        color: white;
        text-align: center;
        margin: 2rem 0;
    }
    .trust-strip h4 {
        color: #FF751F;
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 3px;
        text-transform: uppercase;
        margin: 0 0 0.5rem 0;
    }
    .trust-strip p {
        color: rgba(255,255,255,0.8);
        margin: 0;
        font-size: 1rem;
    }

    /* Footer */
    .footer {
        background: #1a1a1a;
        color: rgba(255,255,255,0.6);
        padding: 2rem;
        text-align: center;
        font-size: 0.85rem;
        margin-top: 4rem;
    }
    .footer strong { color: #FF751F; }

    /* Streamlit button override for the sidebar/footer buttons */
    div.stButton > button {
        background: linear-gradient(90deg, #FF751F, #E4650F) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 14px 32px !important;
        font-weight: 800 !important;
        font-size: 1rem !important;
        box-shadow: 0 8px 24px rgba(255,117,31,0.4) !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. HERO SECTION
# ==========================================
st.markdown(f"""
<div class="hero-wrapper">

    <!-- Top nav bar with brand -->
    <div style="display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 4rem; position: relative; z-index: 2;">
        <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="font-size: 2rem;">📦</span>
            <span style="color: white; font-size: 1.6rem; font-weight: 900; font-style: italic; letter-spacing: -1px;">
                Pack-<span style="color:#FF751F;">N</span>-Ship
            </span>
        </div>
        <div style="display:none;">
            <!-- placeholder to keep spacing on smaller screens -->
        </div>
    </div>

    <!-- Hero content -->
    <div style="position: relative; z-index: 2;">
        <p style="color: #FF751F; font-weight: 800; letter-spacing: 3px; font-size: 0.8rem;
                  text-transform: uppercase; margin-bottom: 1rem;">
            ● LIVE LOGISTICS PLATFORM
        </p>
        <h1 class="hero-title">Deliver Faster.</h1>
        <p class="hero-subtitle">
            On-demand delivery platform connecting senders and providers 
            with blockchain-secured escrow and real-time tracking.
        </p>
        <a href="#features" class="cta-btn">Book a Delivery →</a>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 5. THREE-CARD FEATURE ROW (Like Lalamove)
# ==========================================
st.markdown('<h2 class="section-header" id="features">Built for Every Need</h2>', unsafe_allow_html=True)
st.markdown('<p class="section-subheader">Whether you\'re sending a package or delivering for a living — we\'ve got you covered.</p>', unsafe_allow_html=True)

f1, f2, f3 = st.columns(3)

with f1:
    st.markdown(f"""
    <div class="feature-card">
        {icon_html("reports", 48)}
        <h3>For Business</h3>
        <p>Last-mile delivery solutions for businesses of all sizes. Bulk orders, API access, and dedicated support.</p>
        <a href="#" class="feature-link">Grow your business →</a>
    </div>
    """, unsafe_allow_html=True)

with f2:
    st.markdown(f"""
    <div class="feature-card">
        {icon_html("deliveries", 48)}
        <h3>For Personal</h3>
        <p>Quick on-demand delivery service for all your needs. From documents to parcels — sent in minutes.</p>
        <a href="#" class="feature-link">Send a package →</a>
    </div>
    """, unsafe_allow_html=True)

with f3:
    st.markdown(f"""
    <div class="feature-card">
        {icon_html("car", 48)}
        <h3>For Drivers</h3>
        <p>Earn more as a delivery partner. Flexible hours, instant payouts, and blockchain-secured escrow payments.</p>
        <a href="#" class="feature-link">Become a partner →</a>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 6. STATS BAND (Using your custom icons)
# ==========================================
st.markdown(f"""
<div class="stats-band">
    <h2 class="section-header" style="margin-top:0;">Trusted by Thousands</h2>
    <p class="section-subheader">The numbers behind our growing logistics network</p>
    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; max-width: 1100px; margin: 0 auto;">
        <div class="stat-item">
            {icon_html("users", 64)}
            <p class="stat-value">1,200+</p>
            <p class="stat-label">Active Users</p>
        </div>
        <div class="stat-item">
            {icon_html("deliveries", 64)}
            <p class="stat-value">8,500+</p>
            <p class="stat-label">Deliveries</p>
        </div>
        <div class="stat-item">
            {icon_html("revenue", 64)}
            <p class="stat-value">₱2.4M</p>
            <p class="stat-label">Processed</p>
        </div>
        <div class="stat-item">
            {icon_html("pending", 64)}
            <p class="stat-value">99.9%</p>
            <p class="stat-label">Uptime</p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 7. TRUST STRIP
# ==========================================
st.markdown("""
<div class="trust-strip">
    <h4>🔒 Blockchain-Secured Escrow</h4>
    <p>Every transaction is protected by our escrow system — funds are released only after successful delivery.</p>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 8. CTA SECTION
# ==========================================
st.markdown("""
<div style="text-align:center; padding: 3rem 1rem;">
    <h2 style="font-size: 2.5rem; font-weight: 900; color: #1a1a1a; margin-bottom: 1rem;">Ready to get started?</h2>
    <p style="color: #6b7280; font-size: 1.1rem; margin-bottom: 2rem;">Join thousands of senders and drivers already using Pack-N-Ship.</p>
</div>
""", unsafe_allow_html=True)

c1, c2, c3 = st.columns([1, 1, 1])
with c2:
    st.button("Create Free Account →", use_container_width=True)

# ==========================================
# 9. FOOTER
# ==========================================
st.markdown("""
<div class="footer">
    <p style="font-size:1.2rem; font-weight:900; color:white; margin-bottom: 0.5rem;">
        Pack-<strong>N</strong>-Ship
    </p>
    <p>© 2026 Pack-N-Ship Logistics. All rights reserved.</p>
</div>
""", unsafe_allow_html=True)