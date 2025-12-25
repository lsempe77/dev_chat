"""Add item_type column to documents table."""
import psycopg2
import os

def add_column():
    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:FKUVXTGWDmCbGvvynzmrMSmtZwBbSfGJ@autorack.proxy.rlwy.net:48572/railway?sslmode=require")
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute('ALTER TABLE documents ADD COLUMN IF NOT EXISTS item_type VARCHAR(100)')
        conn.commit()
        print("✅ Column 'item_type' added successfully!")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_column()
