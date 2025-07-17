#!/usr/bin/env python3
"""
Setup Global 2FA Password Script

This script helps administrators configure the global 2FA password 
required for the account selling system.
"""

import secrets
import string
from database.database import Database

def generate_secure_password(length=16):
    """Generate a secure random password"""
    # Use a combination of letters, digits, and special characters
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password

def main():
    print("🔐 Global 2FA Password Setup")
    print("=" * 40)
    
    # Initialize database
    try:
        db = Database()
        print("✅ Database connection established")
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return
    
    # Check current password
    current_password = db.get_global_2fa_password()
    if current_password:
        print(f"⚠️  Global 2FA password is already configured")
        print(f"Current password: {current_password[:4]}****")
        
        response = input("\nDo you want to update it? (y/N): ").lower().strip()
        if response != 'y':
            print("Operation cancelled.")
            return
    else:
        print("ℹ️  No global 2FA password configured")
    
    print("\nChoose an option:")
    print("1. Generate a secure random password (recommended)")
    print("2. Enter a custom password")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        # Generate secure password
        new_password = generate_secure_password()
        print(f"\n🔑 Generated secure password: {new_password}")
        print("⚠️  IMPORTANT: Save this password securely!")
        
    elif choice == "2":
        # Custom password
        while True:
            new_password = input("\nEnter your custom password: ").strip()
            if len(new_password) < 8:
                print("❌ Password must be at least 8 characters long")
                continue
            
            confirm_password = input("Confirm password: ").strip()
            if new_password != confirm_password:
                print("❌ Passwords don't match")
                continue
            break
    else:
        print("❌ Invalid choice")
        return
    
    # Confirm update
    print(f"\nPassword to set: {new_password[:4]}****")
    confirm = input("Confirm setting this password? (y/N): ").lower().strip()
    
    if confirm != 'y':
        print("Operation cancelled.")
        return
    
    # Update password
    try:
        success = db.update_global_2fa_password(new_password, 0)  # 0 = system/script
        if success:
            print("✅ Global 2FA password updated successfully!")
            print("\n📋 Next Steps:")
            print("1. Make sure to save the password securely")
            print("2. The bot can now process accounts with 2FA enabled")
            print("3. You can change this password anytime via Admin Panel → Bot Settings")
        else:
            print("❌ Failed to update global 2FA password")
    except Exception as e:
        print(f"❌ Error updating password: {e}")

if __name__ == "__main__":
    main()