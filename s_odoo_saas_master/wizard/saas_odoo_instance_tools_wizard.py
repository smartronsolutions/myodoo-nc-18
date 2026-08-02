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
        [('odoo', 'Odoo Docker Terminal'), ('psql', 'PostgreSQL Docker Terminal')],
        string='Terminal', required=True, readonly=True, default='odoo'
    )
    # A whitespace default keeps databases upgraded from the earlier required
    # field definition compatible; the interactive widget supplies real input.
    command = fields.Text(string='Command / SQL', default=' ')
    output = fields.Text(string='Terminal Output', readonly=True)
    exit_code = fields.Integer(string='Exit Code', readonly=True)
    current_database = fields.Char(string='Current Database', readonly=True)
    shell_mode = fields.Selection(
        [('container', 'Container Shell'), ('psql', 'PostgreSQL Session')],
        default='container', required=True, readonly=True,
    )
    current_working_directory = fields.Char(
        string='Working Directory', default='/', required=True, readonly=True,
    )

    def _container_prompt(self, container_type):
        directory = self.current_working_directory or '/'
        prefix = 'pg' if container_type == 'psql' else 'odoo'
        return '%s:%s$ ' % (prefix, directory)

    def _run_container_shell(self, container_type, command):
        container_name = self._container_name(container_type)
        directory = self.current_working_directory or '/'
        marker = '__SAAS_TERMINAL_CWD__'
        shell_script = (
            'cd %s 2>/dev/null || cd /; '
            'eval %s; command_status=$?; '
            'printf "\\n%s%%s\\n" "$PWD"; '
            'exit $command_status'
        ) % (shlex.quote(directory), shlex.quote(command), marker)
        docker_options = '-e PGPASSWORD=odoo ' if container_type == 'psql' else ''
        remote_command = 'docker exec -i %s%s /bin/sh -lc %s' % (
            docker_options, shlex.quote(container_name), shlex.quote(shell_script)
        )
        status, result = self._run_remote_command(remote_command)
        if marker in result:
            visible_output, reported_directory = result.rsplit(marker, 1)
            new_directory = reported_directory.splitlines()[0].strip()
            if new_directory.startswith('/'):
                self.current_working_directory = new_directory
            result = visible_output.rstrip()
        return status, result, self._container_prompt(container_type)

    def _run_psql_command(self, database, command, user='odoo'):
        container_name = self._container_name('psql')
        remote_command = (
            'docker exec -i -e PGPASSWORD=odoo %s '
            'psql -X -v ON_ERROR_STOP=1 -U %s -d %s -c %s'
        ) % (
            shlex.quote(container_name), shlex.quote(user),
            shlex.quote(database), shlex.quote(command),
        )
        return self._run_remote_command(remote_command)

    def _parse_psql_connection(self, command):
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            raise ValidationError(_('Invalid psql command: %s') % exc) from exc
        if not parts or parts[0].rsplit('/', 1)[-1] != 'psql':
            return False
        # Informational/listing invocations run in the container shell and must
        # not be mistaken for an interactive database connection request.
        standalone_options = {'--version', '-V', '--help', '-?', '--list', '-l'}
        if any(part in standalone_options for part in parts[1:]):
            return False
        database = self.current_database or self.instance_id.db_name or 'postgres'
        user = 'odoo'
        index = 1
        while index < len(parts):
            part = parts[index]
            if part in ('-d', '--dbname') and index + 1 < len(parts):
                database = parts[index + 1]
                index += 2
                continue
            if part.startswith('--dbname='):
                database = part.split('=', 1)[1]
            elif part in ('-U', '--username') and index + 1 < len(parts):
                user = parts[index + 1]
                index += 2
                continue
            elif part.startswith('--username='):
                user = part.split('=', 1)[1]
            elif not part.startswith('-'):
                database = part
            index += 1
        return database, user

    def _check_unsupported_interactive_command(self, command):
        try:
            parts = shlex.split(command)
        except ValueError:
            return
        if not parts:
            return
        executable = parts[0].rsplit('/', 1)[-1]
        if executable == 'tail':
            follows = any(
                part == '--follow'
                or part.startswith('--follow=')
                or (part.startswith('-') and not part.startswith('--') and 'f' in part[1:])
                for part in parts[1:]
            )
            if follows:
                raise ValidationError(_(
                    'tail -f is a continuous streaming command. Use the Odoo Logs button '
                    'for live logs, or run "tail -n 50 FILE" for one-time output.'
                ))
        if executable in {'top', 'htop', 'watch', 'nano', 'vi', 'vim', 'less', 'more'}:
            raise ValidationError(_(
                'The "%s" command requires an interactive TTY and cannot run in this web terminal.'
            ) % executable)

    def _execute_terminal_command(self, command):
        self._check_access_and_instance()
        command = (command or '').strip()
        if not command:
            raise ValidationError(_('Enter a command to execute.'))
        # A PostgreSQL connection command is emulated as a persistent session
        # below; other never-ending/full-screen commands cannot use HTTP RPC.
        if not (
            self.terminal_type == 'psql'
            and self.shell_mode == 'container'
            and command.lstrip().startswith('psql')
        ):
            self._check_unsupported_interactive_command(command)

        if self.terminal_type == 'odoo':
            prompt = self._container_prompt('odoo')
            status, result, next_prompt = self._run_container_shell('odoo', command)
            block = '%s%s\n%s' % (
                prompt, command, result or _('Command completed without output.')
            )
            return status, next_prompt, block
        elif self.shell_mode == 'container':
            prompt = self._container_prompt('psql')
            connection = self._parse_psql_connection(command)
            if connection:
                database, user = connection
                status, result = self._run_psql_command(
                    database, 'SELECT current_database();', user=user
                )
                block = '%s%s\n%s' % (
                    prompt, command,
                    result if status else _('Connected. PostgreSQL commands can now be entered directly.'),
                )
                if not status:
                    self.write({
                        'shell_mode': 'psql',
                        'current_database': database,
                    })
                    prompt = '%s=> ' % database
                return status, prompt, block
            status, result, next_prompt = self._run_container_shell('psql', command)
            block = '%s%s\n%s' % (
                prompt, command, result or _('Command completed without output.')
            )
            return status, next_prompt, block
        else:
            database = self.current_database or self.instance_id.db_name or 'postgres'
            prompt = '%s=> ' % database
            if command in ('\\q', 'quit', 'exit'):
                self.shell_mode = 'container'
                return 0, self._container_prompt('psql'), '%s%s\n%s' % (
                    prompt, command, _('PostgreSQL session closed. Back in the container shell.')
                )
            if command.startswith('\\c ') or command.startswith('\\connect '):
                parts = command.split(None, 1)
                new_database = parts[1].strip()
                status, result = self._run_psql_command(
                    new_database, 'SELECT current_database();'
                )
                block = '%s%s\n%s' % (
                    prompt, command,
                    result if status else _('You are now connected to database "%s".') % new_database,
                )
                if not status:
                    self.current_database = new_database
                    prompt = '%s=> ' % new_database
                return status, prompt, block
            status, result = self._run_psql_command(database, command)
            block = '%s%s\n%s' % (
                prompt, command, result or _('Command completed without output.')
            )
            return status, prompt, block

        status, result = self._run_remote_command(remote_command)
        block = '%s%s\n%s' % (
            prompt, command, result or _('Command completed without output.')
        )
        return status, prompt, block

    def execute_terminal_command(self, command):
        """RPC endpoint used by the interactive terminal field widget."""
        status, prompt, block = self._execute_terminal_command(command)
        previous = (self.output or '').rstrip()
        self.write({
            'output': ('%s\n\n%s' % (previous, block)).strip(),
            'exit_code': status,
        })
        return {
            'block': block,
            'exit_code': status,
            'prompt': prompt,
        }

    def clear_terminal(self):
        self._check_access_and_instance()
        self.write({'output': False, 'exit_code': 0, 'command': ' '})
        if self.terminal_type == 'psql' and self.shell_mode == 'psql':
            prompt = '%s=> ' % (self.current_database or 'postgres')
        else:
            prompt = self._container_prompt(self.terminal_type)
        return {'prompt': prompt}

    def action_execute(self):
        self.execute_terminal_command(self.command)
        self.command = ' '
        return {
            'type': 'ir.actions.act_window',
            'name': _('PostgreSQL Docker Terminal') if self.terminal_type == 'psql' else _('Odoo Docker Terminal'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_clear(self):
        self.clear_terminal()
        return {
            'type': 'ir.actions.act_window',
            'name': _('PostgreSQL Docker Terminal') if self.terminal_type == 'psql' else _('Odoo Docker Terminal'),
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
            'if python3 -m pip install --help 2>/dev/null '
            '| grep -q -- --break-system-packages; then '
            '%s --break-system-packages %s; '
            'else %s %s; fi'
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

    def get_live_logs(self, cursor=0):
        """Return initial tail or bytes written after cursor for live polling."""
        self._check_access_and_instance()
        container_name = self._container_name('odoo')
        log_path = '/var/log/odoo/odoo.log'
        try:
            cursor = max(0, int(cursor or 0))
        except (TypeError, ValueError):
            cursor = 0
        marker = '__SAAS_LOG_CURSOR__'
        container_script = (
            'if [ -r %s ]; then '
            'log_size=$(wc -c < %s); '
            'if [ %d -gt 0 ] && [ "$log_size" -ge %d ]; then '
            'start_byte=$((%d + 1)); tail -c +"$start_byte" %s; '
            'else tail -n 50 %s; fi; '
            'printf "\\n%s%%s\\n" "$log_size"; '
            'else echo "Log file is not readable: %s"; exit 1; fi'
        ) % (
            shlex.quote(log_path), shlex.quote(log_path),
            cursor, cursor, cursor, shlex.quote(log_path),
            shlex.quote(log_path), marker, log_path,
        )
        remote_command = 'docker exec -i %s /bin/sh -lc %s' % (
            shlex.quote(container_name), shlex.quote(container_script)
        )
        status, output = self._run_remote_command(remote_command)
        new_cursor = cursor
        if marker in output:
            visible_output, reported_cursor = output.rsplit(marker, 1)
            try:
                new_cursor = max(0, int(reported_cursor.splitlines()[0].strip()))
            except (TypeError, ValueError, IndexError):
                new_cursor = cursor
            output = visible_output.rstrip()
        reset = bool(cursor and new_cursor < cursor)
        return {
            'output': output or (_('The log file is currently empty.') if not cursor else ''),
            'exit_code': status,
            'updated_at': fields.Datetime.to_string(fields.Datetime.now()),
            'cursor': new_cursor,
            'reset': reset,
        }
