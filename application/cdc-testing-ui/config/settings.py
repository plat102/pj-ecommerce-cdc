"""
Configuration settings for the CDC Testing Dashboard
"""
import os

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
    "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093").split(","),
    "topics": {
        "customers": "pg.public.customers",
        "products": "pg.public.products",
        "orders": "pg.public.orders",
    },
}

# Streamlit configuration
STREAMLIT_CONFIG = {
    "page_title": "CDC Event Testing Dashboard",
    "page_icon": "🔄",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}