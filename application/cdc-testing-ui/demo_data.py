#!/usr/bin/env python3
"""
Demo Data Generator for CDC Testing
Generates sample data to test CDC events
"""

import psycopg2
import random
import time

# Database config
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "ecommerce",
    "user": "postgres",
    "password": "postgres",
}

# Sample data
CUSTOMER_NAMES = [
    "Alice Johnson",
    "Bob Smith",
    "Charlie Brown",
    "Diana Prince",
    "Eva Green",
    "Frank Castle",
    "Grace Hopper",
    "Henry Ford",
    "Ivy Chen",
    "Jack Sparrow",
    "Kate Winslet",
    "Leo DiCaprio",
    "Mary Jane",
    "Nick Fury",
    "Olivia Pope",
]

PRODUCT_NAMES = [
    "Wireless Headphones",
    "Gaming Mouse",
    "Mechanical Keyboard",
    "4K Monitor",
    "Smartphone",
    "Tablet",
    "Laptop",
    "Desktop PC",
    "Graphics Card",
    "SSD Drive",
    "USB Cable",
    "Power Bank",
    "Bluetooth Speaker",
    "Smart Watch",
    "Camera",
]


def generate_customers(count=20):
    """Generate sample customers"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print(f"🧑‍🤝‍🧑 Generating {count} customers...")

    for i in range(count):
        name = random.choice(CUSTOMER_NAMES)
        email = f"{name.lower().replace(' ', '.')}_{i}@example.com"

        try:
            cursor.execute(
                "INSERT INTO customers (name, email) VALUES (%s, %s)",
                (f"{name} {i + 1}", email),
            )
            print(f"   ✅ Created customer: {name} {i + 1}")
        except Exception as e:
            print(f"   ❌ Error creating customer {i + 1}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Generated {count} customers\n")


def generate_products(count=15):
    """Generate sample products"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print(f"📦 Generating {count} products...")

    for i in range(count):
        name = random.choice(PRODUCT_NAMES)
        price = round(random.uniform(10.99, 999.99), 2)

        try:
            cursor.execute(
                "INSERT INTO products (name, price) VALUES (%s, %s)",
                (f"{name} v{i + 1}", price),
            )
            print(f"   ✅ Created product: {name} v{i + 1} - ${price}")
        except Exception as e:
            print(f"   ❌ Error creating product {i + 1}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Generated {count} products\n")


def generate_orders(count=50):
    """Generate sample orders"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Get available customers and products
    cursor.execute("SELECT id FROM customers")
    customer_ids = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT id FROM products")
    product_ids = [row[0] for row in cursor.fetchall()]

    if not customer_ids or not product_ids:
        print("❌ Need customers and products to generate orders")
        cursor.close()
        conn.close()
        return

    print(f"🛒 Generating {count} orders...")

    for i in range(count):
        customer_id = random.choice(customer_ids)
        product_id = random.choice(product_ids)
        quantity = random.randint(1, 5)

        try:
            cursor.execute(
                "INSERT INTO orders (customer_id, product_id, quantity) VALUES (%s, %s, %s)",
                (customer_id, product_id, quantity),
            )
            print(
                f"   ✅ Created order {i + 1}: Customer {customer_id} -> Product {product_id} (qty: {quantity})"
            )

            # Small delay to spread out timestamps
            time.sleep(0.1)

        except Exception as e:
            print(f"   ❌ Error creating order {i + 1}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Generated {count} orders\n")


def update_random_data():
    """Update some random data to generate UPDATE events"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("📝 Generating UPDATE events...")

    # Update 5 random customers
    cursor.execute("SELECT id, name FROM customers ORDER BY RANDOM() LIMIT 5")
    customers = cursor.fetchall()

    for customer_id, name in customers:
        new_name = f"{name} (Updated)"
        cursor.execute(
            "UPDATE customers SET name = %s WHERE id = %s", (new_name, customer_id)
        )
        print(f"   ✅ Updated customer {customer_id}: {new_name}")

    # Update 3 random products
    cursor.execute("SELECT id, price FROM products ORDER BY RANDOM() LIMIT 3")
    products = cursor.fetchall()

    for product_id, price in products:
        new_price = round(float(price) * random.uniform(0.8, 1.2), 2)
        cursor.execute(
            "UPDATE products SET price = %s WHERE id = %s", (new_price, product_id)
        )
        print(f"   ✅ Updated product {product_id}: ${new_price}")

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Generated UPDATE events\n")


def delete_some_data():
    """Delete some data to generate DELETE events"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("🗑️ Generating DELETE events...")

    # Delete customers without orders
    cursor.execute("""
        DELETE FROM customers 
        WHERE id IN (
            SELECT c.id FROM customers c 
            LEFT JOIN orders o ON c.id = o.customer_id 
            WHERE o.customer_id IS NULL 
            LIMIT 3
        )
        RETURNING id, name
    """)

    deleted_customers = cursor.fetchall()
    for customer_id, name in deleted_customers:
        print(f"   ✅ Deleted customer {customer_id}: {name}")

    # Delete products without orders
    cursor.execute("""
        DELETE FROM products 
        WHERE id IN (
            SELECT p.id FROM products p 
            LEFT JOIN orders o ON p.id = o.product_id 
            WHERE o.product_id IS NULL 
            LIMIT 2
        )
        RETURNING id, name
    """)

    deleted_products = cursor.fetchall()
    for product_id, name in deleted_products:
        print(f"   ✅ Deleted product {product_id}: {name}")

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Generated DELETE events\n")


def show_stats():
    """Show current database stats"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM customers")
    customer_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM products")
    product_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders")
    order_count = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    print("📊 Current Database Stats:")
    print(f"   👥 Customers: {customer_count}")
    print(f"   📦 Products: {product_count}")
    print(f"   🛒 Orders: {order_count}")
    print()


def main():
    print("🔄 CDC Demo Data Generator")
    print("=" * 40)

    try:
        # Test connection
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        print("✅ Database connection successful\n")

        # Show initial stats
        show_stats()

        # Generate data
        generate_customers(20)
        generate_products(15)
        generate_orders(50)

        # Generate some updates and deletes
        time.sleep(2)
        update_random_data()

        time.sleep(1)
        delete_some_data()

        # Show final stats
        show_stats()

        print("🎉 Demo data generation completed!")
        print("💡 Now you can:")
        print("   1. Open the CDC Testing UI: http://localhost:8501")
        print("   2. Monitor CDC events in Kafka Monitor")
        print("   3. Check Debezium UI: http://localhost:8085")
        print("   4. View Kafka topics: http://localhost:8080")

    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        print("💡 Make sure PostgreSQL is running: make up-db")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
