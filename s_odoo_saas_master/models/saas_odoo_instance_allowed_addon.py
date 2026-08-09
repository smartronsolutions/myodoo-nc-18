from odoo import fields, models


class OdooInstanceAllowedAddon(models.Model):
    _name = 'saas.odoo.instance.allowed.addon'
    _description = 'SaaS Odoo Instance Allowed Addon'
    _order = 'application desc, name, technical_name'

    instance_id = fields.Many2one(
        'saas.odoo.instance', required=True, ondelete='cascade', index=True
    )
    technical_name = fields.Char(string='Technical Name', required=True, index=True)
    name = fields.Char(string='Addon Name', required=True)
    application = fields.Boolean(string='Application')
    module_state = fields.Selection([
        ('uninstallable', 'Uninstallable'),
        ('uninstalled', 'Not Installed'),
        ('installed', 'Installed'),
        ('to upgrade', 'To Upgrade'),
        ('to remove', 'To Remove'),
        ('to install', 'To Install'),
    ], string='Status', readonly=True)
    allowed = fields.Boolean(string='Allowed')

    _sql_constraints = [
        (
            'instance_module_unique',
            'unique(instance_id, technical_name)',
            'An addon can only be listed once per Odoo instance.',
        ),
    ]
