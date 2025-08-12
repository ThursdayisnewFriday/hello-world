#!/usr/bin/env python3
"""
Jamf License Reclamation System - Demo Script
Demonstrates the system functionality with sample data
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
import json

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_demo_config():
    """Create demo configuration files"""
    print("🔧 Creating demo configuration...")
    
    # Create demo config.ini
    config_content = """[JAMF]
server_url = https://demo.jamfcloud.com
username = demo_user
password = demo_password

[LICENSE_RECLAMATION]
inactive_days_threshold = 90
grace_period_days = 7
max_reclaims_per_run = 5

[NOTIFICATIONS]
smtp_server = smtp.demo.com
smtp_port = 587
email_username = demo@company.com
email_password = demo_password
admin_email = admin@company.com

[LOGGING]
log_level = INFO
log_file = demo_jamf_license_reclamation.log
max_log_size_mb = 10
backup_count = 3

[SCHEDULE]
run_frequency = weekly
run_time = 02:00
run_days = 1,3,5
"""
    
    with open('demo_config.ini', 'w') as f:
        f.write(config_content)
    
    # Create demo .env
    env_content = """# Demo Environment Variables
JAMF_SERVER_URL=https://demo.jamfcloud.com
JAMF_USERNAME=demo_user
JAMF_PASSWORD=demo_password
ADMIN_EMAIL=admin@company.com
DRY_RUN=true
LOG_LEVEL=INFO
"""
    
    with open('demo.env', 'w') as f:
        f.write(env_content)
    
    print("✅ Demo configuration created")

def run_config_validation_demo():
    """Demonstrate configuration validation"""
    print("\n📋 Configuration Validation Demo")
    print("-" * 40)
    
    try:
        from config_manager import ConfigManager
        
        config_manager = ConfigManager('demo_config.ini', 'demo.env')
        validation = config_manager.validate_config()
        
        print(f"Configuration loaded from: demo_config.ini")
        print(f"Environment loaded from: demo.env")
        
        if validation['errors']:
            print("\n❌ Configuration Errors:")
            for error in validation['errors']:
                print(f"  - {error}")
        else:
            print("\n✅ No configuration errors found")
        
        if validation['warnings']:
            print("\n⚠️  Configuration Warnings:")
            for warning in validation['warnings']:
                print(f"  - {warning}")
        else:
            print("✅ No configuration warnings")
        
        print("\n📊 Configuration Summary:")
        all_config = config_manager.get_all_config()
        print(f"  - Jamf Server: {all_config['jamf']['server_url']}")
        print(f"  - Inactive Threshold: {all_config['license_reclamation']['inactive_days_threshold']} days")
        print(f"  - Grace Period: {all_config['license_reclamation']['grace_period_days']} days")
        print(f"  - Max Reclaims per Run: {all_config['license_reclamation']['max_reclaims_per_run']}")
        print(f"  - Dry Run Mode: {all_config['dry_run']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def run_notification_demo():
    """Demonstrate notification system"""
    print("\n📧 Notification System Demo")
    print("-" * 40)
    
    try:
        from notification_service import NotificationService
        
        # Create demo notification service (won't actually send emails)
        notification_service = NotificationService(
            smtp_server="demo.smtp.com",
            smtp_port=587,
            email_username="demo@company.com",
            email_password="demo_password",
            admin_email="admin@company.com"
        )
        
        # Create sample computer data
        sample_computers = [
            {
                'id': 101,
                'name': 'John-MacBook-Pro',
                'serial_number': 'ABC123456',
                'last_contact': datetime.now() - timedelta(days=95),
                'days_inactive': 95,
                'user_info': {
                    'real_name': 'John Doe',
                    'email_address': 'john.doe@company.com',
                    'department': 'Engineering'
                }
            },
            {
                'id': 102,
                'name': 'Jane-MacBook-Air',
                'serial_number': 'XYZ789012',
                'last_contact': datetime.now() - timedelta(days=120),
                'days_inactive': 120,
                'user_info': {
                    'real_name': 'Jane Smith',
                    'email_address': 'jane.smith@company.com',
                    'department': 'Marketing'
                }
            }
        ]
        
        # Generate sample email content
        print("📝 Generating sample grace period notification...")
        email_content = notification_service._generate_grace_period_email(sample_computers)
        
        # Save to file for inspection
        with open('demo_grace_period_email.html', 'w') as f:
            f.write(email_content)
        
        print("✅ Sample email saved to: demo_grace_period_email.html")
        
        # Generate CSV report
        print("📊 Generating CSV report...")
        csv_content = notification_service._generate_csv_report(sample_computers)
        
        with open('demo_inactive_devices.csv', 'w') as f:
            f.write(csv_content)
        
        print("✅ CSV report saved to: demo_inactive_devices.csv")
        
        # Generate reclamation email
        reclaimed_computers = [sample_computers[0]]  # First computer was reclaimed
        failed_computers = [
            {
                **sample_computers[1],
                'status': 'failed',
                'error': 'Network timeout during API call'
            }
        ]
        
        reclamation_email = notification_service._generate_reclamation_email(
            reclaimed_computers, failed_computers
        )
        
        with open('demo_reclamation_email.html', 'w') as f:
            f.write(reclamation_email)
        
        print("✅ Reclamation email saved to: demo_reclamation_email.html")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def run_database_demo():
    """Demonstrate database operations"""
    print("\n🗄️  Database Operations Demo")
    print("-" * 40)
    
    try:
        from license_reclamation_service import LicenseReclamationService
        from unittest.mock import Mock
        
        # Create temporary database
        import tempfile
        db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_file.close()
        
        # Mock dependencies
        mock_jamf_client = Mock()
        mock_notification_service = Mock()
        
        # Initialize service (this creates the database)
        service = LicenseReclamationService(
            jamf_client=mock_jamf_client,
            notification_service=mock_notification_service,
            database_path=db_file.name
        )
        
        print(f"✅ Database created at: {db_file.name}")
        
        # Add some demo grace period entries
        import sqlite3
        with sqlite3.connect(db_file.name) as conn:
            cursor = conn.cursor()
            
            # Insert demo data
            demo_entries = [
                (201, 'Marketing-MacBook-1', 'MKT001', None, 95, 
                 (datetime.now() - timedelta(days=2)).isoformat(),
                 (datetime.now() + timedelta(days=5)).isoformat(),
                 '{"real_name": "Alice Johnson", "email": "alice@company.com"}'),
                (202, 'Sales-MacBook-2', 'SLS002', 
                 (datetime.now() - timedelta(days=100)).isoformat(), 100,
                 (datetime.now() - timedelta(days=3)).isoformat(),
                 (datetime.now() + timedelta(days=4)).isoformat(),
                 '{"real_name": "Bob Wilson", "email": "bob@company.com"}'),
                (203, 'HR-MacBook-3', 'HR003',
                 (datetime.now() - timedelta(days=130)).isoformat(), 130,
                 (datetime.now() - timedelta(days=8)).isoformat(),
                 (datetime.now() - timedelta(days=1)).isoformat(),  # Expired
                 '{"real_name": "Carol Brown", "email": "carol@company.com"}')
            ]
            
            for entry in demo_entries:
                cursor.execute('''
                    INSERT INTO grace_periods 
                    (computer_id, computer_name, serial_number, last_contact,
                     days_inactive, grace_start_date, grace_end_date, user_info, notified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', entry + (True,))
            
            conn.commit()
        
        print("✅ Demo data inserted into database")
        
        # Show grace period status
        grace_status = service.get_grace_period_status()
        print(f"\n📊 Grace Period Status ({len(grace_status)} devices):")
        
        for device in grace_status:
            status_icon = "⏰" if not device['expired'] else "🔴"
            print(f"  {status_icon} {device['computer_name']} ({device['serial_number']})")
            print(f"     Days remaining: {device['days_remaining']}")
            print(f"     Expired: {device['expired']}")
            print()
        
        # Add some reclamation history
        with sqlite3.connect(db_file.name) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO reclamation_history 
                (computer_id, computer_name, serial_number, last_contact,
                 days_inactive, user_info, reclamation_date, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                301, 'Old-MacBook-1', 'OLD001',
                (datetime.now() - timedelta(days=150)).isoformat(), 150,
                '{"real_name": "David Lee", "email": "david@company.com"}',
                (datetime.now() - timedelta(days=1)).isoformat(), True
            ))
            
            conn.commit()
        
        # Show reclamation history
        history = service.get_reclamation_history(days=7)
        print(f"📈 Recent Reclamation History ({len(history)} entries):")
        
        for entry in history:
            status_icon = "✅" if entry['success'] else "❌"
            print(f"  {status_icon} {entry['computer_name']} ({entry['serial_number']})")
            print(f"     Reclaimed: {entry['reclamation_date']}")
            print()
        
        # Cleanup
        os.unlink(db_file.name)
        print("✅ Demo database cleaned up")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def run_dry_run_demo():
    """Demonstrate dry run functionality"""
    print("\n🔍 Dry Run Demo")
    print("-" * 40)
    
    try:
        from main import JamfLicenseReclamationApp
        
        # Set dry run mode
        os.environ['DRY_RUN'] = 'true'
        
        app = JamfLicenseReclamationApp('demo_config.ini', 'demo.env')
        
        # Setup basic logging to console only
        import logging
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        app.logger = logging.getLogger()
        
        print("🧪 Running in DRY RUN mode...")
        
        # Validate configuration
        if app.validate_configuration():
            print("✅ Configuration validation passed")
            
            # Show status (without initializing services)
            print("\n📊 System Status:")
            print("  - Configuration: Valid")
            print("  - Mode: Dry Run")
            print("  - Jamf Server: https://demo.jamfcloud.com")
            print("  - Inactive Threshold: 90 days")
            print("  - Grace Period: 7 days")
            
            print("\n💡 In dry run mode, the system would:")
            print("  1. Connect to Jamf Pro API")
            print("  2. Identify computers inactive for >90 days")
            print("  3. Add new devices to 7-day grace period")
            print("  4. Send notifications about grace period devices")
            print("  5. Simulate license reclamation for expired devices")
            print("  6. Generate reports and logs")
            print("  7. NO ACTUAL LICENSES WOULD BE RECLAIMED")
            
        else:
            print("❌ Configuration validation failed")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def cleanup_demo_files():
    """Clean up demo files"""
    print("\n🧹 Cleaning up demo files...")
    
    demo_files = [
        'demo_config.ini',
        'demo.env',
        'demo_grace_period_email.html',
        'demo_inactive_devices.csv',
        'demo_reclamation_email.html',
        'demo_jamf_license_reclamation.log'
    ]
    
    for file in demo_files:
        try:
            if os.path.exists(file):
                os.remove(file)
                print(f"  ✅ Removed {file}")
        except Exception as e:
            print(f"  ⚠️  Could not remove {file}: {e}")

def main():
    """Main demo runner"""
    print("🎯 Jamf License Reclamation System - Interactive Demo")
    print("=" * 60)
    print("This demo shows how the system works with sample data.")
    print("No actual connections to Jamf Pro will be made.")
    print("=" * 60)
    
    try:
        # Create demo configuration
        create_demo_config()
        
        # Run demonstrations
        run_config_validation_demo()
        run_notification_demo()
        run_database_demo()
        run_dry_run_demo()
        
        print("\n" + "=" * 60)
        print("🎉 Demo completed successfully!")
        print("=" * 60)
        
        print("\n📁 Files created during demo:")
        demo_files = [
            'demo_grace_period_email.html',
            'demo_inactive_devices.csv', 
            'demo_reclamation_email.html'
        ]
        
        for file in demo_files:
            if os.path.exists(file):
                print(f"  📄 {file}")
        
        print("\n💡 Next steps to use this system:")
        print("  1. Copy .env.example to .env and configure your settings")
        print("  2. Run: python main.py --generate-config-template")
        print("  3. Edit config.ini with your Jamf Pro details")
        print("  4. Test with: python main.py --run-now --dry-run")
        print("  5. Deploy with: python main.py --daemon")
        
        # Ask if user wants to clean up
        try:
            response = input("\n🧹 Clean up demo files? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                cleanup_demo_files()
            else:
                print("Demo files kept for inspection.")
        except (EOFError, KeyboardInterrupt):
            print("\nDemo files kept for inspection.")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n👋 Demo finished!")

if __name__ == "__main__":
    main()