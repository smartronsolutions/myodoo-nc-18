import re
import shlex

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


MAX_OUTPUT_BYTES = 100000
PACKAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:(?:==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+)?$"
)


class InstanceToolWizardMixin(models.AbstractModel):
    _name = 'saas.odoo.instance.tool.wizard.mixin'
    _description = 'SaaS Odoo Instance Tool Wizard Mixin'

    def _check_access_and_instance(self):
        self.ensure_one()
        if not self.env.user.has_group('s_odoo_saas_master.group_odoo_saas_master'):
            raise UserError(_('Only SaaS Master users can access container tools.'))
        if self.instance_id.state != 'deploy' or self.instance_id.operation_state != 'run':
            raise UserError(_('The Odoo instance must be deployed and running.'))
        if not self.instance_id.pserver_id:
            raise UserError(_('No physical server is configured for this instance.'))

    def _container_name(self, container_type):
        containers = self.instance_id.docker_container_ids.filtered(
            lambda container: container.container_type == container_type
        )
        if not containers:
            raise UserError(
                _('No %s container was found for this instance.') % container_type.upper()
            )
        return containers[0].name

    def _run_remote_command(self, command):
        """Run on the physical server and return a bounded, combined output."""
        ssh = self.instance_id.pserver_id._connect_or_raise()
        # Buffer remotely so noisy pip/terminal commands cannot deadlock Paramiko's
        # stdout/stderr channels. Only the last useful portion is returned to Odoo.
        wrapped = (
            'output_file=$(mktemp); '
            '(%s) >"$output_file" 2>&1; command_status=$?; '
            'tail -c %d "$output_file"; rm -f "$output_file"; '
            'exit $command_status'
        ) % (command, MAX_OUTPUT_BYTES)
        try:
            stdin, stdout, stderr = ssh.exec_command(wrapped, timeout=900)
            del stdin
            output = stdout.read().decode('utf-8', errors='replace')
            error_output = stderr.read().decode('utf-8', errors='replace')
            status = stdout.channel.recv_exit_status()
        except Exception as exc:
            raise UserError(_('Container command failed: %s') % exc) from exc
        finally:
            ssh.close()
        return status, (output + error_output).strip()


class InstanceTerminalWizard(models.TransientModel):
    _name = 'saas.odoo.instance.terminal.wizard'
    _inherit = 'saas.odoo.instance.tool.wizard.mixin'
    _description = 'SaaS Odoo Instance Container Terminal'

    instance_id = fields.Many2one(
        'saas.odoo.instance', string='Odoo Instance', required=True, readonly=True,
        ondelete='cascade'
    )
    terminal_type = fields.Selection(
        [('odoo', 'Odoo Docker Terminal'), ('psql', 'PostgreSQL Terminal')],
        string='Terminal', required=True, readonly=True, default='odoo'
    )
    command = fields.Text(string='Command / SQL', required=True)
    output = fields.Text(string='Terminal Output', readonly=True)
    exit_code = fields.Integer(string='Exit Code', readonly=True)

    def action_execute(self):
        self._check_access_and_instance()
        command = (self.command or '').strip()
        if not command:
            raise ValidationError(_('Enter a command to execute.'))

        if self.terminal_type == 'odoo':
            container_name = self._container_name('odoo')
            remote_command = 'docker exec -i %s /bin/sh -lc %s' % (
                shlex.quote(container_name), shlex.quote(command)
            )
            prompt = '$ '
        else:
            container_name = self._container_name('psql')
            database = self.instance_id.db_name or 'postgres'
            remote_command = (
                'docker exec -i -e PGPASSWORD=odoo %s '
                'psql -X -v ON_ERROR_STOP=1 -U odoo -d %s -c %s'
            ) % (
                shlex.quote(container_name), shlex.quote(database), shlex.quote(command)
            )
            prompt = '%s=> ' % database

        status, result = self._run_remote_command(remote_command)
        previous = (self.output or '').rstrip()
        block = '%s%s\n%s\n[exit code: %s]' % (
            prompt, command, result or _('Command completed without output.'), status
        )
        self.write({
            'output': ('%s\n\n%s' % (previous, block)).strip(),
            'exit_code': status,
            'command': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('PostgreSQL Terminal') if self.terminal_type == 'psql' else _('Odoo Docker Terminal'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_clear(self):
        self.write({'output': False, 'exit_code': 0, 'command': False})
        return {
            'type': 'ir.actions.act_window',
            'name': _('PostgreSQL Terminal') if self.terminal_type == 'psql' else _('Odoo Docker Terminal'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class InstancePythonPackageWizard(models.TransientModel):
    _name = 'saas.odoo.instance.python.package.wizard'
    _inherit = 'saas.odoo.instance.tool.wizard.mixin'
    _description = 'Install Python Packages in SaaS Odoo Instance'

    instance_id = fields.Many2one(
        'saas.odoo.instance', string='Odoo Instance', required=True, readonly=True,
        ondelete='cascade'
    )
    package_names = fields.Text(
        string='Python Packages', required=True,
        help='Enter one or more package specifications, separated by spaces or new lines. '
             'Example: requests psycopg2-binary==2.9.10'
    )
    output = fields.Text(string='Installation Output', readonly=True)
    exit_code = fields.Integer(string='Exit Code', readonly=True)

    def _parse_packages(self):
        try:
            packages = shlex.split(self.package_names or '')
        except ValueError as exc:
            raise ValidationError(_('Invalid package list: %s') % exc) from exc
        if not packages:
            raise ValidationError(_('Enter at least one Python package.'))
        invalid = [package for package in packages if not PACKAGE_RE.fullmatch(package)]
        if invalid:
            raise ValidationError(
                _('Invalid package specification(s): %s') % ', '.join(invalid)
            )
        return packages

    def action_install(self):
        self._check_access_and_instance()
        packages = self._parse_packages()
        container_name = self._container_name('odoo')
        package_args = ' '.join(shlex.quote(package) for package in packages)
        pip_base = 'python3 -m pip install --disable-pip-version-check --no-input'
        install_script = (
            '%s %s || %s --break-system-packages %s'
            % (pip_base, package_args, pip_base, package_args)
        )
        remote_command = 'docker exec -u 0 -i %s /bin/sh -lc %s' % (
            shlex.quote(container_name), shlex.quote(install_script)
        )
        status, result = self._run_remote_command(remote_command)
        if status:
            result = '%s\n\n%s' % (
                _('INSTALLATION FAILED (exit code %s)') % status,
                result or _('No error output was returned.'),
            )
        else:
            result = '%s\n\n%s' % (
                _('INSTALLATION SUCCESSFUL'),
                result or _('Installation completed without output.'),
            )
        self.write({
            'output': result,
            'exit_code': status,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Install Python Packages'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class InstanceOdooLogWizard(models.TransientModel):
    _name = 'saas.odoo.instance.odoo.log.wizard'
    _inherit = 'saas.odoo.instance.tool.wizard.mixin'
    _description = 'SaaS Odoo Instance Live Log Viewer'

    instance_id = fields.Many2one(
        'saas.odoo.instance', string='Odoo Instance', required=True, readonly=True,
        ondelete='cascade'
    )
    log_output = fields.Text(string='Odoo Logs', readonly=True)

    def get_live_logs(self):
        """Return the latest 50 lines for the auto-refreshing backend widget."""
        self._check_access_and_instance()
        container_name = self._container_name('odoo')
        log_path = '/var/log/odoo/odoo.log'
        container_script = (
            'if [ -r %s ]; then tail -n 50 %s; '
            'else echo "Log file is not readable: %s"; exit 1; fi'
        ) % (
            shlex.quote(log_path), shlex.quote(log_path), log_path
        )
        remote_command = 'docker exec -i %s /bin/sh -lc %s' % (
            shlex.quote(container_name), shlex.quote(container_script)
        )
        status, output = self._run_remote_command(remote_command)
        return {
            'output': output or _('The log file is currently empty.'),
            'exit_code': status,
            'updated_at': fields.Datetime.to_string(fields.Datetime.now()),
        }
