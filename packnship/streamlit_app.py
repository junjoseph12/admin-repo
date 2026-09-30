import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

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
# 2. CUSTOM CSS (Orange Design from login.html)
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Animated Orange Gradient Background */
    .stApp {
        background: linear-gradient(135deg, #FF751F 0%, #E4650F 30%, #C9540A 60%, #E4650F 100%);
        background-size: 300% 300%;
        animation: gradientShift 14s ease infinite;
    }
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Glassmorphism Card */
    .glass-card {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 24px;
        padding: 2.5rem 2rem;
        box-shadow: 0 25px 60px -15px rgba(15, 23, 42, 0.35);
        border: 1px solid rgba(255, 255, 255, 0.6);
        text-align: center;
        height: 100%;
    }
    
    .hero-title {
        font-size: 4rem;
        font-weight: 900;
        font-style: italic;
        color: #1f2937;
        margin-bottom: 0.5rem;
        line-height: 1;
    }
    .hero-title span { color: #FF751F; }
    
    .hero-subtitle {
        font-size: 1.15rem;
        color: #4b5563;
        max-width: 700px;
        margin: 0 auto;
        font-weight: 500;
    }

    .badge {
        display: inline-block;
        background: #FFEEDD;
        color: #D47A4A;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 1.5rem;
    }

    /* Feature Cards */
    .feature-card {
        background: white;
        padding: 1.5rem;
        border-radius: 16px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        text-align: center;
        height: 100%;
        border-top: 4px solid #FF751F;
    }
    .feature-card h3 {
        color: #1f2937;
        margin-top: 0.5rem;
        font-size: 1.1rem;
    }
    .feature-card p {
        color: #6b7280;
        font-size: 0.9rem;
        margin: 0;
    }

    /* Metric Cards */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 16px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border-left: 5px solid #FF751F;
        text-align: center;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 900;
        color: #FF751F;
        margin: 0;
    }
    .metric-label {
        font-size: 0.75rem;
        font-weight: 800;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 0;
    }

    /* Section Headers */
    .section-header {
        text-align: center;
        color: white;
        font-size: 2rem;
        font-weight: 800;
        margin: 3rem 0 2rem 0;
    }

    /* Streamlit Button Override */
    div.stButton > button {
        background: linear-gradient(90deg, #FF751F, #E4650F) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 24px !important;
        font-weight: 800 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        box-shadow: 0 4px 14px rgba(255, 117, 31, 0.35) !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. DATABASE CONNECTION
# ==========================================
def get_db_connection():
    try:
        db_host = st.secrets["DB_HOST"]
        db_name = st.secrets["DB_NAME"]
        db_user = st.secrets["DB_USER"]
        db_pass = st.secrets["DB_PASSWORD"]
        db_port = st.secrets.get("DB_PORT", "5432")
    except Exception:
        # --- CHANGE THESE FOR LOCAL TESTING ---
        db_host = "localhost"
        db_name = "your_db_name"
        db_user = "postgres"
        db_pass = "your_password"
        db_port = "5432"
    return create_engine(f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")

# ==========================================
# 4. HERO SECTION
# ==========================================
st.write("")
st.write("")

col1, col2, col3 = st.columns([1, 4, 1])
with col2:
    st.markdown("""
    <div class="glass-card">
        <div class="badge">🚀 Live Logistics Platform</div>
        <div class="hero-title">Pack-<span>N</span>-Ship</div>
        <p class="hero-subtitle">
            A modern, real-time logistics solution connecting senders and providers 
            with blockchain-secured escrow payments and live tracking.
        </p>
    </div>
    """, unsafe_allow_html=True)

st.write("")
st.write("")

# ==========================================
# 5. LIVE METRICS (Real Data from DB)
# ==========================================
st.markdown('<h2 class="section-header">📊 Live Platform Stats</h2>', unsafe_allow_html=True)

# Default fallback values
total_users = 0
total_deliveries = 0
total_revenue = 0.0
pending_deliveries = 0

try:
    engine = get_db_connection()
    query_stats = """
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM deliveries) AS total_deliveries,
            (SELECT COALESCE(SUM(total_amount), 0) 
             FROM transactions 
             WHERE status IN ('Completed', 'Released')) AS total_revenue,
            (SELECT COUNT(*) FROM (
                SELECT DISTINCT ON (delivery_id) delivery_id, status
                FROM delivery_status_history
                ORDER BY delivery_id, updated_at DESC
            ) latest WHERE latest.status = 'Pending') AS pending_deliveries
    """
    df = pd.read_sql(query_stats, engine)
    total_users        = int(df['total_users'].iloc[0])
    total_deliveries   = int(df['total_deliveries'].iloc[0])
    total_revenue      = float(df['total_revenue'].iloc[0])
    pending_deliveries = int(df['pending_deliveries'].iloc[0])
except Exception as e:
    st.warning(f"⚠️ Live data unavailable right now. Showing cached stats. ({e})")

# Display Metric Cards
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{total_users:,}</p>
        <p class="metric-label">Total Users</p>
    </div>
    """, unsafe_allow_html=True)
with m2:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{total_deliveries:,}</p>
        <p class="metric-label">Deliveries</p>
    </div>
    """, unsafe_allow_html=True)
with m3:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">₱{total_revenue:,.0f}</p>
        <p class="metric-label">Revenue</p>
    </div>
    """, unsafe_allow_html=True)
with m4:
    st.markdown(f"""
    <div class="metric-card">
        <p class="metric-value">{pending_deliveries:,}</p>
        <p class="metric-label">Pending Now</p>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 6. FEATURES SECTION
# ==========================================
st.markdown('<h2 class="section-header">✨ Key Features</h2>', unsafe_allow_html=True)

f1, f2, f3 = st.columns(3)
with f1:
    st.markdown("""
    <div class="feature-card">
        <h3>📊 Real-Time Analytics</h3>
        <p>Live dashboard tracking every delivery from pickup to drop-off.</p>
    </div>
    """, unsafe_allow_html=True)
with f2:
    st.markdown("""
    <div class="feature-card">
        <h3>🔒 Secure Escrow</h3>
        <p>Blockchain-anchored payments protecting both senders and providers.</p>
    </div>
    """, unsafe_allow_html=True)
with f3:
    st.markdown("""
    <div class="feature-card">
        <h3>⚡ Fast Delivery</h3>
        <p>Optimized routing and instant status updates for every package.</p>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# 7. FOOTER
# ==========================================
st.write("")
st.write("")
st.markdown("""
<p style='text-align: center; color: rgba(255,255,255,0.75); font-size: 0.8rem; font-weight: 600; padding: 2rem 0;'>
    © 2026 Pack-N-Ship Logistics · Built with ❤️ using Streamlit
</p>
""", unsafe_allow_html=True)