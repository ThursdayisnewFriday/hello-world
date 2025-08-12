#!/usr/bin/env python3
"""
Configuration Manager for Jamf License Reclamation
This module handles configuration loading, validation, and management.
"""

import os
import configparser
import logging
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from pathlib import Path

class ConfigManager:
    """Manages configuration for Jamf license reclamation system"""
    
    def __init__(self, config_file: str = "config.ini", env_file: str = ".env"):
        """
        Initialize configuration manager
        
        Args:
            config_file: Path to configuration file
            env_file: Path to environment file
        """
        self.config_file = config_file
        self.env_file = env_file
        self.config = configparser.ConfigParser()
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self._load_config()
    
    def _load_config(self):
        """Load configuration from files and environment variables"""
        # Load environment variables
        if os.path.exists(self.env_file):
            load_dotenv(self.env_file)
            self.logger.info(f"Loaded environment variables from {self.env_file}")
        
        # Load configuration file
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
            self.logger.info(f"Loaded configuration from {self.config_file}")
        else:
            self.logger.warning(f"Configuration file {self.config_file} not found")
    
    def get_jamf_config(self) -> Dict[str, Any]:
        """
        Get Jamf API configuration
        
        Returns:
            Dictionary with Jamf configuration
        """
        config = {}
        
        # Get from environment variables first, then config file
        config['server_url'] = (
            os.getenv('JAMF_SERVER_URL') or 
            self.config.get('JAMF', 'server_url', fallback='')
        )
        
        config['username'] = (
            os.getenv('JAMF_USERNAME') or 
            self.config.get('JAMF', 'username', fallback='')
        )
        
        config['password'] = (
            os.getenv('JAMF_PASSWORD') or 
            self.config.get('JAMF', 'password', fallback='')
        )
        
        config['api_token'] = (
            os.getenv('JAMF_API_TOKEN') or 
            self.config.get('JAMF', 'api_token', fallback='')
        )
        
        return config
    
    def get_license_reclamation_config(self) -> Dict[str, Any]:
        """
        Get license reclamation configuration
        
        Returns:
            Dictionary with license reclamation settings
        """
        config = {}
        
        config['inactive_days_threshold'] = int(
            os.getenv('INACTIVE_DAYS_THRESHOLD') or 
            self.config.get('LICENSE_RECLAMATION', 'inactive_days_threshold', fallback='90')
        )
        
        config['grace_period_days'] = int(
            os.getenv('GRACE_PERIOD_DAYS') or 
            self.config.get('LICENSE_RECLAMATION', 'grace_period_days', fallback='7')
        )
        
        config['max_reclaims_per_run'] = int(
            os.getenv('MAX_RECLAIMS_PER_RUN') or 
            self.config.get('LICENSE_RECLAMATION', 'max_reclaims_per_run', fallback='10')
        )
        
        return config
    
    def get_notification_config(self) -> Dict[str, Any]:
        """
        Get notification configuration
        
        Returns:
            Dictionary with notification settings
        """
        config = {}
        
        # Email configuration
        config['smtp_server'] = (
            os.getenv('SMTP_SERVER') or 
            self.config.get('NOTIFICATIONS', 'smtp_server', fallback='smtp.gmail.com')
        )
        
        config['smtp_port'] = int(
            os.getenv('SMTP_PORT') or 
            self.config.get('NOTIFICATIONS', 'smtp_port', fallback='587')
        )
        
        config['email_username'] = (
            os.getenv('EMAIL_USERNAME') or 
            self.config.get('NOTIFICATIONS', 'email_username', fallback='')
        )
        
        config['email_password'] = (
            os.getenv('EMAIL_PASSWORD') or 
            self.config.get('NOTIFICATIONS', 'email_password', fallback='')
        )
        
        config['admin_email'] = (
            os.getenv('ADMIN_EMAIL') or 
            self.config.get('NOTIFICATIONS', 'admin_email', fallback='')
        )
        
        # Slack configuration
        config['slack_webhook_url'] = (
            os.getenv('SLACK_WEBHOOK_URL') or 
            self.config.get('NOTIFICATIONS', 'slack_webhook_url', fallback='')
        )
        
        return config
    
    def get_logging_config(self) -> Dict[str, Any]:
        """
        Get logging configuration
        
        Returns:
            Dictionary with logging settings
        """
        config = {}
        
        config['log_level'] = (
            os.getenv('LOG_LEVEL') or 
            self.config.get('LOGGING', 'log_level', fallback='INFO')
        )
        
        config['log_file'] = (
            os.getenv('LOG_FILE') or 
            self.config.get('LOGGING', 'log_file', fallback='jamf_license_reclamation.log')
        )
        
        config['max_log_size_mb'] = int(
            os.getenv('MAX_LOG_SIZE_MB') or 
            self.config.get('LOGGING', 'max_log_size_mb', fallback='50')
        )
        
        config['backup_count'] = int(
            os.getenv('BACKUP_COUNT') or 
            self.config.get('LOGGING', 'backup_count', fallback='5')
        )
        
        return config
    
    def get_schedule_config(self) -> Dict[str, Any]:
        """
        Get schedule configuration
        
        Returns:
            Dictionary with schedule settings
        """
        config = {}
        
        config['run_frequency'] = (
            os.getenv('RUN_FREQUENCY') or 
            self.config.get('SCHEDULE', 'run_frequency', fallback='weekly')
        )
        
        config['run_time'] = (
            os.getenv('RUN_TIME') or 
            self.config.get('SCHEDULE', 'run_time', fallback='02:00')
        )
        
        run_days_str = (
            os.getenv('RUN_DAYS') or 
            self.config.get('SCHEDULE', 'run_days', fallback='0,3,5')
        )
        config['run_days'] = [int(day.strip()) for day in run_days_str.split(',')]
        
        return config
    
    def validate_config(self) -> Dict[str, list]:
        """
        Validate configuration settings
        
        Returns:
            Dictionary with validation results {'errors': [...], 'warnings': [...]}
        """
        errors = []
        warnings = []
        
        # Validate Jamf configuration
        jamf_config = self.get_jamf_config()
        
        if not jamf_config['server_url']:
            errors.append("Jamf server URL is required")
        
        if not jamf_config['api_token'] and not (jamf_config['username'] and jamf_config['password']):
            errors.append("Either API token or username/password is required for Jamf authentication")
        
        # Validate notification configuration
        notification_config = self.get_notification_config()
        
        if not notification_config['admin_email']:
            warnings.append("Admin email not configured - error notifications will not be sent")
        
        if notification_config['email_username'] and not notification_config['email_password']:
            errors.append("Email password is required when email username is provided")
        
        # Validate license reclamation configuration
        license_config = self.get_license_reclamation_config()
        
        if license_config['inactive_days_threshold'] < 1:
            errors.append("Inactive days threshold must be at least 1")
        
        if license_config['grace_period_days'] < 1:
            errors.append("Grace period days must be at least 1")
        
        if license_config['max_reclaims_per_run'] < 1:
            errors.append("Max reclaims per run must be at least 1")
        
        # Validate schedule configuration
        schedule_config = self.get_schedule_config()
        
        if schedule_config['run_frequency'] not in ['daily', 'weekly', 'monthly']:
            errors.append("Run frequency must be 'daily', 'weekly', or 'monthly'")
        
        try:
            from datetime import datetime
            datetime.strptime(schedule_config['run_time'], '%H:%M')
        except ValueError:
            errors.append("Run time must be in HH:MM format")
        
        for day in schedule_config['run_days']:
            if day < 0 or day > 6:
                errors.append("Run days must be between 0 (Monday) and 6 (Sunday)")
        
        return {'errors': errors, 'warnings': warnings}
    
    def get_database_path(self) -> str:
        """
        Get database file path
        
        Returns:
            Path to SQLite database file
        """
        return os.getenv('DATABASE_PATH') or 'license_reclamation.db'
    
    def is_dry_run_enabled(self) -> bool:
        """
        Check if dry run mode is enabled
        
        Returns:
            True if dry run mode is enabled
        """
        dry_run_str = os.getenv('DRY_RUN', 'false').lower()
        return dry_run_str in ('true', '1', 'yes', 'on')
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        Get all configuration settings
        
        Returns:
            Dictionary with all configuration
        """
        return {
            'jamf': self.get_jamf_config(),
            'license_reclamation': self.get_license_reclamation_config(),
            'notifications': self.get_notification_config(),
            'logging': self.get_logging_config(),
            'schedule': self.get_schedule_config(),
            'database_path': self.get_database_path(),
            'dry_run': self.is_dry_run_enabled()
        }
    
    def save_config_template(self, output_file: str = "config_template.ini"):
        """
        Save a configuration template file
        
        Args:
            output_file: Output file path
        """
        template_config = configparser.ConfigParser()
        
        # Jamf section
        template_config.add_section('JAMF')
        template_config.set('JAMF', '# Jamf Pro server URL', '')
        template_config.set('JAMF', 'server_url', 'https://your-jamf-instance.jamfcloud.com')
        template_config.set('JAMF', '# API username (if using basic auth)', '')
        template_config.set('JAMF', 'username', 'your_api_username')
        template_config.set('JAMF', '# API password (if using basic auth)', '')
        template_config.set('JAMF', 'password', 'your_api_password')
        template_config.set('JAMF', '# API token (alternative to username/password)', '')
        template_config.set('JAMF', 'api_token', '')
        
        # License reclamation section
        template_config.add_section('LICENSE_RECLAMATION')
        template_config.set('LICENSE_RECLAMATION', '# Days of inactivity before license reclamation', '')
        template_config.set('LICENSE_RECLAMATION', 'inactive_days_threshold', '90')
        template_config.set('LICENSE_RECLAMATION', '# Grace period in days before actual reclamation', '')
        template_config.set('LICENSE_RECLAMATION', 'grace_period_days', '7')
        template_config.set('LICENSE_RECLAMATION', '# Maximum number of licenses to reclaim per run', '')
        template_config.set('LICENSE_RECLAMATION', 'max_reclaims_per_run', '10')
        
        # Notifications section
        template_config.add_section('NOTIFICATIONS')
        template_config.set('NOTIFICATIONS', '# Email notifications', '')
        template_config.set('NOTIFICATIONS', 'smtp_server', 'smtp.gmail.com')
        template_config.set('NOTIFICATIONS', 'smtp_port', '587')
        template_config.set('NOTIFICATIONS', 'email_username', 'your_email@company.com')
        template_config.set('NOTIFICATIONS', 'email_password', 'your_app_password')
        template_config.set('NOTIFICATIONS', 'admin_email', 'admin@company.com')
        template_config.set('NOTIFICATIONS', '# Slack webhook (optional)', '')
        template_config.set('NOTIFICATIONS', 'slack_webhook_url', '')
        
        # Logging section
        template_config.add_section('LOGGING')
        template_config.set('LOGGING', 'log_level', 'INFO')
        template_config.set('LOGGING', 'log_file', 'jamf_license_reclamation.log')
        template_config.set('LOGGING', 'max_log_size_mb', '50')
        template_config.set('LOGGING', 'backup_count', '5')
        
        # Schedule section
        template_config.add_section('SCHEDULE')
        template_config.set('SCHEDULE', '# Run frequency (daily, weekly, monthly)', '')
        template_config.set('SCHEDULE', 'run_frequency', 'weekly')
        template_config.set('SCHEDULE', '# Specific time to run (HH:MM format)', '')
        template_config.set('SCHEDULE', 'run_time', '02:00')
        template_config.set('SCHEDULE', '# Days of week for weekly runs (0=Monday, 6=Sunday)', '')
        template_config.set('SCHEDULE', 'run_days', '0,3,5')
        
        with open(output_file, 'w') as f:
            template_config.write(f)
        
        self.logger.info(f"Configuration template saved to {output_file}")