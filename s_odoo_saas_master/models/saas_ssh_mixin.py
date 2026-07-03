import logging
from odoo import models


_logger = logging.getLogger(__name__)


class SSHMixin(models.AbstractModel):
    _name = 'saas.ssh.mixin'
    _description = "SaaS SSH Mixin"

    def _exec_cmd(self, command, ssh, arguments=False, without_return=True):
        assert isinstance(command, str) and command
        command = command.strip()
        stdin, stdout, stderr = ssh.exec_command(command)
        if arguments:
            for arg in arguments:
                stdin.write('%s\n' % arg)
            stdin.flush()
        channel = stdout.channel
        channel.recv_exit_status()
        if not without_return:
            return stdout.readlines()

    def _create_file(self, ssh, file_path, file_content):
        sftp = ssh.open_sftp()
        f = sftp.open(file_path, 'w')
        f.write(file_content)
        f.close()
        sftp.close()
        return True

    def _create_symlink(self, ssh, from_path, to_path, overwrite=False):
        cmd = "ln -s"
        if overwrite:
            cmd += 'f'
        cmd += ' ' + from_path + ' ' + to_path

        return self._exec_cmd(cmd, ssh)
