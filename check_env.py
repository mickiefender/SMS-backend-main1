"""
Script to check if Supabase environment variables are properly loaded
Run this to verify your .env configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

print("=" * 60)
print("ENVIRONMENT VARIABLES CHECK")
print("=" * 60)

# Check Supabase variables
supabase_url = os.environ.get('SUPABASE_URL')
supabase_key = os.environ.get('SUPABASE_KEY')
supabase_service_key = os.environ.get('SUPABASE_SERVICE_KEY')
supabase_bucket = os.environ.get('SUPABASE_STORAGE_BUCKET', 'school-documents')
use_supabase = os.environ.get('USE_SUPABASE_STORAGE', 'False')

print(f"\nUSE_SUPABASE_STORAGE: {use_supabase}")
print(f"SUPABASE_URL: {'✓ Set' if supabase_url else '✗ NOT SET'}")
if supabase_url:
    print(f"  Value: {supabase_url}")

print(f"\nSUPABASE_KEY: {'✓ Set' if supabase_key else '✗ NOT SET'}")
if supabase_key:
    print(f"  Value: {supabase_key[:20]}... (truncated)")

print(f"\nSUPABASE_SERVICE_KEY: {'✓ Set' if supabase_service_key else '✗ NOT SET'}")
if supabase_service_key:
    print(f"  Value: {supabase_service_key[:20]}... (truncated)")

print(f"\nSUPABASE_STORAGE_BUCKET: {supabase_bucket}")

print("\n" + "=" * 60)
print("CONFIGURATION STATUS")
print("=" * 60)

if use_supabase == 'True':
    if supabase_url and (supabase_service_key or supabase_key):
        print("✓ Supabase storage is ENABLED and properly configured")
        print("\nYou can now upload files to Supabase!")
    else:
        print("✗ Supabase storage is ENABLED but MISSING credentials")
        print("\nRequired variables:")
        if not supabase_url:
            print("  - SUPABASE_URL")
        if not supabase_service_key and not supabase_key:
            print("  - SUPABASE_SERVICE_KEY (or SUPABASE_KEY)")
        print("\nPlease add these to your .env file")
else:
    print("ℹ Supabase storage is DISABLED (using local storage)")
    print("\nTo enable Supabase storage, set USE_SUPABASE_STORAGE=True in .env")

print("=" * 60)
