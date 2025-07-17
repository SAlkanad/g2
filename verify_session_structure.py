#!/usr/bin/env python3
"""
Verify that the bot uses only session_files structure
"""

import os
from sessions.session_paths import get_session_paths

def verify_session_structure():
    """Verify that all session directories are within session_files"""
    
    print("🔍 Verifying session directory structure...")
    print("=" * 50)
    
    # Get centralized session paths
    session_paths = get_session_paths()
    all_paths = session_paths.get_all_paths()
    
    print(f"📁 Base session directory: {session_paths.sessions_dir}")
    print(f"📂 All session directories:")
    
    for name, path in all_paths.items():
        # Check if path exists
        exists = "✅" if os.path.exists(path) else "❌"
        # Check if path is within session_files
        is_within_session_files = path.startswith(session_paths.sessions_dir)
        structure_ok = "✅" if is_within_session_files else "❌"
        
        print(f"   {exists} {structure_ok} {name}: {path}")
    
    # Check for any unwanted directories at root level
    print(f"\n🔍 Checking for unwanted directories at root level...")
    
    unwanted_patterns = ['approved_accounts', 'pending_accounts', 'rejected_accounts', 'temp']
    found_unwanted = []
    
    for item in os.listdir('.'):
        if os.path.isdir(item) and any(pattern in item for pattern in unwanted_patterns):
            found_unwanted.append(item)
    
    if found_unwanted:
        print(f"❌ Found unwanted directories: {found_unwanted}")
        return False
    else:
        print("✅ No unwanted directories found")
    
    # Summary
    all_within_session_files = all(path.startswith(session_paths.sessions_dir) for path in all_paths.values())
    
    print(f"\n" + "=" * 50)
    if all_within_session_files and not found_unwanted:
        print("🎉 SUCCESS: All directories are properly organized under session_files/")
        return True
    else:
        print("❌ ISSUES: Some directories are not properly organized")
        return False

if __name__ == "__main__":
    success = verify_session_structure()
    exit(0 if success else 1)