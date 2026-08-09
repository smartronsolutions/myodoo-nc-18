from odoo import _, models
from odoo.exceptions import AccessError


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _saas_check_install_allowed(self):
        parameters = self.env['ir.config_parameter'].sudo()
        enabled = parameters.get_param(
            's_saas_addon_guard.enabled', default='False'
        ).lower() in ('1', 'true', 'yes', 'on')
        if not enabled:
            return
        allowed = {
            name.strip()
            for name in parameters.get_param(
                's_saas_addon_guard.allowed_modules', default=''
            ).split(',')
            if name.strip()
        }
        allowed.add('s_saas_addon_guard')
        denied = self.filtered(lambda module: module.name not in allowed)
        if denied:
            raise AccessError(_(
                "You do not have access to install these addons: %s. "
                "Please contact your administrator."
            ) % ', '.join(sorted(denied.mapped('name'))))

    def button_immediate_install(self):
        self._saas_check_install_allowed()
        return super().button_immediate_install()

    def button_install(self):
        self._saas_check_install_allowed()
        return super().button_install()
