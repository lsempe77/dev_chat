"""Add Zotero-compatible columns to documents table."""
import psycopg2
import os

# New columns to add for Zotero compatibility
COLUMNS_TO_ADD = [
    # item_type already exists
    ("isbn", "VARCHAR(50)"),
    ("issn", "VARCHAR(50)"),
    ("url", "TEXT"),
    ("publication", "VARCHAR(500)"),  # Journal name (Zotero: publicationTitle)
    ("volume", "VARCHAR(50)"),
    ("issue", "VARCHAR(50)"),
    ("pages", "VARCHAR(100)"),
    ("edition", "VARCHAR(100)"),
    ("place", "VARCHAR(255)"),  # Publication place
    ("series", "VARCHAR(500)"),
    ("series_number", "VARCHAR(50)"),
    ("book_title", "VARCHAR(500)"),  # For book sections
    ("num_pages", "INTEGER"),  # Total pages
    ("institution", "VARCHAR(500)"),  # Report institution or thesis university
    ("report_number", "VARCHAR(100)"),
    ("report_type", "VARCHAR(100)"),
    ("thesis_type", "VARCHAR(100)"),
    ("conference_name", "VARCHAR(500)"),
    ("proceedings_title", "VARCHAR(500)"),
    ("accessed_date", "VARCHAR(50)"),
]

def add_columns():
    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres:FKUVXTGWDmCbGvvynzmrMSmtZwBbSfGJ@autorack.proxy.rlwy.net:48572/railway?sslmode=require")
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        
        for col_name, col_type in COLUMNS_TO_ADD:
            try:
                cur.execute(f'ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col_name} {col_type}')
                print(f"✅ Column '{col_name}' added/verified")
            except Exception as e:
                print(f"⚠️ Column '{col_name}': {e}")
        
        conn.commit()
        print("\n✅ All Zotero columns migration completed!")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_columns()
