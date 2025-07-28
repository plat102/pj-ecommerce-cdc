"""
Products management page
"""
import streamlit as st
import time


def show_products_page():
    """Show products management page"""
    st.header("📦 Products Management")

    db_manager = st.session_state.db_manager

    # Current products
    st.subheader("Current Products")
    products_df = db_manager.get_table_data("products")

    if not products_df.empty:
        st.dataframe(products_df, use_container_width=True)
    else:
        st.info("No products found")

    st.markdown("---")

    # Create new product
    st.subheader("Create New Product")

    with st.form("create_product"):
        col1, col2 = st.columns(2)

        with col1:
            product_name = st.text_input(
                "Product Name", placeholder="Enter product name"
            )

        with col2:
            product_price = st.number_input(
                "Price", min_value=0.01, step=0.01, format="%.2f"
            )

        submit_create = st.form_submit_button("Create Product", type="primary")

        if submit_create and product_name and product_price:
            query = "INSERT INTO products (name, price) VALUES (%s, %s)"
            result = db_manager.execute_query(
                query, (product_name, product_price), fetch=False
            )

            if result:
                st.success(f"✅ Product '{product_name}' created successfully!")
                time.sleep(1)
                st.rerun()

    # Update product
    if not products_df.empty:
        st.markdown("---")
        st.subheader("Update Product")

        selected_product = st.selectbox(
            "Select product to update:",
            options=products_df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {products_df[products_df['id'] == x]['name'].iloc[0]}",
        )

        if selected_product:
            product_data = products_df[products_df["id"] == selected_product].iloc[0]

            with st.form("update_product"):
                col1, col2 = st.columns(2)

                with col1:
                    new_name = st.text_input("New Name", value=product_data["name"])

                with col2:
                    new_price = st.number_input(
                        "New Price",
                        value=float(product_data["price"]),
                        min_value=0.01,
                        step=0.01,
                    )

                col1, col2 = st.columns(2)

                with col1:
                    submit_update = st.form_submit_button(
                        "Update Product", type="primary"
                    )

                with col2:
                    submit_delete = st.form_submit_button(
                        "Delete Product", type="secondary"
                    )

                if submit_update and new_name and new_price:
                    query = "UPDATE products SET name = %s, price = %s WHERE id = %s"
                    result = db_manager.execute_query(
                        query, (new_name, new_price, selected_product), fetch=False
                    )

                    if result:
                        st.success("✅ Product updated successfully!")
                        time.sleep(1)
                        st.rerun()

                if submit_delete:
                    # Check if product has orders
                    orders_check = db_manager.execute_query(
                        "SELECT COUNT(*) as count FROM orders WHERE product_id = %s",
                        (selected_product,),
                    )

                    if orders_check.iloc[0]["count"] > 0:
                        st.error("❌ Cannot delete product with existing orders")
                    else:
                        query = "DELETE FROM products WHERE id = %s"
                        result = db_manager.execute_query(
                            query, (selected_product,), fetch=False
                        )

                        if result:
                            st.success("✅ Product deleted successfully!")
                            time.sleep(1)
                            st.rerun()