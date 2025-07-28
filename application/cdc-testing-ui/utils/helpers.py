"""
Helper functions and utilities
"""
import streamlit as st
from config.settings import DB_CONFIG, KAFKA_CONFIG
from managers.database import DatabaseManager
from managers.kafka import KafkaManager


def init_session_state():
    """Initialize session state variables"""
    if "db_manager" not in st.session_state:
        st.session_state.db_manager = DatabaseManager(DB_CONFIG)

    if "kafka_manager" not in st.session_state:
        st.session_state.kafka_manager = KafkaManager(KAFKA_CONFIG)

    if "kafka_messages" not in st.session_state:
        st.session_state.kafka_messages = []

    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = False


def show_connection_status():
    """Show connection status in sidebar"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Connection Status")

    # Test database connection
    try:
        st.session_state.db_manager.execute_query("SELECT 1")
        st.sidebar.success("✅ Database Connected")
    except Exception:
        st.sidebar.error("❌ Database Connection Failed")

    # Test Kafka connection
    try:
        consumer = st.session_state.kafka_manager.create_consumer(["__consumer_offsets"])
        if consumer:
            consumer.close()
            st.sidebar.success("✅ Kafka Connected")
        else:
            st.sidebar.error("❌ Kafka Connection Failed")
    except Exception:
        st.sidebar.error("❌ Kafka Connection Failed")


def create_navigation():
    """Create sidebar navigation"""
    st.sidebar.title("Navigation")
    return st.sidebar.selectbox(
        "Choose a page:",
        [
            "🏠 Dashboard",
            "👥 Customers",
            "📦 Products",
            "🛒 Orders",
            "📡 Kafka Monitor",
            "🧪 Batch Testing",
        ],
    )