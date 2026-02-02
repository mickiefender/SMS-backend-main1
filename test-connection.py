import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

def test_database_connection():
    """Test the Supabase PostgreSQL connection"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()
        
        if result:
            print("✅ SUCCESS: Connected to Supabase PostgreSQL!")
            
            # Get database info
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT datname, pg_size_pretty(pg_database.pg_size(datname)) 
                    FROM pg_database 
                    WHERE datname = current_database();
                """)
                db_info = cursor.fetchone()
                if db_info:
                    print(f"   Database: {db_info[0]}")
                    print(f"   Size: {db_info[1]}")
            
            # Check tables
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = 'public';
                """)
                table_count = cursor.fetchone()[0]
                print(f"   Tables: {table_count}")
            
            if table_count == 0:
                print("\n⚠️  No tables found. You need to run the SQL setup script first!")
                print("   Go to Supabase Dashboard → SQL Editor → New Query")
                print("   Paste the contents of backend/scripts/000_complete_schema.sql and run it.")
            else:
                print(f"\n✅ Database has {table_count} tables. Ready to use!")
        
    except Exception as e:
        print(f"❌ ERROR: Could not connect to Supabase")
        print(f"   Error: {str(e)}")
        print("\n📝 Troubleshooting:")
        print("   1. Check your DATABASE_URL is correct in .env file")
        print("   2. Ensure your Supabase project is active")
        print("   3. Check your network connection")
        sys.exit(1)

if __name__ == '__main__':
    test_database_connection()
