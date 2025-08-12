#!/usr/bin/env python3
"""
Jamf License Reclamation - Main Application
Automated license reclamation system for inactive Mac devices in Jamf Pro.
"""

import sys
import os
import argparse
import logging
import logging.handlers
import schedule
import time
import signal
from datetime import datetime
from typing import Optional

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from jamf_client import JamfAPIClient
from notification_service import NotificationService
from license_reclamation_service import LicenseReclamationService

class JamfLicenseReclamationApp:
    """Main application class for Jamf license reclamation"""
    
    def __init__(self, config_file: str = "config.ini", env_file: str = ".env"):
        """
        Initialize the application
        
        Args:
            config_file: Path to configuration file
            env_file: Path to environment file
        """
        self.config_manager = ConfigManager(config_file, env_file)
        self.logger = None
        self.jamf_client = None
        self.notification_service = None
        self.reclamation_service = None
        self.running = False
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        if self.logger:
            self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def setup_logging(self):
        """Set up logging configuration"""
        logging_config = self.config_manager.get_logging_config()
        
        # Configure logging level
        log_level = getattr(logging, logging_config['log_level'].upper(), logging.INFO)
        
        # Create logger
        self.logger = logging.getLogger()
        self.logger.setLevel(log_level)
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        if logging_config['log_file']:
            max_bytes = logging_config['max_log_size_mb'] * 1024 * 1024
            file_handler = logging.handlers.RotatingFileHandler(
                logging_config['log_file'],
                maxBytes=max_bytes,
                backupCount=logging_config['backup_count']
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        
        self.logger.info("Logging configured successfully")
    
    def validate_configuration(self) -> bool:
        """
        Validate configuration settings
        
        Returns:
            True if configuration is valid
        """
        validation_result = self.config_manager.validate_config()
        
        if validation_result['errors']:
            self.logger.error("Configuration validation failed:")
            for error in validation_result['errors']:
                self.logger.error(f"  - {error}")
            return False
        
        if validation_result['warnings']:
            self.logger.warning("Configuration warnings:")
            for warning in validation_result['warnings']:
                self.logger.warning(f"  - {warning}")
        
        self.logger.info("Configuration validation passed")
        return True
    
    def initialize_services(self):
        """Initialize all service components"""
        try:
            # Get configuration
            jamf_config = self.config_manager.get_jamf_config()
            notification_config = self.config_manager.get_notification_config()
            database_path = self.config_manager.get_database_path()
            
            # Initialize Jamf client
            self.jamf_client = JamfAPIClient(
                server_url=jamf_config['server_url'],
                username=jamf_config['username'] if jamf_config['username'] else None,
                password=jamf_config['password'] if jamf_config['password'] else None,
                api_token=jamf_config['api_token'] if jamf_config['api_token'] else None
            )
            self.logger.info("Jamf API client initialized")
            
            # Initialize notification service
            self.notification_service = NotificationService(
                smtp_server=notification_config['smtp_server'],
                smtp_port=notification_config['smtp_port'],
                email_username=notification_config['email_username'],
                email_password=notification_config['email_password'],
                admin_email=notification_config['admin_email'],
                slack_webhook_url=notification_config['slack_webhook_url'] if notification_config['slack_webhook_url'] else None
            )
            self.logger.info("Notification service initialized")
            
            # Initialize license reclamation service
            self.reclamation_service = LicenseReclamationService(
                jamf_client=self.jamf_client,
                notification_service=self.notification_service,
                database_path=database_path
            )
            self.logger.info("License reclamation service initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize services: {str(e)}")
            raise
    
    def run_reclamation_cycle(self):
        """Run a single license reclamation cycle"""
        try:
            self.logger.info("Starting license reclamation cycle")
            
            # Get configuration
            license_config = self.config_manager.get_license_reclamation_config()
            dry_run = self.config_manager.is_dry_run_enabled()
            
            if dry_run:
                self.logger.info("Running in DRY RUN mode - no licenses will actually be reclaimed")
            
            # Run the cycle
            results = self.reclamation_service.run_license_reclamation_cycle(
                inactive_days_threshold=license_config['inactive_days_threshold'],
                grace_period_days=license_config['grace_period_days'],
                max_reclaims_per_run=license_config['max_reclaims_per_run'],
                dry_run=dry_run
            )
            
            # Log results
            self.logger.info(f"License reclamation cycle completed in {results.get('duration', 0):.2f} seconds")
            self.logger.info(f"Results: {results}")
            
        except Exception as e:
            error_msg = f"Error during license reclamation cycle: {str(e)}"
            self.logger.error(error_msg)
            
            # Send error notification
            if self.notification_service:
                self.notification_service.send_error_notification(
                    "License reclamation cycle failed", str(e)
                )
    
    def setup_scheduler(self):
        """Set up the job scheduler"""
        schedule_config = self.config_manager.get_schedule_config()
        
        run_time = schedule_config['run_time']
        run_frequency = schedule_config['run_frequency']
        run_days = schedule_config['run_days']
        
        if run_frequency == 'daily':
            schedule.every().day.at(run_time).do(self.run_reclamation_cycle)
            self.logger.info(f"Scheduled to run daily at {run_time}")
            
        elif run_frequency == 'weekly':
            days_map = {
                0: schedule.every().monday,
                1: schedule.every().tuesday,
                2: schedule.every().wednesday,
                3: schedule.every().thursday,
                4: schedule.every().friday,
                5: schedule.every().saturday,
                6: schedule.every().sunday
            }
            
            for day in run_days:
                if day in days_map:
                    days_map[day].at(run_time).do(self.run_reclamation_cycle)
            
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            scheduled_days = [day_names[day] for day in run_days if 0 <= day <= 6]
            self.logger.info(f"Scheduled to run weekly on {', '.join(scheduled_days)} at {run_time}")
            
        elif run_frequency == 'monthly':
            # For monthly, run on the first occurrence of each specified day
            # This is a simplified implementation
            for day in run_days:
                if 0 <= day <= 6:
                    days_map = {
                        0: schedule.every().monday,
                        1: schedule.every().tuesday,
                        2: schedule.every().wednesday,
                        3: schedule.every().thursday,
                        4: schedule.every().friday,
                        5: schedule.every().saturday,
                        6: schedule.every().sunday
                    }
                    days_map[day].at(run_time).do(self.run_reclamation_cycle)
            
            self.logger.info(f"Scheduled to run monthly at {run_time}")
    
    def run_daemon(self):
        """Run the application as a daemon"""
        self.logger.info("Starting Jamf License Reclamation daemon")
        
        # Set up scheduler
        self.setup_scheduler()
        
        # Main daemon loop
        self.running = True
        while self.running:
            try:
                # Run pending scheduled jobs
                schedule.run_pending()
                
                # Sleep for a minute before checking again
                time.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in daemon loop: {str(e)}")
                time.sleep(60)  # Wait before retrying
        
        self.logger.info("Daemon stopped")
    
    def get_status(self) -> dict:
        """Get current system status"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'configuration_valid': False,
            'services_initialized': False,
            'grace_period_devices': 0,
            'recent_reclamations': 0
        }
        
        try:
            # Check configuration
            validation_result = self.config_manager.validate_config()
            status['configuration_valid'] = len(validation_result['errors']) == 0
            
            # Check services
            if self.reclamation_service:
                status['services_initialized'] = True
                
                # Get grace period status
                grace_period_devices = self.reclamation_service.get_grace_period_status()
                status['grace_period_devices'] = len(grace_period_devices)
                
                # Get recent reclamations (last 7 days)
                recent_history = self.reclamation_service.get_reclamation_history(days=7)
                status['recent_reclamations'] = len([h for h in recent_history if h['success']])
        
        except Exception as e:
            self.logger.error(f"Error getting status: {str(e)}")
        
        return status
    
    def cleanup(self):
        """Clean up resources"""
        try:
            if self.reclamation_service:
                self.reclamation_service.close()
            
            if self.logger:
                self.logger.info("Application cleanup completed")
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error during cleanup: {str(e)}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Jamf License Reclamation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --daemon                    # Run as daemon with scheduled reclamation
  %(prog)s --run-now                   # Run reclamation cycle immediately
  %(prog)s --dry-run                   # Run in dry-run mode (no actual reclamation)
  %(prog)s --status                    # Show current system status
  %(prog)s --validate-config           # Validate configuration only
  %(prog)s --grace-period-status       # Show devices in grace period
  %(prog)s --reclamation-history       # Show recent reclamation history
        """
    )
    
    parser.add_argument(
        '--config-file', '-c',
        default='config.ini',
        help='Configuration file path (default: config.ini)'
    )
    
    parser.add_argument(
        '--env-file', '-e',
        default='.env',
        help='Environment file path (default: .env)'
    )
    
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='Run as daemon with scheduled reclamation'
    )
    
    parser.add_argument(
        '--run-now', '-r',
        action='store_true',
        help='Run reclamation cycle immediately'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run in dry-run mode (no actual reclamation)'
    )
    
    parser.add_argument(
        '--status', '-s',
        action='store_true',
        help='Show current system status'
    )
    
    parser.add_argument(
        '--validate-config',
        action='store_true',
        help='Validate configuration only'
    )
    
    parser.add_argument(
        '--grace-period-status',
        action='store_true',
        help='Show devices currently in grace period'
    )
    
    parser.add_argument(
        '--reclamation-history',
        action='store_true',
        help='Show recent reclamation history'
    )
    
    parser.add_argument(
        '--generate-config-template',
        action='store_true',
        help='Generate configuration template file'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Override log level'
    )
    
    args = parser.parse_args()
    
    # Set dry run environment variable if specified
    if args.dry_run:
        os.environ['DRY_RUN'] = 'true'
    
    # Initialize application
    app = JamfLicenseReclamationApp(args.config_file, args.env_file)
    
    try:
        # Generate config template if requested
        if args.generate_config_template:
            app.config_manager.save_config_template()
            print("Configuration template generated: config_template.ini")
            return 0
        
        # Set up logging (override log level if specified)
        if args.log_level:
            os.environ['LOG_LEVEL'] = args.log_level
        app.setup_logging()
        
        # Validate configuration only
        if args.validate_config:
            if app.validate_configuration():
                app.logger.info("Configuration is valid")
                return 0
            else:
                app.logger.error("Configuration validation failed")
                return 1
        
        # Initialize services for other operations
        if not app.validate_configuration():
            return 1
        
        app.initialize_services()
        
        # Show status
        if args.status:
            status = app.get_status()
            print("\n=== Jamf License Reclamation Status ===")
            print(f"Timestamp: {status['timestamp']}")
            print(f"Configuration Valid: {status['configuration_valid']}")
            print(f"Services Initialized: {status['services_initialized']}")
            print(f"Devices in Grace Period: {status['grace_period_devices']}")
            print(f"Recent Reclamations (7 days): {status['recent_reclamations']}")
            return 0
        
        # Show grace period status
        if args.grace_period_status:
            grace_devices = app.reclamation_service.get_grace_period_status()
            print(f"\n=== Devices in Grace Period ({len(grace_devices)}) ===")
            
            if not grace_devices:
                print("No devices currently in grace period")
            else:
                for device in grace_devices:
                    print(f"Device: {device['computer_name']} ({device['serial_number']})")
                    print(f"  Last Contact: {device['last_contact']}")
                    print(f"  Days Remaining: {device['days_remaining']}")
                    print(f"  Expired: {device['expired']}")
                    print()
            return 0
        
        # Show reclamation history
        if args.reclamation_history:
            history = app.reclamation_service.get_reclamation_history(days=30)
            print(f"\n=== Reclamation History (30 days) - {len(history)} entries ===")
            
            if not history:
                print("No recent reclamation history")
            else:
                for entry in history[:10]:  # Show last 10 entries
                    status_icon = "✅" if entry['success'] else "❌"
                    print(f"{status_icon} {entry['computer_name']} ({entry['serial_number']})")
                    print(f"    Reclaimed: {entry['reclamation_date']}")
                    if not entry['success'] and entry['error_message']:
                        print(f"    Error: {entry['error_message']}")
                    print()
            return 0
        
        # Run immediately
        if args.run_now:
            app.run_reclamation_cycle()
            return 0
        
        # Run as daemon
        if args.daemon:
            app.run_daemon()
            return 0
        
        # If no specific action is requested, show help
        parser.print_help()
        return 0
        
    except KeyboardInterrupt:
        if app.logger:
            app.logger.info("Interrupted by user")
        return 0
    
    except Exception as e:
        if app.logger:
            app.logger.error(f"Unexpected error: {str(e)}")
        else:
            print(f"Error: {str(e)}")
        return 1
    
    finally:
        app.cleanup()

if __name__ == "__main__":
    sys.exit(main())