#!/usr/bin/env python3
"""
Initialize production database with PostgreSQL schema
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def init_production_db():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL not found in environment variables")
        return False
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Read and execute schema
        with open('postgresql_schema.sql', 'r') as f:
            schema = f.read()
        
        cur.execute(schema)
        conn.commit()
        
        print("Database initialized successfully!")
        return True
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    init_production_db()