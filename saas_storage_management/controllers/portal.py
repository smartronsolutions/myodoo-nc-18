from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class StoragePortal(http.Controller):
    
    @http.route('/my/storage', auth='user', website=True)
    def storage_dashboard(self, **kw):
        """Client storage dashboard"""
        partner = request.env.user.partner_id
        instances = request.env['saas.odoo.instance'].search([
            ('partner_id', '=', partner.id)
        ])
        
        # Check for storage warnings
        warnings = []
        for instance in instances:
            if instance.storage_limit_gb and instance.storage_limit_gb > 0:
                percentage = (instance.storage_used_gb / instance.storage_limit_gb) * 100
                if percentage >= 80:
                    warnings.append({
                        'instance_name': instance.name,
                        'used': round(instance.storage_used_gb, 2),
                        'limit': instance.storage_limit_gb,
                        'percentage': round(percentage, 1),
                        'status': 'critical' if percentage >= 90 else 'warning'
                    })
        
        return request.render('saas_storage_management.portal_storage_dashboard', {
            'instances': instances,
            'warnings': warnings,
            'page_name': 'storage',
        })
    
    @http.route('/my/storage/request-upgrade', auth='user', website=True, type='json')
    def request_upgrade(self, **kw):
        """Request storage upgrade"""
        try:
            # The frontend posts a plain JSON body (not a JSON-RPC envelope),
            # so read it directly instead of relying on dispatcher-parsed params.
            data = json.loads(request.httprequest.data)
            instance_id = data.get('instance_id')
            new_limit_gb = data.get('new_limit_gb')
            
            _logger.info(f"[STORAGE] Request upgrade: instance_id={instance_id}, new_limit={new_limit_gb}")
            
            if not instance_id or not new_limit_gb:
                return {'status': 'error', 'message': 'Missing instance_id or new_limit_gb'}
            
            instance = request.env['saas.odoo.instance'].browse(int(instance_id))
            
            if not instance.exists():
                return {'status': 'error', 'message': 'Instance not found'}
            
            if instance.partner_id.id != request.env.user.partner_id.id:
                return {'status': 'error', 'message': 'Unauthorized'}
            
            # Call model method and get status dict
            result = instance.request_upgrade(float(new_limit_gb))
            
            # Log the result
            _logger.info(f"[STORAGE] Request upgrade result: {result}")
            
            # Return the status dict from model
            return result
        except Exception as e:
            _logger.error(f"[STORAGE] Error in request_upgrade: {str(e)}")
            return {'status': 'error', 'message': str(e)}
