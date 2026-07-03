from odoo import fields, models


class OdooServer(models.Model):
    _name = 'saas.odoo.server'
    _description = "SaaS Odoo Server"
    _order = 'sequence'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer('Sequence', default=10, required=True)
    pserver_id = fields.Many2one('saas.pserver', string="Physical Server", required=True, copy=False)
    working_ip_id = fields.Many2one('saas.pserver.ip', string="Working IP", required=True, copy=False)
    odoo_version_id = fields.Many2one('saas.odoo.version', string='Odoo Version', required=True)
    psql_version_id = fields.Many2one('saas.psql.version', string='PSQL Version', required=True)
    nginx_server_id = fields.Many2one('saas.nginx.server', string='Nginx Server', required=True)
    extra_addon_ids = fields.One2many('saas.odoo.server.extra.addon', 'odoo_server_id', string='Extra Addons')
    description = fields.Text(string='Description')
    active = fields.Boolean(string="Active", default=True)
