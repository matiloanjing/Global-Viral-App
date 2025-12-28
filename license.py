"""
Kilat Code Clipper - License Management Module
Uses Supabase for license verification and activation.
"""

import os
import json
import hashlib
import platform
import subprocess
from typing import Optional, Dict, Tuple
from pathlib import Path

# Optional imports
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Supabase Configuration
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_ANON_KEY = "YOUR_ANON_KEY"

# Local license file location
LICENSE_FILE = Path.home() / ".kilat_code_clipper" / "license.dat"


def get_machine_id() -> str:
    """
    Generate unique machine ID from hardware components.
    Combines: Computer name + Windows SID + MAC address hash
    """
    try:
        components = []
        
        # Computer name
        components.append(platform.node())
        
        # Windows Machine GUID (unique per installation)
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ["wmic", "csproduct", "get", "UUID"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                uuid_line = [l for l in result.stdout.strip().split('\n') if l.strip() and 'UUID' not in l]
                if uuid_line:
                    components.append(uuid_line[0].strip())
            except Exception:
                pass
        
        # CPU info
        components.append(platform.processor())
        
        # Create hash
        combined = "|".join(components)
        machine_hash = hashlib.sha256(combined.encode()).hexdigest()[:32]
        
        return machine_hash
        
    except Exception:
        # Fallback to simple hash
        return hashlib.sha256(platform.node().encode()).hexdigest()[:32]


def check_license_online(license_key: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Check license key against Supabase database.
    Returns: (valid, message, license_data)
    """
    if not HAS_REQUESTS:
        return False, "Network library not available", None
    
    try:
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json"
        }
        
        # Query license
        url = f"{SUPABASE_URL}/rest/v1/licenses"
        params = {
            "license_key": f"eq.{license_key}",
            "select": "*"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code != 200:
            return False, f"Server error: {response.status_code}", None
        
        data = response.json()
        
        if not data:
            return False, "License key not found", None
        
        license_data = data[0]
        machine_id = get_machine_id()
        
        # Check if already activated
        if license_data.get('activated'):
            # Check if same machine
            if license_data.get('machine_id') == machine_id:
                return True, "License valid", license_data
            else:
                return False, "License already activated on another device", None
        
        # Not yet activated - this is fine
        return True, "License valid (not yet activated)", license_data
        
    except requests.exceptions.Timeout:
        return False, "Connection timeout. Check your internet.", None
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to server. Check your internet.", None
    except Exception as e:
        return False, f"Error: {str(e)}", None


def activate_license(license_key: str) -> Tuple[bool, str]:
    """
    Activate license key and bind to this machine.
    Returns: (success, message)
    """
    if not HAS_REQUESTS:
        return False, "Network library not available"
    
    try:
        from datetime import datetime, timezone
        machine_id = get_machine_id()
        
        headers = {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        # Update license with machine_id
        url = f"{SUPABASE_URL}/rest/v1/licenses"
        params = {
            "license_key": f"eq.{license_key}"
        }
        
        # Use proper ISO timestamp
        now = datetime.now(timezone.utc).isoformat()
        
        payload = {
            "activated": True,
            "machine_id": machine_id,
            "activated_at": now
        }
        
        response = requests.patch(url, headers=headers, params=params, json=payload, timeout=10)
        
        if response.status_code in [200, 201, 204]:
            # Save license locally
            save_local_license(license_key, machine_id)
            return True, "License activated successfully!"
        else:
            # Get error details
            try:
                error_data = response.json()
                error_msg = error_data.get('message', str(response.status_code))
            except:
                error_msg = str(response.status_code)
            return False, f"Activation failed: {error_msg}"
            
    except Exception as e:
        return False, f"Activation error: {str(e)}"


def save_local_license(license_key: str, machine_id: str):
    """Save license info locally for offline verification."""
    try:
        LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "license_key": license_key,
            "machine_id": machine_id,
            "verified": True
        }
        
        # Simple obfuscation (not encryption, just to deter casual tampering)
        encoded = hashlib.sha256(f"{license_key}:{machine_id}".encode()).hexdigest()
        data["checksum"] = encoded
        
        with open(LICENSE_FILE, 'w') as f:
            json.dump(data, f)
            
    except Exception:
        pass


def load_local_license() -> Optional[Dict]:
    """Load and verify local license cache."""
    try:
        if not LICENSE_FILE.exists():
            return None
        
        with open(LICENSE_FILE, 'r') as f:
            data = json.load(f)
        
        # Verify checksum
        license_key = data.get('license_key', '')
        machine_id = data.get('machine_id', '')
        stored_checksum = data.get('checksum', '')
        
        expected_checksum = hashlib.sha256(f"{license_key}:{machine_id}".encode()).hexdigest()
        
        if stored_checksum != expected_checksum:
            return None
        
        # Verify machine ID matches current
        current_machine = get_machine_id()
        if machine_id != current_machine:
            return None
        
        return data
        
    except Exception:
        return None


def verify_license() -> Tuple[bool, str]:
    """
    Main verification function called at app startup.
    1. Check local cache first
    2. If no cache or invalid, require online verification
    """
    # Check local cache
    local_license = load_local_license()
    
    if local_license:
        # Have valid local cache - optionally verify online
        license_key = local_license.get('license_key')
        
        # Try online verification (but don't block if offline)
        if HAS_REQUESTS:
            try:
                valid, message, _ = check_license_online(license_key)
                if valid:
                    return True, "License verified"
            except Exception:
                pass
        
        # Offline mode - trust local cache
        return True, "License valid (offline mode)"
    
    # No local cache - need activation
    return False, "License activation required"


def clear_local_license():
    """Remove local license file (for reset/deactivation)."""
    try:
        if LICENSE_FILE.exists():
            LICENSE_FILE.unlink()
    except Exception:
        pass
