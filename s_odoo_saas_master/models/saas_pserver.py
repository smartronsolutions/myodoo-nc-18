import paramiko
import json
import logging
import os
import shlex
from odoo import fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class PServer(models.Model):
    _name = 'saas.pserver'
    _inherit = ['saas.ssh.mixin']
    _description = "SaaS Physical Server"

    name = fields.Char(string='Name', required=True)
    ssh_port = fields.Integer(string="SSH Port", required=True, default=22)
    ssh_keypair_id = fields.Many2one('saas.ssh.keypair', string="SSH Key Pair", required=True)
    ssh_keypair_name = fields.Char(related="ssh_keypair_id.name", string="SSH Key", readonly=True)
    can_edit_ssh_key = fields.Boolean(string="Can Edit SSH Key", compute="_compute_can_edit_ssh_key")
    ip_ids = fields.One2many('saas.pserver.ip', 'pserver_id', string="IPs")
    version_16_plus = fields.Boolean(string='Ubuntu Version 16+', default=True)
    active = fields.Boolean(string="Active", default=True)

    def _compute_can_edit_ssh_key(self):
        """Check if the current user can edit SSH key fields."""
        is_saas_master = self.env.user.has_group('s_odoo_saas_master.group_odoo_saas_master')
        for record in self:
            record.can_edit_ssh_key = is_saas_master

    def action_test_connection(self):
        ssh = self._connect_or_raise()
        if ssh:
            ssh.close()

        message = _("Connection Successful!")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_managing_ip(self):
        managing_ips = self.ip_ids.filtered(lambda ip: ip.type == 'managing_ip')
        if not managing_ips:
            raise UserError(_("Cannot find managing IP of %s server") % self.name)
        return managing_ips[0].name

    def _connect(self):
        managing_ip = self._get_managing_ip()
        privatekey_file_full_path = self.ssh_keypair_id.private_key_id._full_path(self.ssh_keypair_id.private_key_id.store_fname)
        if not privatekey_file_full_path:
            raise UserError(_("Cannot find attachment path of private key of %s server.") % self.name)

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(managing_ip, username='root', port=self.ssh_port, key_filename=privatekey_file_full_path)
            if not ssh:
                raise UserError(_("Cannot connect to server %s. Please check server information and SSH Key Pair") % self.name)
            return ssh
        except Exception:
            return False

    def _connect_or_raise(self):
        ssh = self._connect()
        if not ssh:
            raise UserError(
                _("Cannot connect to server %s. Please check server information and SSH Key Pair.")
                % self.display_name
            )
        return ssh

    def _deploy_odoo_instance(self, instance):
        ssh = self._connect()
        try:
            self._create_instance_folder(instance, ssh)
            self._create_odoo_instance_config_file(instance, ssh)
            # self._create_standard_extra_addons(instance, ssh)
            self._create_custom_addons(instance.custom_addon_ids, ssh)
            if instance.default_module:
                odoo_command = 'odoo -i %s -d %s' % (instance.default_module, instance.technical_name)
                self._create_docker_compose_file(instance, ssh, odoo_command)
                self._docker_compose_up(instance, ssh)
                file_path = instance._get_docker_compose_file_path()
                self._exec_cmd('rm -f %s' % file_path, ssh)
                self._create_docker_compose_file(instance, ssh)
                instance.write({'need_to_compose_up': True})
            else:
                self._create_docker_compose_file(instance, ssh)
                self._docker_compose_up(instance, ssh)
            self._create_nginx_file(instance.domain_name_ids, ssh)
            ssh.close()
        except Exception as ex:
            self._revoke_odoo_instance(instance, ssh)
            raise UserError(ex)

    def _deploy_odoo_instance_from_template(self, instance):
        ssh = self._connect()
        try:
            self._create_instance_folder(instance, ssh)
            self._prepare_instance_folder_from_template(instance, ssh)
            self._create_docker_compose_file(instance, ssh)
            self._docker_compose_up(instance, ssh)
            self._create_nginx_file(instance.domain_name_ids, ssh)            
            ssh.close()
        except Exception as ex:
            self._revoke_odoo_instance(instance, ssh)
            raise UserError(ex)

    def _prepare_instance_folder_from_template(self, instance, ssh):
        self._exec_cmd("cp -r -a /home/%s/* /home/%s" % (instance.template_instance_id.technical_name, instance.technical_name), ssh)
        self._exec_cmd("rm -rf /home/%s/odoo-web-data/sessions" % instance.technical_name, ssh)
        self._exec_cmd("rm -rf /home/%s/docker-compose.yml" % instance.technical_name, ssh)

    def _create_instance_folder(self, instance, ssh):
        self._exec_cmd('mkdir /home/%s' % instance.technical_name, ssh)
        for volume in instance.docker_compose_volume_ids:
            self._exec_cmd('mkdir %s' % volume.storage_path, ssh)

    def _create_odoo_instance_config_file(self, instance, ssh):
        file_content = self.env['saas.odoo.instance.config']._get_config_file_content(instance)
        file_path = self.env['saas.odoo.instance.config']._get_config_file_path(instance)
        self._create_file(ssh, file_path, file_content)

    def _create_standard_extra_addons(self, instance, ssh):
        for extra_addon in instance.odoo_server_id.extra_addon_ids:
            self._exec_cmd('cp -r %s /home/%s/custom-addons' % (extra_addon.source_path, instance.technical_name), ssh)

    def _create_custom_addons(self, custom_addons, ssh):
        for custom_addon in custom_addons.filtered(lambda c: not c.cloned):
            cmd = 'git clone %s --branch %s --depth 1 --single-branch %s' % (custom_addon.clone_uri, custom_addon.branch, custom_addon.addon_path)
            self._exec_cmd(cmd, ssh)

    def _create_docker_compose_file(self, instance, ssh, odoo_command=False):
        file_content = instance._get_docker_compose_file_content(odoo_command=odoo_command)
        file_path = instance._get_docker_compose_file_path()
        self._create_file(ssh, file_path, file_content)

    def _docker_compose_up(self, instance, ssh=False):
        if not ssh:
            ssh = self._connect()
        cmd = 'cd /home/%s' % instance.technical_name + ';'
        cmd += 'docker-compose up -d ;'
        self._exec_cmd(cmd, ssh)

    def _create_nginx_file(self, domain_name_ids, ssh):
        for domain_name in domain_name_ids:
            file_content = domain_name._get_nginx_file_content()
            file_path = domain_name._get_nginx_file_path()
            symlink_path = domain_name._get_nginx_symlink_file_path()
            self._create_file(ssh, file_path, file_content)
            self._create_symlink(ssh, file_path, symlink_path)

        self._exec_cmd('systemctl reload nginx', ssh)
        domain_names = ' -d '.join(domain_name_ids.mapped('name'))
        self._exec_cmd('certbot --non-interactive --nginx --agree-tos -d %s --redirect' % domain_names, ssh)

    def _revoke_odoo_instance(self, instance, ssh=None):
        if not ssh:
            ssh = self._connect_or_raise()
        try:
            self._remove_docker_containers(instance, ssh)
            self._remove_instance_folder(instance, ssh)
            self._remove_nginx_file(instance.domain_name_ids, ssh)
            self._remove_network(instance, ssh)
        finally:
            if ssh:
                ssh.close()

    def _remove_docker_containers(self, instance, ssh):
        if not instance.docker_container_ids:
            return
        container_names = ' '.join(instance.docker_container_ids.mapped('name'))
        self._exec_cmd('docker stop %s' % container_names, ssh)
        self._exec_cmd('docker rm -v %s' % container_names, ssh)

    def _remove_instance_folder(self, instance, ssh):
        self._exec_cmd('rm -rf /home/%s' % instance.technical_name, ssh)

    def _remove_nginx_file(self, domain_name_ids, ssh):
        need_to_remove = []
        for domain_name in domain_name_ids:
            need_to_remove.append(domain_name._get_nginx_file_path())
            need_to_remove.append(domain_name._get_nginx_symlink_file_path())

        self._exec_cmd('rm -rf %s' % ' '.join(need_to_remove), ssh)
        self._exec_cmd('systemctl reload nginx', ssh)

    def _remove_network(self, instance, ssh):
        network_name = "%s_default" % instance.technical_name
        self._exec_cmd('docker network rm %s' % network_name, ssh)

    def _get_container_status(self, containers):
        res = {}
        if not containers:
            return res
        container_names = ' '.join(containers.mapped('name'))
        ssh = self._connect()
        if not ssh:
            _logger.warning(
                "Cannot connect to server %s while reading Docker container status.",
                self.display_name,
            )
            return {container.name: 'unknown' for container in containers}

        try:
            status = self._exec_cmd("docker inspect -f '{{.State.Status}}' " + container_names, ssh, without_return=False)
        except Exception:
            _logger.exception(
                "Cannot read Docker container status from server %s.",
                self.display_name,
            )
            return {container.name: 'unknown' for container in containers}
        finally:
            ssh.close()

        for index, container in enumerate(containers):
            if index < len(status):
                res[container.name] = status[index].rstrip()
            else:
                res[container.name] = 'unknown'
                _logger.error(f"Container status missing for {container.name}")
        return res

    def _container_operation(self, instance, operation, container_names, ssh=False):
        if not container_names:
            return

        if not ssh:
            ssh = self._connect_or_raise()
        if instance.need_to_compose_up:
            self._docker_compose_up(instance, ssh)
            instance.write({'need_to_compose_up': False})
        self._exec_cmd("docker %s %s" % (operation, container_names), ssh)
        if ssh:
            ssh.close()

    def _redeploy_odoo_instance_config(self, instance):
        ssh = self._connect()
        try:
            self._remove_odoo_instance_config_file(instance, ssh)
            self._create_odoo_instance_config_file(instance, ssh)
            self._container_operation(instance, 'restart', 'odoo_%s' % instance.technical_name, ssh=ssh)
        except Exception as ex:
            ssh.close()
            raise UserError(ex)

    def _redeploy_odoo_instance_nginx(self, domain_name_ids):
        ssh = self._connect()
        try:
            self._remove_nginx_file(domain_name_ids, ssh)
            self._create_nginx_file(domain_name_ids, ssh)
            ssh.close()
        except Exception as ex:
            ssh.close()
            raise UserError(ex)

    def _remove_odoo_instance_config_file(self, instance, ssh):
        config_path = instance.docker_compose_volume_ids.filtered(lambda v: v.volume_type == 'odoo_config')[0].storage_path
        self._exec_cmd('rm -f %s' % config_path, ssh)

    def _cancel_nginx(self, domain_name_ids):
        ssh = self._connect()
        self._remove_nginx_file(domain_name_ids, ssh)
        ssh.close()

    def _deploy_nginx(self, domain_name_ids):
        ssh = self._connect()
        self._create_nginx_file(domain_name_ids, ssh)
        ssh.close()

    def _clone_customer_addons(self, custom_addons):
        ssh = self._connect()
        self._create_custom_addons(custom_addons, ssh)
        ssh.close()

    def _pull_customer_addons(self, custom_addons):        
        ssh = self._connect()
        for custom_addon in custom_addons:
            self._exec_cmd('cd %s && git pull' % custom_addon.addon_path, ssh)
            self._container_operation(custom_addon.instance_id, 'restart', 'odoo_%s' % custom_addon.instance_id.technical_name, ssh=ssh)
        ssh.close()

    def _remove_customer_addons(self, custom_addons):
        ssh = self._connect()
        for custom_addon in custom_addons:
            self._exec_cmd('rm -rf %s' % custom_addons.addon_path, ssh)
            self._container_operation(custom_addon.instance_id, 'restart', 'odoo_%s' % custom_addon.instance_id.technical_name, ssh=ssh)
        ssh.close()

    def _recreate_docker_compose_file(self, instance, odoo_command=False, update=False):
        # TODO: check upgrade finish to run docker-compose up -d
        ssh = self._connect()
        # 1. Remove origin docker compose file
        file_path = instance._get_docker_compose_file_path()
        self._exec_cmd('rm -f %s' % file_path, ssh)
        # 2. Create new docker compose file
        self._create_docker_compose_file(instance, ssh, odoo_command=odoo_command)
        # 3. docker compose up
        self._docker_compose_up(instance, ssh)
        if not update:
            # 4. Remove new docker compose file
            self._exec_cmd('rm -f %s' % file_path, ssh)
            # 5. Recreate origin docker compose file
            self._create_docker_compose_file(instance, ssh)
        ssh.close()

    def _get_active_user(self, instances):
        res = {}
        if not instances:
            return res
        ssh = self._connect()
        for instance in instances:
            psql_containers = instance.docker_container_ids.filtered(lambda c: c.container_type == 'psql')
            for container in psql_containers:
                query = 'select count(*) from res_users where share=False and active=True'
                cmd = 'docker exec -i %s psql -U odoo -W -d %s -c "%s"' % (container.name, instance.db_name, query)
                output = self._exec_cmd(cmd, ssh, arguments=['odoo'], without_return=False)
                if output:
                    output = output[2]
                    output = int(output.replace('\n', '').strip())
                    res.update({instance.id: output})
        ssh.close()
        return res

    def _get_installed_apps(self, instances):
        res = {}
        if not instances:
            return res
        ssh = self._connect()
        for instance in instances:
            psql_containers = instance.docker_container_ids.filtered(lambda c: c.container_type == 'psql')
            for container in psql_containers:
                query = "select shortdesc,name,write_date from ir_module_module where application=true and state='installed'"
                cmd = 'docker exec -i %s psql -U odoo -W -d %s -c "%s"' % (container.name, instance.db_name, query)
                output = self._exec_cmd(cmd, ssh, arguments=['odoo'], without_return=False)
                output = output[:-2][2:]
                apps = []
                for item in output:
                    item = item.split('|')
                    app_name = item[0].strip()
                    if instance.odoo_version_id.version >= 16:
                        app_name = json.loads(app_name)
                        app_name = list(app_name.values())[0]

                    technical_name = item[1].strip()
                    write_date = item[2].replace('\n', '').strip().split('.')[0]
                    apps.append({
                        'name': app_name,
                        'technical_name': technical_name,
                        'installed_date': fields.Datetime.to_datetime(write_date),
                    })
                res.update({instance.id: apps})
        ssh.close()
        return res
    
    def _create_backup_folder(self, backup_dir):
        ssh = self._connect()
        self._exec_cmd('mkdir %s' % backup_dir, ssh)
        self._exec_cmd('chmod 755 %s' % backup_dir, ssh)
        ssh.close()

    def _create_odoo_instance_zip_backup(self, instance, local_filepath):
        ssh = self._connect_or_raise()
        remote_dir = '/tmp/saas_odoo_backups'
        remote_name = os.path.splitext(os.path.basename(local_filepath))[0]
        remote_workdir = '%s/%s' % (remote_dir, remote_name)
        remote_filepath = '%s/%s' % (remote_dir, os.path.basename(local_filepath))
        container_name = 'psql_%s' % instance.technical_name
        db_name = instance.db_name or instance.technical_name
        filestore_path = '/home/%s/odoo-web-data/filestore/%s' % (instance.technical_name, db_name)
        cmd = (
            'set -e; '
            'rm -rf {remote_workdir} {remote_filepath}; '
            'mkdir -p {remote_workdir}; '
            'docker exec -e PGPASSWORD=odoo {container} '
            'pg_dump -U odoo -d {db_name} > {remote_workdir}/dump.sql; '
            'mkdir -p {remote_workdir}/filestore; '
            'if [ -d {filestore_path} ]; then '
            'cp -a {filestore_contents} {remote_workdir}/filestore/; '
            'fi; '
            'cd {remote_workdir}; '
            'python3 -m zipfile -c {remote_filepath} dump.sql filestore 2>/dev/null || '
            'python -m zipfile -c {remote_filepath} dump.sql filestore'
        ).format(
            remote_workdir=shlex.quote(remote_workdir),
            remote_filepath=shlex.quote(remote_filepath),
            container=shlex.quote(container_name),
            db_name=shlex.quote(db_name),
            filestore_path=shlex.quote(filestore_path),
            filestore_contents=shlex.quote(filestore_path + '/.'),
        )
        try:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            error = stderr.read().decode().strip()
            if exit_status:
                raise UserError(
                    _("Database backup error: backup packaging failed for %s. %s")
                    % (instance.display_name, error or _("Unknown Error."))
                )
            sftp = ssh.open_sftp()
            try:
                sftp.get(remote_filepath, local_filepath)
            finally:
                sftp.close()
        finally:
            if ssh:
                try:
                    self._exec_cmd(
                        'rm -rf %s %s' % (
                            shlex.quote(remote_workdir),
                            shlex.quote(remote_filepath),
                        ),
                        ssh,
                    )
                except Exception:
                    _logger.warning("Could not remove temporary backup files for %s", remote_filepath)
            ssh.close()
