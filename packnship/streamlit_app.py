import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="Capstone Website",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed" # Hides the sidebar for a cleaner landing page look
)

# 2. Custom CSS for Design
# This injects CSS to make the page look modern (cards, colors, buttons)
st.markdown("""
<style>
    /* Main background color */
    .stApp {
        background-color: #f8f9fa;
    }
    
    /* Hero Section Styling */
    .hero-section {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 4rem 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .hero-section h1 {
        color: white !important;
        font-size: 3rem !important;
        margin-bottom: 0.5rem;
    }
    .hero-section p {
        font-size: 1.2rem;
        opacity: 0.9;
    }

    /* Feature Card Styling */
    .feature-card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-top: 4px solid #2a5298;
        height: 100%;
        transition: transform 0.2s;
    }
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.1);
    }
    .feature-card h3 {
        color: #1e3c72;
        margin-top: 0;
    }
    .feature-card p {
        color: #555;
        font-size: 0.95rem;
    }

    /* Button Styling Override */
    div.stButton > button:first-child {
        background-color: #ff4b4b;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 2rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    div.stButton > button:first-child:hover {
        background-color: #ff3333;
        transform: scale(1.05);
    }
    
    /* Secondary Button Styling */
    div.stButton > button:not(:first-child) {
        background-color: transparent;
        color: #1e3c72;
        border: 2px solid #1e3c72;
        border-radius: 8px;
        padding: 0.5rem 2rem;
        font-weight: bold;
    }
    div.stButton > button:not(:first-child):hover {
        background-color: #1e3c72;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# 3. Hero Section using HTML
st.markdown("""
<div class="hero-section">
    <h1>🚀 Capstone(Website)</h1>
    <p>A modern, interactive solution built with Python and Streamlit.</p>
</div>
""", unsafe_allow_html=True)

# 4. Call to Action Buttons
col1, col2, col3 = st.columns([1, 1, 1])
with col2:
    st.button("Get Started", use_container_width=True)

st.write("") # Spacer

# 5. Features Section using HTML Cards
st.markdown("<h2 style='text-align: center; color: #1e3c72;'>✨ Key Features</h2>", unsafe_allow_html=True)
st.write("") # Spacer

feat_col1, feat_col2, feat_col3 = st.columns(3)

with feat_col1:
    st.markdown("""
    <div class="feature-card">
        <h3>📊 Data Analytics</h3>
        <p>Real-time data processing and visualization directly in the browser. No complex setup required.</p>
    </div>
    """, unsafe_allow_html=True)

with feat_col2:
    st.markdown("""
    <div class="feature-card">
        <h3>🔒 Secure</h3>
        <p>Built with modern security practices to ensure your data is safe and your users are protected.</p>
    </div>
    """, unsafe_allow_html=True)

with feat_col3:
    st.markdown("""
    <div class="feature-card">
        <h3>⚡ Fast</h3>
        <p>Lightning-fast performance powered by Streamlit and Python, ensuring a smooth user experience.</p>
    </div>
    """, unsafe_allow_html=True)

st.write("") # Spacer

# 6. Metrics Section
st.markdown("<h2 style='text-align: center; color: #1e3c72;'>📈 Project Impact</h2>", unsafe_allow_html=True)
st.write("") # Spacer

m_col1, m_col2, m_col3, m_col4 = st.columns(4)

m_col1.metric("Users", "1,200", "+15%")
m_col2.metric("Transactions", "8,500", "+5%")
m_col3.metric("Uptime", "99.9%", "0%")
m_col4.metric("Efficiency", "85%", "+10%")

st.write("") # Spacer
st.divider()

# 7. Footer
st.markdown("""
<div style='text-align: center; color: #888; padding: 2rem;'>
    <p>© 2024 Capstone Project. Built with ❤️ using Streamlit.</p>
</div>
""", unsafe_allow_html=True)