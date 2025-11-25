#!/usr/bin/env python3
import psycopg2
import os
from urllib.parse import urlparse

def create_database():
    """Initialize PostgreSQL database with schema"""
    
    # Database URL from environment or default
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/voxiscribe')
    
    try:
        # Parse database URL
        url = urlparse(database_url)
        
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host=url.hostname,
            port=url.port or 5432,
            user=url.username,
            password=url.password,
            database=url.path[1:] if url.path else 'postgres'
        )
        
        conn.autocommit = True
        cur = conn.cursor()
        
        # Read and execute schema
        with open('database/postgresql_schema.sql', 'r') as f:
            schema_sql = f.read()
        
        cur.execute(schema_sql)
        print("✅ Database schema created successfully!")
        
        # Create default admin user
        cur.execute("""
            INSERT INTO users (username, password, role) 
            VALUES ('admin', 'admin123', 'teacher')
            ON CONFLICT (username) DO NOTHING
        """)
        
        print("✅ Default admin user created (username: admin, password: admin123)")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

if __name__ == "__main__":
    create_database()