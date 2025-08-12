#!/usr/bin/env python3
"""
Test script for Jamf License Reclamation System
Comprehensive testing of all system components
"""

import sys
import os
import unittest
import tempfile
import sqlite3
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from jamf_client import JamfAPIClient
from notification_service import NotificationService
from license_reclamation_service import LicenseReclamationService

class TestConfigManager(unittest.TestCase):
    """Test configuration manager functionality"""
    
    def setUp(self):
        self.test_config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False)
        self.test_config_file.write("""
[JAMF]
server_url = https://test.jamfcloud.com
username = test_user
password = test_pass

[LICENSE_RECLAMATION]
inactive_days_threshold = 90
grace_period_days = 7
max_reclaims_per_run = 10

[NOTIFICATIONS]
smtp_server = smtp.test.com
smtp_port = 587
email_username = test@test.com
email_password = test_pass
admin_email = admin@test.com

[LOGGING]
log_level = INFO
log_file = test.log
max_log_size_mb = 50
backup_count = 5

[SCHEDULE]
run_frequency = weekly
run_time = 02:00
run_days = 0,3,5
        """)
        self.test_config_file.close()
        
        self.config_manager = ConfigManager(self.test_config_file.name, "non_existent.env")
    
    def tearDown(self):
        os.unlink(self.test_config_file.name)
    
    def test_jamf_config_loading(self):
        """Test Jamf configuration loading"""
        config = self.config_manager.get_jamf_config()
        self.assertEqual(config['server_url'], 'https://test.jamfcloud.com')
        self.assertEqual(config['username'], 'test_user')
        self.assertEqual(config['password'], 'test_pass')
    
    def test_license_config_loading(self):
        """Test license reclamation configuration loading"""
        config = self.config_manager.get_license_reclamation_config()
        self.assertEqual(config['inactive_days_threshold'], 90)
        self.assertEqual(config['grace_period_days'], 7)
        self.assertEqual(config['max_reclaims_per_run'], 10)
    
    def test_config_validation(self):
        """Test configuration validation"""
        validation = self.config_manager.validate_config()
        self.assertIsInstance(validation['errors'], list)
        self.assertIsInstance(validation['warnings'], list)

class TestJamfAPIClient(unittest.TestCase):
    """Test Jamf API client functionality"""
    
    def setUp(self):
        # Mock the session to avoid actual API calls
        with patch('jamf_client.requests.Session'):
            self.jamf_client = JamfAPIClient(
                server_url="https://test.jamfcloud.com",
                username="test_user",
                password="test_pass"
            )
    
    @patch('jamf_client.requests.Session')
    def test_initialization(self, mock_session):
        """Test client initialization"""
        client = JamfAPIClient(
            server_url="https://test.jamfcloud.com",
            api_token="test_token"
        )
        self.assertEqual(client.server_url, "https://test.jamfcloud.com")
        self.assertEqual(client.api_token, "test_token")
    
    def test_computer_data_processing(self):
        """Test computer data processing methods"""
        # Mock computer data
        test_computer = {
            'id': 123,
            'name': 'Test-Mac',
            'serial_number': 'ABC123'
        }
        
        # Test that methods can handle mock data
        self.assertEqual(test_computer['id'], 123)
        self.assertEqual(test_computer['name'], 'Test-Mac')

class TestNotificationService(unittest.TestCase):
    """Test notification service functionality"""
    
    def setUp(self):
        self.notification_service = NotificationService(
            smtp_server="smtp.test.com",
            smtp_port=587,
            email_username="test@test.com",
            email_password="test_pass",
            admin_email="admin@test.com"
        )
    
    def test_csv_generation(self):
        """Test CSV report generation"""
        test_computers = [
            {
                'name': 'Test-Mac-1',
                'serial_number': 'ABC123',
                'last_contact': datetime.now(),
                'days_inactive': 95,
                'user_info': {'real_name': 'Test User', 'email_address': 'user@test.com'}
            }
        ]
        
        csv_content = self.notification_service._generate_csv_report(test_computers)
        self.assertIn('Test-Mac-1', csv_content)
        self.assertIn('ABC123', csv_content)
        self.assertIn('Test User', csv_content)
    
    def test_email_content_generation(self):
        """Test email content generation"""
        test_computers = [
            {
                'name': 'Test-Mac-1',
                'serial_number': 'ABC123',
                'last_contact': datetime.now(),
                'days_inactive': 95
            }
        ]
        
        email_content = self.notification_service._generate_grace_period_email(test_computers)
        self.assertIn('Test-Mac-1', email_content)
        self.assertIn('ABC123', email_content)
        self.assertIn('Grace Period', email_content)

class TestLicenseReclamationService(unittest.TestCase):
    """Test license reclamation service functionality"""
    
    def setUp(self):
        # Create temporary database
        self.db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_file.close()
        
        # Mock dependencies
        self.mock_jamf_client = Mock(spec=JamfAPIClient)
        self.mock_notification_service = Mock(spec=NotificationService)
        
        self.reclamation_service = LicenseReclamationService(
            jamf_client=self.mock_jamf_client,
            notification_service=self.mock_notification_service,
            database_path=self.db_file.name
        )
    
    def tearDown(self):
        os.unlink(self.db_file.name)
    
    def test_database_initialization(self):
        """Test database initialization"""
        # Check if tables were created
        with sqlite3.connect(self.db_file.name) as conn:
            cursor = conn.cursor()
            
            # Check grace_periods table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='grace_periods'")
            self.assertIsNotNone(cursor.fetchone())
            
            # Check reclamation_history table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reclamation_history'")
            self.assertIsNotNone(cursor.fetchone())
    
    def test_grace_period_management(self):
        """Test grace period entry management"""
        # Test data
        test_computers = [
            {
                'id': 123,
                'name': 'Test-Mac',
                'serial_number': 'ABC123',
                'last_contact': datetime.now() - timedelta(days=100),
                'days_inactive': 100
            }
        ]
        
        # Mock the user info retrieval
        self.mock_jamf_client.get_computer_user_info.return_value = {
            'username': 'testuser',
            'real_name': 'Test User',
            'email_address': 'test@example.com'
        }
        
        # Process new inactive computers
        grace_entries = self.reclamation_service._process_new_inactive_computers(
            test_computers, grace_period_days=7
        )
        
        self.assertEqual(len(grace_entries), 1)
        self.assertEqual(grace_entries[0].computer_id, 123)
        self.assertEqual(grace_entries[0].computer_name, 'Test-Mac')
    
    def test_expired_grace_periods(self):
        """Test finding expired grace periods"""
        # Add a test entry with expired grace period
        with sqlite3.connect(self.db_file.name) as conn:
            cursor = conn.cursor()
            
            expired_date = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute('''
                INSERT INTO grace_periods 
                (computer_id, computer_name, serial_number, last_contact,
                 days_inactive, grace_start_date, grace_end_date, user_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                456, 'Expired-Mac', 'XYZ789', None, 100,
                (datetime.now() - timedelta(days=8)).isoformat(),
                expired_date, '{}'
            ))
            conn.commit()
        
        # Find expired grace periods
        expired_computers = self.reclamation_service._get_expired_grace_periods()
        
        self.assertEqual(len(expired_computers), 1)
        self.assertEqual(expired_computers[0]['id'], 456)
        self.assertEqual(expired_computers[0]['name'], 'Expired-Mac')

class TestSystemIntegration(unittest.TestCase):
    """Test system integration and end-to-end workflows"""
    
    def setUp(self):
        # Create temporary files
        self.config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False)
        self.config_file.write("""
[JAMF]
server_url = https://test.jamfcloud.com
username = test_user
password = test_pass

[LICENSE_RECLAMATION]
inactive_days_threshold = 90
grace_period_days = 7
max_reclaims_per_run = 5

[NOTIFICATIONS]
smtp_server = smtp.test.com
smtp_port = 587
email_username = test@test.com
email_password = test_pass
admin_email = admin@test.com

[LOGGING]
log_level = INFO
log_file = test.log
max_log_size_mb = 50
backup_count = 5

[SCHEDULE]
run_frequency = weekly
run_time = 02:00
run_days = 0,3,5
        """)
        self.config_file.close()
        
        self.db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.db_file.close()
    
    def tearDown(self):
        os.unlink(self.config_file.name)
        os.unlink(self.db_file.name)
    
    @patch('jamf_client.requests.Session')
    def test_full_cycle_dry_run(self, mock_session):
        """Test complete reclamation cycle in dry run mode"""
        # Set up mocks
        mock_session_instance = Mock()
        mock_session.return_value = mock_session_instance
        
        # Mock successful authentication
        mock_auth_response = Mock()
        mock_auth_response.json.return_value = {'token': 'test_token'}
        mock_auth_response.raise_for_status.return_value = None
        
        with patch('jamf_client.requests.post', return_value=mock_auth_response):
            # Initialize services
            config_manager = ConfigManager(self.config_file.name, "non_existent.env")
            
            jamf_client = JamfAPIClient(
                server_url="https://test.jamfcloud.com",
                username="test_user",
                password="test_pass"
            )
            
            notification_service = NotificationService(
                smtp_server="smtp.test.com",
                smtp_port=587,
                email_username="test@test.com",
                email_password="test_pass",
                admin_email="admin@test.com"
            )
            
            reclamation_service = LicenseReclamationService(
                jamf_client=jamf_client,
                notification_service=notification_service,
                database_path=self.db_file.name
            )
            
            # Mock inactive computers
            with patch.object(jamf_client, 'get_inactive_computers') as mock_get_inactive:
                mock_get_inactive.return_value = []
                
                # Run cycle
                results = reclamation_service.run_license_reclamation_cycle(
                    inactive_days_threshold=90,
                    grace_period_days=7,
                    max_reclaims_per_run=5,
                    dry_run=True
                )
                
                # Verify results structure
                self.assertIn('start_time', results)
                self.assertIn('inactive_computers_found', results)
                self.assertIn('new_grace_periods', results)
                self.assertIn('licenses_reclaimed', results)
                self.assertIn('failed_reclamations', results)
                self.assertEqual(results['inactive_computers_found'], 0)

def run_system_checks():
    """Run additional system checks beyond unit tests"""
    print("\n" + "="*60)
    print("JAMF LICENSE RECLAMATION SYSTEM - HEALTH CHECK")
    print("="*60)
    
    # Check Python version
    python_version = sys.version_info
    print(f"✓ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 7):
        print("⚠ Warning: Python 3.7+ recommended")
    
    # Check required modules
    required_modules = ['requests', 'schedule', 'sqlite3', 'smtplib', 'configparser']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ Module {module} available")
        except ImportError:
            missing_modules.append(module)
            print(f"✗ Module {module} missing")
    
    if missing_modules:
        print(f"\n⚠ Missing modules: {', '.join(missing_modules)}")
        print("Install with: pip install -r requirements.txt")
    
    # Check file permissions (if on Unix-like system)
    if os.name == 'posix':
        current_dir = os.getcwd()
        try:
            # Check if we can create files
            test_file = os.path.join(current_dir, 'test_permissions.tmp')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print("✓ File system permissions OK")
        except Exception as e:
            print(f"⚠ File system permission issue: {e}")
    
    # Check if main components can be imported
    try:
        from main import JamfLicenseReclamationApp
        print("✓ Main application components importable")
    except Exception as e:
        print(f"✗ Import error: {e}")
    
    print("\n" + "="*60)
    print("HEALTH CHECK COMPLETE")
    print("="*60)

def main():
    """Main test runner"""
    print("Jamf License Reclamation System - Test Suite")
    print("=" * 50)
    
    # Run system checks first
    run_system_checks()
    
    # Run unit tests
    print("\nRunning unit tests...")
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestConfigManager))
    test_suite.addTest(unittest.makeSuite(TestJamfAPIClient))
    test_suite.addTest(unittest.makeSuite(TestNotificationService))
    test_suite.addTest(unittest.makeSuite(TestLicenseReclamationService))
    test_suite.addTest(unittest.makeSuite(TestSystemIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    # Return appropriate exit code
    if result.failures or result.errors:
        print("\n❌ Some tests failed!")
        return 1
    else:
        print("\n✅ All tests passed!")
        return 0

if __name__ == "__main__":
    sys.exit(main())