"""
CDC Event Testing Dashboard
A Streamlit application for testing Change Data Capture events
in the ecommerce system.
"""

import streamlit as st
import psycopg2
import pandas as pd
import json
import time
import os
from datetime import datetime, timedelta
from kafka import KafkaConsumer
from typing import Dict, List

# Page config
st.set_page_config(
    page_title="CDC Event Testing Dashboard",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "ecommerce"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

# Kafka configuration
KAFKA_CONFIG = {
    "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093").split(
        ","
    ),
    "topics": {
        "customers": "pg.public.customers",
        "products": "pg.public.products",
        "orders": "pg.public.orders",
    },
}


class DatabaseManager:
    """Handle database operations"""

    def __init__(self, config: Dict):
        self.config = config
        self._connection = None

    @property
    def connection(self):
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(**self.config)
        return self._connection

    def execute_query(self, query: str, params=None, fetch=True):
        """Execute SQL query"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    columns = (
                        [desc[0] for desc in cursor.description]
                        if cursor.description
                        else []
                    )
                    rows = cursor.fetchall()
                    return (
                        pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame()
                    )
                else:
                    self.connection.commit()
                    return True
        except Exception as e:
            self.connection.rollback()
            st.error(f"Database error: {e}")
            return None

    def get_table_data(self, table: str) -> pd.DataFrame:
        """Get all data from a table"""
        query = f"SELECT * FROM {table} ORDER BY id"
        return self.execute_query(query)

    def get_table_count(self, table: str) -> int:
        """Get row count for a table"""
        query = f"SELECT COUNT(*) as count FROM {table}"
        result = self.execute_query(query)
        return result.iloc[0]["count"] if not result.empty else 0


class KafkaManager:
    """Handle Kafka operations"""

    def __init__(self, config: Dict):
        self.config = config
        self.consumer = None
        self.producer = None

    def create_consumer(self, topics: List[str], group_id: str = "streamlit-consumer", from_beginning: bool = False):
        """Create Kafka consumer"""
        try:
            # Use different group IDs for different modes
            if from_beginning:
                group_id = f"{group_id}-recent-{int(time.time())}"
                auto_offset_reset = 'earliest'
            else:
                auto_offset_reset = 'latest'
            
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self.config["bootstrap_servers"],
                group_id=group_id,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")) if x else None,
                key_deserializer=lambda x: x.decode("utf-8") if x else None,
                consumer_timeout_ms=2000,  # Increased timeout
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=True,
                auto_commit_interval_ms=1000
            )
            return consumer
        except Exception as e:
            st.error(f"Kafka consumer error: {e}")
            return None

    def consume_messages(self, topics: List[str], max_messages: int = 10, recent_only: bool = False) -> List[Dict]:
        """Consume latest messages from topics"""
        messages = []
        
        # For recent messages, use a temporary consumer with 'earliest' offset
        if recent_only:
            consumer = self.create_consumer(topics, from_beginning=True)
            target_time = datetime.now() - timedelta(minutes=5)  # Last 5 minutes
        else:
            consumer = self.create_consumer(topics, from_beginning=False)
            target_time = None

        if consumer:
            try:
                message_count = 0
                for message in consumer:
                    if message_count >= max_messages:
                        break
                    
                    message_time = datetime.fromtimestamp(message.timestamp / 1000)
                    
                    # Filter by time if recent_only
                    if recent_only and target_time and message_time < target_time:
                        continue
                    
                    messages.append({
                        "topic": message.topic,
                        "partition": message.partition,
                        "offset": message.offset,
                        "timestamp": message_time,
                        "key": message.key,
                        "value": message.value,
                    })
                    
                    message_count += 1

            except Exception as e:
                st.error(f"Error consuming messages: {e}")
            finally:
                consumer.close()
        
        # Sort by timestamp descending (newest first)
        messages.sort(key=lambda x: x['timestamp'], reverse=True)
        return messages

    def get_realtime_consumer(self, topics: List[str]) -> KafkaConsumer:
        """Get or create a persistent consumer for real-time monitoring"""
        try:
            if self.consumer is None or self.consumer.subscription() != set(topics):
                if self.consumer:
                    self.consumer.close()
                
                self.consumer = KafkaConsumer(
                    *topics,
                    bootstrap_servers=self.config["bootstrap_servers"],
                    group_id=f"streamlit-realtime-{int(time.time())}",
                    value_deserializer=lambda x: json.loads(x.decode("utf-8")) if x else None,
                    key_deserializer=lambda x: x.decode("utf-8") if x else None,
                    consumer_timeout_ms=100,  # Short timeout for real-time
                    auto_offset_reset='latest',
                    enable_auto_commit=False  # Don't commit for real-time monitoring
                )
            
            return self.consumer
        except Exception as e:
            st.error(f"Real-time consumer error: {e}")
            return None

    def poll_realtime_messages(self, topics: List[str], max_messages: int = 5) -> List[Dict]:
        """Poll for new messages in real-time"""
        messages = []
        consumer = self.get_realtime_consumer(topics)
        
        if consumer:
            try:
                # Poll for new messages
                message_batch = consumer.poll(timeout_ms=100)
                
                for topic_partition, records in message_batch.items():
                    for message in records[-max_messages:]:  # Get last N messages per partition
                        messages.append({
                            "topic": message.topic,
                            "partition": message.partition,
                            "offset": message.offset,
                            "timestamp": datetime.fromtimestamp(message.timestamp / 1000),
                            "key": message.key,
                            "value": message.value,
                        })
                        
                        if len(messages) >= max_messages:
                            break
                    
                    if len(messages) >= max_messages:
                        break
                        
            except Exception:
                # Silently handle polling errors for real-time
                pass
        
        return sorted(messages, key=lambda x: x['timestamp'], reverse=True)


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


def main():
    """Main application"""

    init_session_state()

    st.title("🔄 CDC Event Testing Dashboard")
    st.markdown("Test Change Data Capture events for the ecommerce system")

    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
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

    # Connection status
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
        consumer = st.session_state.kafka_manager.create_consumer(
            ["__consumer_offsets"]
        )
        if consumer:
            consumer.close()
            st.sidebar.success("✅ Kafka Connected")
        else:
            st.sidebar.error("❌ Kafka Connection Failed")
    except Exception:
        st.sidebar.error("❌ Kafka Connection Failed")

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
            customer_data = customers_df[customers_df["id"] == selected_customer].iloc[
                0
            ]

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


def show_kafka_monitor():
    """Show Kafka message monitor with real-time updates"""
    st.header("� Kafka CDC Messages Monitor")
    
    if "kafka_manager" not in st.session_state:
        st.warning("Kafka not initialized. Please go to Database Operations first.")
        return

    col1, col2 = st.columns([2, 1])
    
    with col1:
        topics = st.multiselect(
            "Select Topics to Monitor:",
            ["pg.public.customers", "pg.public.products", "pg.public.orders"],
            default=["pg.public.customers", "pg.public.products", "pg.public.orders"],
        )
    
    with col2:
        max_messages = st.number_input("Max Messages", min_value=1, max_value=50, value=10)
    
    # Real-time controls
    col3, col4, col5 = st.columns(3)
    
    with col3:
        if st.button("🔄 Refresh Recent Messages", type="primary"):
            st.session_state.refresh_messages = True
    
    with col4:
        auto_refresh = st.checkbox("Auto Refresh (5s)", value=False)
    
    with col5:
        show_recent_only = st.checkbox("Recent Only (5 min)", value=True)

    if auto_refresh:
        # Auto-refresh every 5 seconds
        time.sleep(5)
        st.rerun()
    
    if not topics:
        st.warning("Please select at least one topic to monitor.")
        return

    # Initialize refresh flag
    if "refresh_messages" not in st.session_state:
        st.session_state.refresh_messages = True
    
    # Load messages
    with st.spinner("Loading messages..."):
        if show_recent_only:
            messages = st.session_state.kafka_manager.consume_messages(
                topics, max_messages, recent_only=True
            )
        else:
            # For real-time monitoring, try polling first
            if auto_refresh:
                realtime_messages = st.session_state.kafka_manager.poll_realtime_messages(
                    topics, max_messages
                )
                if realtime_messages:
                    messages = realtime_messages
                else:
                    # Fallback to regular consumption
                    messages = st.session_state.kafka_manager.consume_messages(
                        topics, max_messages, recent_only=False
                    )
            else:
                messages = st.session_state.kafka_manager.consume_messages(
                    topics, max_messages, recent_only=False
                )

    # Reset refresh flag
    st.session_state.refresh_messages = False

    if messages:
        st.success(f"Found {len(messages)} messages")
        
        # Display summary
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Messages", len(messages))
        with col2:
            latest_time = max(msg['timestamp'] for msg in messages)
            st.metric("Latest Message", latest_time.strftime("%H:%M:%S"))
        with col3:
            unique_topics = len(set(msg['topic'] for msg in messages))
            st.metric("Active Topics", unique_topics)

        # Filter by topic for display
        selected_topic = st.selectbox(
            "Filter by Topic (for detailed view):",
            ["All"] + topics,
            index=0
        )
        
        display_messages = messages
        if selected_topic != "All":
            display_messages = [msg for msg in messages if msg['topic'] == selected_topic]

        # Display messages in expandable cards
        for i, message in enumerate(display_messages):
            time_diff = datetime.now() - message['timestamp']
            time_ago = f"{int(time_diff.total_seconds())}s ago" if time_diff.total_seconds() < 60 else f"{int(time_diff.total_seconds()/60)}m ago"
            
            # Color code by topic
            topic_colors = {
                "pg.public.customers": "🟦",
                "pg.public.products": "🟩", 
                "pg.public.orders": "🟨"
            }
            
            topic_icon = topic_colors.get(message['topic'], "⚪")
            
            with st.expander(
                f"{topic_icon} {message['topic']} | Offset: {message['offset']} | {time_ago}",
                expanded=(i < 3)  # Expand first 3 messages
            ):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.write("**Message Info:**")
                    st.write(f"- **Topic:** {message['topic']}")
                    st.write(f"- **Partition:** {message['partition']}")
                    st.write(f"- **Offset:** {message['offset']}")
                    st.write(f"- **Timestamp:** {message['timestamp']}")
                    if message['key']:
                        st.write(f"- **Key:** {message['key']}")
                
                with col2:
                    st.write("**Message Content:**")
                    if message['value']:
                        # Pretty print JSON
                        st.json(message['value'], expanded=False)
                    else:
                        st.write("*No content*")
    else:
        st.info("No messages found. Try:")
        st.write("- Make sure your CDC connector is running")
        st.write("- Perform some database operations to generate events")
        st.write("- Check if the topics exist in Kafka")
        
        # Show connection status
        try:
            consumer = st.session_state.kafka_manager.create_consumer(topics[:1] if topics else ["pg.public.customers"])
            if consumer:
                st.success("✅ Kafka connection established")
                consumer.close()
            else:
                st.error("❌ Cannot connect to Kafka")
        except Exception as e:
            st.error(f"❌ Kafka connection error: {e}")


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
            import random

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
                import random

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


if __name__ == "__main__":
    main()
