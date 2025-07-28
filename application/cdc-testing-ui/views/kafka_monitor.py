"""
Kafka monitoring page
"""
import streamlit as st
import time
from datetime import datetime


def show_kafka_monitor():
    """Show Kafka message monitor with real-time updates"""
    st.header("📡 Kafka CDC Messages Monitor")
    
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