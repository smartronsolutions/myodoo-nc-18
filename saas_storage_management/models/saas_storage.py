from odoo import models, fields
from odoo.exceptions import ValidationError, UserError
import os
import logging

_logger = logging.getLogger(__name__)


class SaasOdooInstance(models.Model):
    _inherit = 'saas.odoo.instance'

    # Storage fields
    storage_limit_gb = fields.Float(
        string='Storage Limit (GB)',
        default=0.5,
        help='Maximum storage allowed for this instance in GB. Leave empty or 0 for unlimited. Default: 500MB (0.5GB)'
    )
    
    storage_used_gb = fields.Float(
        string='Storage Used (GB)',
        compute='_compute_storage_used',
        store=False
    )
    
    storage_percentage = fields.Float(
        string='Storage Usage %',
        compute='_compute_storage_percentage',
        store=False
    )
    
    storage_status = fields.Selection([
        ('ok', 'OK'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('full', 'Full'),
        ('unlimited', 'Unlimited'),
    ], string='Storage Status', compute='_compute_storage_status', store=False)
    
    storage_is_unlimited = fields.Boolean(
        string='Unlimited Storage',
        compute='_compute_storage_is_unlimited',
        store=False
    )
    
    storage_last_check = fields.Datetime(string='Last Check')
    storage_notification_sent = fields.Boolean(default=False)
    
    storage_upgrade_requested = fields.Boolean(default=False)
    storage_upgrade_requested_gb = fields.Float()
    storage_upgrade_request_date = fields.Datetime()
    storage_upgrade_request_reason = fields.Text()
    
    # Relationship to storage history
    storage_history_ids = fields.One2many('saas.storage.history', 'instance_id', string='Storage History', readonly=True)

    def _compute_storage_used(self):
        """Compute storage used for each instance"""
        for record in self:
            try:
                record.storage_used_gb = round(self._calculate_filestore_size(record), 2)
            except Exception as e:
                _logger.error(f"[STORAGE] Error computing storage for {record.name}: {str(e)}")
                record.storage_used_gb = 0.0

    def _compute_storage_percentage(self):
        """Compute storage percentage"""
        for record in self:
            if record.storage_is_unlimited or not record.storage_limit_gb or record.storage_limit_gb == 0:
                record.storage_percentage = 0.0
            else:
                record.storage_percentage = round((record.storage_used_gb / record.storage_limit_gb) * 100, 1)

    def _compute_storage_is_unlimited(self):
        """Check if storage is unlimited"""
        for record in self:
            record.storage_is_unlimited = not record.storage_limit_gb or record.storage_limit_gb == 0

    def _compute_storage_status(self):
        """Compute storage status"""
        for record in self:
            if record.storage_is_unlimited:
                record.storage_status = 'unlimited'
            elif record.storage_percentage >= 100:
                record.storage_status = 'full'
            elif record.storage_percentage >= 90:
                record.storage_status = 'critical'
            elif record.storage_percentage >= 80:
                record.storage_status = 'warning'
            else:
                record.storage_status = 'ok'

    def _calculate_filestore_size(self, instance):
        """
        Calculate total size of /home/{technical_name}/ directory in GB
        
        Path structure:
        /home/{technical_name}/
        ├── Dockerfile
        ├── config/
        ├── custom-addons/
        ├── docker-compose.yml
        ├── odoo-web-data/
        └── pgdata/
        """
        try:
            # Use technical_name for path
            if not instance.technical_name:
                _logger.warning(f"[STORAGE] No technical_name for instance {instance.name}")
                return 0.0
            
            instance_path = f"/home/{instance.technical_name}"
            
            _logger.info(f"[STORAGE] Starting calculation for {instance.name} at {instance_path}")
            
            # Check if path exists
            if not os.path.exists(instance_path):
                _logger.warning(f"[STORAGE] Path not found: {instance_path}")
                return 0.0
            
            # Check if path is readable
            if not os.access(instance_path, os.R_OK):
                _logger.warning(f"[STORAGE] No read permission for: {instance_path}")
                return 0.0
            
            total_size = 0
            file_count = 0
            error_count = 0
            
            # Walk through all directories and files
            try:
                for dirpath, dirnames, filenames in os.walk(instance_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            if os.path.isfile(filepath) and os.path.exists(filepath):
                                file_size = os.path.getsize(filepath)
                                total_size += file_size
                                file_count += 1
                        except (OSError, IOError):
                            error_count += 1
                            continue
            except Exception as e:
                _logger.error(f"[STORAGE] Error walking directory {instance_path}: {str(e)}")
            
            size_gb = total_size / (1024 ** 3)
            _logger.info(f"[STORAGE] {instance.name}: {total_size} bytes ({file_count} files, {error_count} errors) = {size_gb:.4f} GB")
            return size_gb
            
        except Exception as e:
            _logger.error(f"[STORAGE] Error calculating storage for {instance.name}: {str(e)}")
            return 0.0

    def check_storage(self):
        """Check storage and create history record"""
        for record in self:
            try:
                # Calculate storage
                size_gb = self._calculate_filestore_size(record)
                record.storage_used_gb = size_gb
                
                # Calculate percentage
                if record.storage_is_unlimited or not record.storage_limit_gb or record.storage_limit_gb == 0:
                    percentage = 0
                else:
                    percentage = (size_gb / record.storage_limit_gb) * 100
                
                # Get status
                if record.storage_is_unlimited:
                    status = 'unlimited'
                elif percentage >= 100:
                    status = 'full'
                elif percentage >= 90:
                    status = 'critical'
                elif percentage >= 80:
                    status = 'warning'
                else:
                    status = 'ok'
                
                # Update last check
                record.storage_last_check = fields.Datetime.now()
                
                # Create history record
                self.env['saas.storage.history'].create({
                    'instance_id': record.id,
                    'storage_used_gb': round(size_gb, 2),
                    'storage_limit_gb': record.storage_limit_gb,
                    'storage_percentage': round(percentage, 2),
                    'storage_status': status,
                })
                
                _logger.info(f"[STORAGE] Updated instance {record.name}: {size_gb:.2f}GB ({percentage:.1f}%)")
                
            except Exception as e:
                _logger.error(f"[STORAGE] Error checking storage for {record.name}: {str(e)}")

    def request_upgrade(self, new_limit_gb):
        """Client requests storage upgrade - returns status dict"""
        for record in self:
            try:
                # Validate new limit
                if not new_limit_gb or new_limit_gb <= 0:
                    return {
                        'status': 'error',
                        'message': 'Storage limit must be greater than 0'
                    }
                
                # Check if new limit is not greater than current limit
                if not record.storage_is_unlimited and new_limit_gb <= record.storage_limit_gb:
                    current_limit = record.storage_limit_gb
                    return {
                        'status': 'error',
                        'message': f'You already have {current_limit} GB. Please request a limit above {current_limit} GB.'
                    }
                
                # Check if there's already a pending request
                if record.storage_upgrade_requested:
                    pending_limit = record.storage_upgrade_requested_gb
                    return {
                        'status': 'error',
                        'message': f'You already have a pending upgrade request for {pending_limit} GB. Support will contact you soon.'
                    }
                
                # Create upgrade request
                record.storage_upgrade_requested = True
                record.storage_upgrade_requested_gb = new_limit_gb
                record.storage_upgrade_request_date = fields.Datetime.now()
                
                _logger.info(f"[STORAGE] Upgrade request for {record.name}: {record.storage_limit_gb}GB → {new_limit_gb}GB")
                
                # Send email to admin
                self._send_upgrade_request_email(record, new_limit_gb)
                
                # Return success message
                return {
                    'status': 'success',
                    'message': f'Your request for {new_limit_gb} GB has been submitted. Support will contact you soon via email or phone. Thank you!'
                }
                
            except Exception as e:
                _logger.error(f"[STORAGE] Error requesting upgrade for {record.name}: {str(e)}")
                return {
                    'status': 'error',
                    'message': f'An error occurred: {str(e)}'
                }

    def _send_upgrade_request_email(self, instance, new_limit_gb):
        """Send email notification to admin about upgrade request"""
        try:
            # Get admin users
            admin_users = self.env['res.users'].search([('groups_id.name', 'ilike', 'SaaS Manager')])
            
            if not admin_users:
                # Fallback to super admin
                admin_users = self.env['res.users'].search([('id', '=', 2)])
            
            if not admin_users:
                _logger.warning(f"[STORAGE] No admin users found to send upgrade request email")
                return
            
            # Prepare email content
            subject = f"Storage Upgrade Request - {instance.name}"
            body = f"""
            <p>Storage upgrade request received:</p>
            <ul>
                <li><strong>Instance:</strong> {instance.name}</li>
                <li><strong>Current Limit:</strong> {instance.storage_limit_gb} GB</li>
                <li><strong>Current Usage:</strong> {instance.storage_used_gb:.2f} GB ({instance.storage_percentage:.1f}%)</li>
                <li><strong>Requested Limit:</strong> {new_limit_gb} GB</li>
                <li><strong>Request Date:</strong> {instance.storage_upgrade_request_date}</li>
                <li><strong>Customer:</strong> {instance.partner_id.name}</li>
            </ul>
            <p><a href="/web#id={instance.id}&model=saas.odoo.instance&view_type=form">View Instance</a></p>
            """
            
            # Send email
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_from': self.env.user.email,
                'email_to': ','.join([user.email for user in admin_users if user.email]),
            }
            
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            
            _logger.info(f"[STORAGE] Upgrade request email sent for {instance.name}")
            
        except Exception as e:
            _logger.error(f"[STORAGE] Error sending upgrade request email: {str(e)}")

    def approve_upgrade(self):
        """Admin approves upgrade"""
        for record in self:
            try:
                if not record.storage_upgrade_requested:
                    raise UserError('No upgrade request for this instance')
                
                old_limit = record.storage_limit_gb
                new_limit = record.storage_upgrade_requested_gb
                
                # Update storage limit
                record.storage_limit_gb = new_limit
                record.storage_upgrade_requested = False
                record.storage_upgrade_requested_gb = 0
                
                _logger.info(f"[STORAGE] Upgrade approved for {record.name}: {old_limit}GB → {new_limit}GB")
                
                # Send approval email to customer
                self._send_approval_email(record, old_limit, new_limit)
                
            except Exception as e:
                _logger.error(f"[STORAGE] Error approving upgrade for {record.name}: {str(e)}")
                raise

    def reject_upgrade(self):
        """Admin rejects upgrade"""
        for record in self:
            try:
                if not record.storage_upgrade_requested:
                    raise UserError('No upgrade request for this instance')
                
                requested_limit = record.storage_upgrade_requested_gb
                
                # Reject request
                record.storage_upgrade_requested = False
                record.storage_upgrade_requested_gb = 0
                
                _logger.info(f"[STORAGE] Upgrade rejected for {record.name}: {requested_limit}GB")
                
                # Send rejection email to customer
                self._send_rejection_email(record, requested_limit)
                
            except Exception as e:
                _logger.error(f"[STORAGE] Error rejecting upgrade for {record.name}: {str(e)}")
                raise

    def _send_approval_email(self, instance, old_limit, new_limit):
        """Send approval email to customer"""
        try:
            customer_email = instance.partner_id.email
            if not customer_email:
                _logger.warning(f"[STORAGE] No email for customer {instance.partner_id.name}")
                return
            
            subject = f"Storage Upgrade Approved - {instance.name}"
            body = f"""
            <p>Your storage upgrade request has been approved!</p>
            <ul>
                <li><strong>Instance:</strong> {instance.name}</li>
                <li><strong>Previous Limit:</strong> {old_limit} GB</li>
                <li><strong>New Limit:</strong> {new_limit} GB</li>
                <li><strong>Approved Date:</strong> {fields.Datetime.now()}</li>
            </ul>
            <p>Your storage limit has been updated. You can now use up to {new_limit} GB.</p>
            """
            
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_from': self.env.user.email,
                'email_to': customer_email,
            }
            
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            
            _logger.info(f"[STORAGE] Approval email sent to {customer_email}")
            
        except Exception as e:
            _logger.error(f"[STORAGE] Error sending approval email: {str(e)}")

    def _send_rejection_email(self, instance, requested_limit):
        """Send rejection email to customer"""
        try:
            customer_email = instance.partner_id.email
            if not customer_email:
                _logger.warning(f"[STORAGE] No email for customer {instance.partner_id.name}")
                return
            
            subject = f"Storage Upgrade Request Rejected - {instance.name}"
            body = f"""
            <p>Your storage upgrade request has been rejected.</p>
            <ul>
                <li><strong>Instance:</strong> {instance.name}</li>
                <li><strong>Requested Limit:</strong> {requested_limit} GB</li>
                <li><strong>Current Limit:</strong> {instance.storage_limit_gb} GB</li>
                <li><strong>Rejection Date:</strong> {fields.Datetime.now()}</li>
            </ul>
            <p>Please contact support for more information.</p>
            """
            
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_from': self.env.user.email,
                'email_to': customer_email,
            }
            
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            
            _logger.info(f"[STORAGE] Rejection email sent to {customer_email}")
            
        except Exception as e:
            _logger.error(f"[STORAGE] Error sending rejection email: {str(e)}")


class SaasStorageHistory(models.Model):
    _name = 'saas.storage.history'
    _description = 'Storage Check History'
    _order = 'check_date desc'

    instance_id = fields.Many2one('saas.odoo.instance', string='Instance', ondelete='cascade')
    check_date = fields.Datetime(string='Check Date', default=fields.Datetime.now)
    storage_used_gb = fields.Float(string='Storage Used (GB)')
    storage_limit_gb = fields.Float(string='Storage Limit (GB)')
    storage_percentage = fields.Float(string='Storage Usage %')
    storage_status = fields.Selection([
        ('ok', 'OK'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('full', 'Full'),
        ('unlimited', 'Unlimited'),
    ], string='Storage Status')
