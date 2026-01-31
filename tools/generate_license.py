
import requests
import uuid
import sys
import random
import string

# Supabase Config
SUPABASE_URL = "https://rpmtfgntofxtxwmjpcxk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJwbXRmZ250b2Z4dHh3bWpwY3hrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU2Mzg2NzAsImV4cCI6MjA4MTIxNDY3MH0.AB33Qk3WjxnbYlCrvrkdGMJLujgIHki0o8Fprfodvpw"

def generate_key(prefix="KILAT", year="2025"):
    """Generate a random license key format: KILAT-2025-XXXX-XXXX"""
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=4))
    part2 = ''.join(random.choices(chars, k=4))
    return f"{prefix}-{year}-{part1}-{part2}"

def create_license(key, email=None):
    url = f"{SUPABASE_URL}/rest/v1/licenses"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    data = {
        "license_key": key,
        "activated": False
    }
    if email:
        data["email"] = email
        
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        print(f"✅ Created: {key}")
        return True
    else:
        print(f"❌ Failed: {response.text}")
        return False

def main():
    print("⚡ Kilat Code Clipper - License Generator")
    print("-" * 40)
    
    count = int(input("How many licenses to generate? (default 1): ") or "1")
    email = input("Assign to email (optional): ").strip() or None
    
    print("\nGenerating...")
    
    created = 0
    for _ in range(count):
        key = generate_key()
        if create_license(key, email):
            created += 1
            
    print("-" * 40)
    print(f"Done! {created} licenses created.")

if __name__ == "__main__":
    main()
