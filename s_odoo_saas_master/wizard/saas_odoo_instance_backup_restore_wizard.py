from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OdooInstanceBackupRestoreWizard(models.TransientModel):
    _name = 'saas.odoo.instance.backup.restore.wizard'
    _description = "SaaS Odoo Instance Backup Restore Wizard"

    backup_id = fields.Many2one('saas.odoo.instance.backup', string='Backup', required=True, ondelete='cascade')
    odoo_version_id = fields.Many2one(related='backup_id.odoo_version_id', string='Backup Odoo Version')
    instance_id = fields.Many2one('saas.odoo.instance', string='Restore To Instance', required=True,
        domain=[('state', '=', 'deploy'), ('is_template', '=', False)])
    confirmation = fields.Char(string="Type 'yes' to confirm")

    @api.onchange('backup_id')
    def _onchange_backup_id(self):
        domain = [('state', '=', 'deploy'), ('is_template', '=', False)]
        if self.backup_id.odoo_version_id:
            domain.append(('odoo_version_id', '=', self.backup_id.odoo_version_id.id))
        return {'domain': {'instance_id': domain}}

    def action_restore(self):
        self.ensure_one()
        if self.confirmation != 'yes':
            raise ValidationError(_("Please enter 'yes' in the confirmation box before restoring the backup."))
        self.backup_id.action_restore_to(self.instance_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _("Restore started for %s. Reopen this backup to track the progress.") % self.instance_id.display_name,
                'type': 'success',
                'sticky': False,
            }
        }
