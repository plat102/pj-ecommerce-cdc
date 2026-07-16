"""
CDC Event Testing Dashboard
A Streamlit application for testing Change Data Capture events
in the ecommerce system.
"""
import streamlit as st

# Import configurations and utilities
from config.settings import STREAMLIT_CONFIG
from utils.helpers import init_session_state, show_connection_status, create_navigation

# Import page functions
from views.dashboard import show_dashboard
from views.customers import show_customers_page
from views.products import show_products_page
from views.orders import show_orders_page
from views.kafka_monitor import show_kafka_monitor
from views.batch_testing import show_batch_testing
from views.dlq_triage import show_dlq_triage

# Page config
st.set_page_config(**STREAMLIT_CONFIG)


def main():
    """Main application"""
    init_session_state()

    st.title("🔄 CDC Event Testing Dashboard")
    st.markdown("Test Change Data Capture events for the ecommerce system")

    # Sidebar navigation
    page = create_navigation()
    show_connection_status()

    # Route to different pages
    if page == "🏠 Dashboard":
        show_dashboard()
    elif page == "👥 Customers":
        show_customers_page()
    elif page == "📦 Products":
        show_products_page()
    elif page == "🛒 Orders":
        show_orders_page()
    elif page == "📡 Kafka Monitor":
        show_kafka_monitor()
    elif page == "🧪 Batch Testing":
        show_batch_testing()
    elif page == "🚨 DLQ Triage":
        show_dlq_triage()


if __name__ == "__main__":
    main()