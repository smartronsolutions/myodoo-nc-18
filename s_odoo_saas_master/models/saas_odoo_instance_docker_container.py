from odoo import fields, models, api


class OdooIstanceDockerContainer(models.Model):
    _name = 'saas.odoo.instance.docker.container'
    _description = "SaaS Odoo Instance Docker Container"

    instance_id = fields.Many2one('saas.odoo.instance', string='Odoo Instance', required=True, ondelete='cascade')
    name = fields.Char(string='Name', required=True)
    image = fields.Char(string='Image', required=True)
    container_type = fields.Selection([
        ('odoo', 'Odoo'),
        ('psql', 'PSQL')
    ], string='Container Type', required=True)
    ports = fields.Char(string='Ports', compute='_compute_ports', store=True)
    docker_compose_volume_ids = fields.One2many('saas.odoo.instance.docker.compose.volume', 'container_id', string='Volumes')
    state = fields.Selection([
        ('unknown', 'Unknown'),
        ('run', 'Running'),
        ('stop', 'Stopped')
    ], string="Status", compute='_compute_state', compute_sudo=True)

    @api.depends(
        'container_type', 'instance_id',
        'instance_id.docker_xmlrpc_expose_port', 'instance_id.docker_xmlrpcs_expose_port', 'instance_id.docker_longpolling_expose_port',
        'instance_id.docker_xmlrpc_container_port', 'instance_id.docker_xmlrpcs_container_port', 'instance_id.docker_longpolling_container_port')
    def _compute_ports(self):
        for r in self:
            ports = 'Unknown'
            if r.instance_id:
                if r.container_type == 'odoo' and r.instance_id.docker_xmlrpc_expose_port:
                    ports = '%s->%s' % (r.instance_id.docker_xmlrpc_expose_port, r.instance_id.docker_xmlrpc_container_port)
                    ports += ', %s->%s' % (r.instance_id.docker_xmlrpcs_expose_port, r.instance_id.docker_xmlrpcs_container_port)
                    ports += ', %s->%s' % (r.instance_id.docker_longpolling_expose_port, r.instance_id.docker_longpolling_container_port)
                elif r.container_type == 'psql':
                    ports = '5432'
                r.ports = ports

    def _compute_state(self):
        results = {}
        for pserver in self.instance_id.pserver_id:
            containers = self.instance_id.filtered(lambda i: i.pserver_id == pserver and i.state in ('deploy', 'suspend')).docker_container_ids
            results.update(pserver._get_container_status(containers))
        for r in self:
            status = results.get(r.name, False)
            if status == 'running':
                r.state = 'run'
            elif status == 'exited':
                r.state = 'stop'
            else:
                r.state = 'unknown'

    def action_restart(self):
        for instance in self.instance_id:
            ssh = instance.pserver_id._connect()
            try:
                instance.pserver_id._exec_cmd(f"cd /home/{instance.technical_name} && docker-compose restart", ssh)
            finally:
                ssh.close()

    def action_stop(self):
        for instance in self.instance_id:
            ssh = instance.pserver_id._connect()
            try:
                # Use docker-compose stop to ensure all services are stopped consistently
                instance.pserver_id._exec_cmd(f"cd /home/{instance.technical_name} && docker-compose stop", ssh)
            finally:
                ssh.close()

        for instance in self.instance_id:
            if all(c.state == 'stop' for c in instance.docker_container_ids):
                instance.write({'operation_state': 'stop'})

    def action_start(self):
        for instance in self.instance_id:
            ssh = instance.pserver_id._connect()
            try:
                # Use docker-compose start to ensure all services start consistently
                instance.pserver_id._exec_cmd(f"cd /home/{instance.technical_name} && docker-compose start", ssh)
            finally:
                ssh.close()

        for instance in self.instance_id:
            if all(c.state == 'run' for c in instance.docker_container_ids):
                instance.write({'state': 'deploy', 'operation_state': 'run'})
