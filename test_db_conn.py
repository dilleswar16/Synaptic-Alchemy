import os
import psycopg
from urllib.parse import urlparse

from corvin.core.config_loader import get_env
from corvin.core.settings import load_settings

def test_connection():
    env = get_env()
    print(f"Environment: {env}")
    
    settings = load_settings(env)
    db_url = settings.storage.database_url
    
    # Parse URL to mask password
    parsed = urlparse(db_url)
    masked_url = db_url.replace(parsed.password, "*****") if parsed.password else db_url
    print(f"Trying to connect to: {masked_url}")
    print(f"Host: {parsed.hostname}")
    print(f"Port: {parsed.port or 5432}")
    
    try:
        # We try to connect directly using psycopg
        print("Attempting connection...")
        with psycopg.connect(db_url, connect_timeout=5) as conn:
            print("SUCCESS! Connected to the database.")
            
            # Run a simple query
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                print(f"Query test successful. Result: {cur.fetchone()}")
                
    except Exception as e:
        print(f"\nERROR: Failed to connect to the database.")
        print(f"Exception Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")

if __name__ == "__main__":
    test_connection()
