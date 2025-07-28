"""
Batch testing page
"""
import streamlit as st
import time
import random


def show_batch_testing():
    """Show batch testing page"""
    st.header("🧪 Batch Testing")
    st.markdown("Generate multiple database operations to test CDC event handling")

    db_manager = st.session_state.db_manager

    # Batch customer creation
    st.subheader("Batch Customer Creation")

    with st.form("batch_customers"):
        col1, col2 = st.columns(2)

        with col1:
            customer_count = st.number_input(
                "Number of customers to create", min_value=1, max_value=100, value=10
            )

        with col2:
            customer_prefix = st.text_input("Name prefix", value="BatchCustomer")

        submit_customers = st.form_submit_button(
            "Create Batch Customers", type="primary"
        )

        if submit_customers:
            progress_bar = st.progress(0)
            status_text = st.empty()

            created_count = 0
            for i in range(customer_count):
                try:
                    name = f"{customer_prefix}_{int(time.time())}_{i}"
                    email = f"{name.lower()}@example.com"

                    query = "INSERT INTO customers (name, email) VALUES (%s, %s)"
                    result = db_manager.execute_query(query, (name, email), fetch=False)

                    if result:
                        created_count += 1

                    progress_bar.progress((i + 1) / customer_count)
                    status_text.text(f"Creating customer {i + 1}/{customer_count}")

                except Exception as e:
                    st.error(f"Error creating customer {i + 1}: {e}")

            st.success(f"✅ Created {created_count} customers successfully!")

    st.markdown("---")

    # Batch product creation
    st.subheader("Batch Product Creation")

    with st.form("batch_products"):
        col1, col2, col3 = st.columns(3)

        with col1:
            product_count = st.number_input(
                "Number of products to create", min_value=1, max_value=100, value=10
            )

        with col2:
            product_prefix = st.text_input("Product name prefix", value="BatchProduct")

        with col3:
            price_range = st.slider(
                "Price range", min_value=10, max_value=1000, value=(50, 500)
            )

        submit_products = st.form_submit_button("Create Batch Products", type="primary")

        if submit_products:
            progress_bar = st.progress(0)
            status_text = st.empty()

            created_count = 0
            for i in range(product_count):
                try:
                    name = f"{product_prefix}_{int(time.time())}_{i}"
                    price = round(random.uniform(price_range[0], price_range[1]), 2)

                    query = "INSERT INTO products (name, price) VALUES (%s, %s)"
                    result = db_manager.execute_query(query, (name, price), fetch=False)

                    if result:
                        created_count += 1

                    progress_bar.progress((i + 1) / product_count)
                    status_text.text(f"Creating product {i + 1}/{product_count}")

                except Exception as e:
                    st.error(f"Error creating product {i + 1}: {e}")

            st.success(f"✅ Created {created_count} products successfully!")

    st.markdown("---")

    # Batch order creation
    st.subheader("Batch Order Creation")

    customers_df = db_manager.get_table_data("customers")
    products_df = db_manager.get_table_data("products")

    if customers_df.empty or products_df.empty:
        st.warning("⚠️ You need customers and products to create orders")
    else:
        with st.form("batch_orders"):
            order_count = st.number_input(
                "Number of orders to create", min_value=1, max_value=100, value=20
            )

            submit_orders = st.form_submit_button("Create Batch Orders", type="primary")

            if submit_orders:
                progress_bar = st.progress(0)
                status_text = st.empty()

                customer_ids = customers_df["id"].tolist()
                product_ids = products_df["id"].tolist()

                created_count = 0
                for i in range(order_count):
                    try:
                        customer_id = random.choice(customer_ids)
                        product_id = random.choice(product_ids)
                        quantity = random.randint(1, 5)

                        query = "INSERT INTO orders (customer_id, product_id, quantity) VALUES (%s, %s, %s)"
                        result = db_manager.execute_query(
                            query, (customer_id, product_id, quantity), fetch=False
                        )

                        if result:
                            created_count += 1

                        progress_bar.progress((i + 1) / order_count)
                        status_text.text(f"Creating order {i + 1}/{order_count}")

                    except Exception as e:
                        st.error(f"Error creating order {i + 1}: {e}")

                st.success(f"✅ Created {created_count} orders successfully!")