"""
Dashboard page - System overview and recent activity
"""
import streamlit as st
from config.settings import KAFKA_CONFIG


def show_dashboard():
    """Show main dashboard"""
    st.header("System Overview")

    # Metrics
    col1, col2, col3, col4 = st.columns(4)

    db_manager = st.session_state.db_manager

    with col1:
        customers_count = db_manager.get_table_count("customers")
        st.metric("Customers", customers_count)

    with col2:
        products_count = db_manager.get_table_count("products")
        st.metric("Products", products_count)

    with col3:
        orders_count = db_manager.get_table_count("orders")
        st.metric("Orders", orders_count)

    with col4:
        st.metric("CDC Topics", 3)

    # Recent activity
    st.subheader("Recent Database Activity")

    # Get recent orders with customer and product info
    recent_orders_query = """
    SELECT 
        o.id, o.quantity, o.order_time,
        c.name as customer_name, c.email as customer_email,
        p.name as product_name, p.price as product_price
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    JOIN products p ON o.product_id = p.id
    ORDER BY o.order_time DESC
    LIMIT 10
    """

    recent_orders = db_manager.execute_query(recent_orders_query)

    if not recent_orders.empty:
        st.dataframe(recent_orders, use_container_width=True)
    else:
        st.info("No recent orders found")

    # Kafka messages preview
    st.subheader("Recent CDC Events")

    topics = list(KAFKA_CONFIG["topics"].values())
    recent_messages = st.session_state.kafka_manager.consume_messages(
        topics, max_messages=5
    )

    if recent_messages:
        for msg in recent_messages:
            with st.expander(
                f"📡 {msg['topic']} - {msg['timestamp'].strftime('%H:%M:%S')}"
            ):
                st.json(msg["value"])
    else:
        st.info("No recent CDC events found")