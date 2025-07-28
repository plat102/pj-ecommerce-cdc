"""
Customers management page
"""
import streamlit as st
import time


def show_customers_page():
    """Show customers management page"""
    st.header("👥 Customers Management")

    db_manager = st.session_state.db_manager

    # Current customers
    st.subheader("Current Customers")
    customers_df = db_manager.get_table_data("customers")

    if not customers_df.empty:
        st.dataframe(customers_df, use_container_width=True)
    else:
        st.info("No customers found")

    st.markdown("---")

    # Create new customer
    st.subheader("Create New Customer")

    with st.form("create_customer"):
        col1, col2 = st.columns(2)

        with col1:
            customer_name = st.text_input(
                "Customer Name", placeholder="Enter customer name"
            )

        with col2:
            customer_email = st.text_input("Email", placeholder="customer@example.com")

        submit_create = st.form_submit_button("Create Customer", type="primary")

        if submit_create and customer_name and customer_email:
            query = "INSERT INTO customers (name, email) VALUES (%s, %s)"
            result = db_manager.execute_query(
                query, (customer_name, customer_email), fetch=False
            )

            if result:
                st.success(f"✅ Customer '{customer_name}' created successfully!")
                time.sleep(1)
                st.rerun()

    # Update customer
    if not customers_df.empty:
        st.markdown("---")
        st.subheader("Update Customer")

        selected_customer = st.selectbox(
            "Select customer to update:",
            options=customers_df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {customers_df[customers_df['id'] == x]['name'].iloc[0]}",
        )

        if selected_customer:
            customer_data = customers_df[customers_df["id"] == selected_customer].iloc[0]

            with st.form("update_customer"):
                col1, col2 = st.columns(2)

                with col1:
                    new_name = st.text_input("New Name", value=customer_data["name"])

                with col2:
                    new_email = st.text_input("New Email", value=customer_data["email"])

                col1, col2 = st.columns(2)

                with col1:
                    submit_update = st.form_submit_button(
                        "Update Customer", type="primary"
                    )

                with col2:
                    submit_delete = st.form_submit_button(
                        "Delete Customer", type="secondary"
                    )

                if submit_update and new_name and new_email:
                    query = "UPDATE customers SET name = %s, email = %s WHERE id = %s"
                    result = db_manager.execute_query(
                        query, (new_name, new_email, selected_customer), fetch=False
                    )

                    if result:
                        st.success("✅ Customer updated successfully!")
                        time.sleep(1)
                        st.rerun()

                if submit_delete:
                    # Check if customer has orders
                    orders_check = db_manager.execute_query(
                        "SELECT COUNT(*) as count FROM orders WHERE customer_id = %s",
                        (selected_customer,),
                    )

                    if orders_check.iloc[0]["count"] > 0:
                        st.error("❌ Cannot delete customer with existing orders")
                    else:
                        query = "DELETE FROM customers WHERE id = %s"
                        result = db_manager.execute_query(
                            query, (selected_customer,), fetch=False
                        )

                        if result:
                            st.success("✅ Customer deleted successfully!")
                            time.sleep(1)
                            st.rerun()