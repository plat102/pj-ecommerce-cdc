"""
Orders management page
"""
import streamlit as st
import time


def show_orders_page():
    """Show orders management page"""
    st.header("🛒 Orders Management")

    db_manager = st.session_state.db_manager

    # Current orders with joins
    st.subheader("Current Orders")

    orders_query = """
    SELECT 
        o.id, o.quantity, o.order_time,
        c.name as customer_name, c.email as customer_email,
        p.name as product_name, p.price as product_price,
        (o.quantity * p.price) as total_amount
    FROM orders o
    JOIN customers c ON o.customer_id = c.id
    JOIN products p ON o.product_id = p.id
    ORDER BY o.order_time DESC
    """

    orders_df = db_manager.execute_query(orders_query)

    if not orders_df.empty:
        st.dataframe(orders_df, use_container_width=True)
    else:
        st.info("No orders found")

    st.markdown("---")

    # Create new order
    st.subheader("Create New Order")

    # Get customers and products for dropdowns
    customers_df = db_manager.get_table_data("customers")
    products_df = db_manager.get_table_data("products")

    if customers_df.empty or products_df.empty:
        st.warning(
            "⚠️ You need at least one customer and one product to create an order"
        )
    else:
        with st.form("create_order"):
            col1, col2, col3 = st.columns(3)

            with col1:
                selected_customer = st.selectbox(
                    "Customer:",
                    options=customers_df["id"].tolist(),
                    format_func=lambda x: f"{customers_df[customers_df['id'] == x]['name'].iloc[0]}",
                )

            with col2:
                selected_product = st.selectbox(
                    "Product:",
                    options=products_df["id"].tolist(),
                    format_func=lambda x: f"{products_df[products_df['id'] == x]['name'].iloc[0]} (${products_df[products_df['id'] == x]['price'].iloc[0]})",
                )

            with col3:
                quantity = st.number_input("Quantity", min_value=1, value=1)

            submit_create = st.form_submit_button("Create Order", type="primary")

            if submit_create:
                query = "INSERT INTO orders (customer_id, product_id, quantity) VALUES (%s, %s, %s)"
                result = db_manager.execute_query(
                    query, (selected_customer, selected_product, quantity), fetch=False
                )

                if result:
                    st.success("✅ Order created successfully!")
                    time.sleep(1)
                    st.rerun()