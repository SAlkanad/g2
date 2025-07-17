#!/usr/bin/env python3
"""
Environment Setup Script for Account Market Bot
Helps generate secure configuration values
"""

import os
import secrets
import shutil
from pathlib import Path

def generate_encryption_key():
    """Generate a secure encryption key"""
    return secrets.token_hex(32)

def create_env_file():
    """Create .env file from template with some auto-generated values"""
    template_path = Path('.env.template')
    env_path = Path('.env')
    
    if not template_path.exists():
        print("❌ .env.template file not found!")
        return False
    
    if env_path.exists():
        response = input("📁 .env file already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("✅ Keeping existing .env file")
            return True
    
    # Read template
    with open(template_path, 'r') as f:
        content = f.read()
    
    # Generate secure values
    encryption_key = generate_encryption_key()
    
    # Replace placeholder values
    content = content.replace('your_64_character_hex_encryption_key', encryption_key)
    
    # Write .env file
    with open(env_path, 'w') as f:
        f.write(content)
    
    print("✅ .env file created successfully!")
    print(f"🔐 Generated secure encryption key: {encryption_key[:16]}...")
    return True

def check_required_files():
    """Check if required files exist"""
    files_to_check = [
        ('serviceAccountKey.json', 'Firebase service account key'),
    ]
    
    missing_files = []
    for file_path, description in files_to_check:
        if not Path(file_path).exists():
            missing_files.append((file_path, description))
    
    if missing_files:
        print("\n⚠️  Missing required files:")
        for file_path, description in missing_files:
            print(f"   • {file_path} - {description}")
        print("\n📝 Instructions:")
        print("   1. Go to Firebase Console > Project Settings > Service Accounts")
        print("   2. Click 'Generate new private key'")
        print("   3. Save the file as 'serviceAccountKey.json' in this directory")
        return False
    
    return True

def validate_env_values():
    """Validate that required environment variables are set"""
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = {
        'BOT_TOKEN': 'Telegram bot token from @BotFather',
        'API_ID': 'Telegram API ID from my.telegram.org',
        'API_HASH': 'Telegram API hash from my.telegram.org',
        'ADMIN_IDS': 'Your Telegram user ID (comma-separated for multiple admins)',
        'SESSION_ENCRYPTION_KEY': 'Encryption key for secure session storage'
    }
    
    missing_vars = []
    placeholder_vars = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value:
            missing_vars.append((var, description))
        elif value.startswith('your_') or value in ['your_bot_token_from_botfather', 'your_api_id_from_my_telegram_org']:
            placeholder_vars.append((var, description))
    
    if missing_vars or placeholder_vars:
        print("\n❌ Environment configuration issues:")
        
        if missing_vars:
            print("\n   Missing variables:")
            for var, desc in missing_vars:
                print(f"   • {var}: {desc}")
        
        if placeholder_vars:
            print("\n   Placeholder values need to be replaced:")
            for var, desc in placeholder_vars:
                print(f"   • {var}: {desc}")
        
        print(f"\n📝 Please edit the .env file and set these values")
        return False
    
    print("✅ All required environment variables are set!")
    return True

def main():
    """Main setup function"""
    print("🔧 Account Market Bot - Environment Setup")
    print("=" * 50)
    
    # Step 1: Create .env file
    print("\n1️⃣ Creating environment configuration...")
    if not create_env_file():
        return False
    
    # Step 2: Check required files
    print("\n2️⃣ Checking required files...")
    files_ok = check_required_files()
    
    # Step 3: Validate environment
    print("\n3️⃣ Validating environment configuration...")
    env_ok = validate_env_values()
    
    # Summary
    print("\n" + "=" * 50)
    if files_ok and env_ok:
        print("🎉 Setup completed successfully!")
        print("🚀 You can now start the bot with: python number_market_bot.py")
    else:
        print("⚠️  Setup incomplete. Please address the issues above.")
        print("💡 After fixing the issues, run this script again to validate.")
    
    return files_ok and env_ok

if __name__ == "__main__":
    main()