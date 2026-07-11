from odoo import http, fields
from odoo.http import request
from datetime import timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class StoragePortal(http.Controller):

    def _get_own_instance(self, instance_id):
        """Portal user's own instance, or an empty recordset if not found/not theirs"""
        return request.env['saas.odoo.instance'].search([
            ('id', '=', instance_id),
            ('partner_id', '=', request.env.user.partner_id.id),
        ], limit=1)

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
    
    @http.route('/my/storage/<int:instance_id>', auth='user', website=True)
    def storage_instance_detail(self, instance_id, **kw):
        """Per-instance storage page: current usage + last 7 days report + request upgrade"""
        instance = self._get_own_instance(instance_id)
        if not instance:
            return request.redirect('/my/storage')

        since = fields.Datetime.now() - timedelta(days=7)
        history = request.env['saas.storage.history'].search([
            ('instance_id', '=', instance.id),
            ('check_date', '>=', since),
        ], order='check_date asc')

        # Keep only the last check of each day (most recent overwrites earlier same-day ones)
        daily = {}
        for h in history:
            daily[h.check_date.date()] = h
        daily_history = sorted(daily.values(), key=lambda h: h.check_date, reverse=True)

        return request.render('saas_storage_management.portal_storage_instance_detail', {
            'instance': instance,
            'daily_history': daily_history,
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
            
            instance = self._get_own_instance(int(instance_id))

            if not instance:
                return {'status': 'error', 'message': 'Instance not found'}

            # Call model method and get status dict
            result = instance.request_upgrade(float(new_limit_gb))
            
            # Log the result
            _logger.info(f"[STORAGE] Request upgrade result: {result}")
            
            # Return the status dict from model
            return result
        except Exception as e:
            _logger.error(f"[STORAGE] Error in request_upgrade: {str(e)}")
            return {'status': 'error', 'message': str(e)}
