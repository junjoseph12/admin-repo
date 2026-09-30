import streamlit as st

# 1. Page Configuration (Must be the first Streamlit command)
st.set_page_config(
    page_title="Capstone Website",
    page_icon="🚀",
    layout="wide"
)

# 2. Hero Section
st.title("🚀 Welcome to Capstone(Website)")
st.subheader("A modern solution built with Python")
st.write(
    "This is the landing page for our Capstone project. "
    "We are transitioning from a traditional Django framework to an interactive Streamlit dashboard."
)

# Add some action buttons
col1, col2, _ = st.columns([1, 1, 4])
with col1:
    st.button("Get Started", type="primary")
with col2:
    st.button("Learn More")

st.divider() # Adds a nice horizontal line

# 3. Features Section (Using Columns)
st.header("✨ Key Features")

# Create 3 columns for features
feat_col1, feat_col2, feat_col3 = st.columns(3)

with feat_col1:
    st.subheader("📊 Data Analytics")
    st.write("Real-time data processing and visualization directly in the browser.")

with feat_col2:
    st.subheader("🔒 Secure")
    st.write("Built with modern security practices to ensure your data is safe.")

with feat_col3:
    st.subheader("⚡ Fast")
    st.write("Lightning-fast performance powered by Streamlit and Python.")

st.divider()

# 4. Metrics Section (Good for showing project impact)
st.header("📈 Project Impact")
m_col1, m_col2, m_col3, m_col4 = st.columns(4)

m_col1.metric("Users", "1,200", "+15%")
m_col2.metric("Transactions", "8,500", "+5%")
m_col3.metric("Uptime", "99.9%", "0%")
m_col4.metric("Efficiency", "85%", "+10%")

st.divider()

# 5. Call to Action / Footer
st.header("Ready to explore?")
st.write("Click the button below to enter the main application dashboard.")
if st.button("Enter Dashboard", use_container_width=True):
    st.success("Dashboard connection coming soon! (This is where you would link to your main app logic)")
    # Note: In Streamlit, you usually switch pages using st.switch_page() or a sidebar navigation