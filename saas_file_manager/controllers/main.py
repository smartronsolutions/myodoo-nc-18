import os
import logging
import werkzeug
from odoo import http, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

class SaaSFileManager(http.Controller):

    # Client instances run in Docker containers whose volumes are bind-mounted
    # to /home/{technical_name}/ on this host, so the master Odoo (running
    # directly on Ubuntu) can reach instance files via the local filesystem.
    INSTANCES_BASE_PATH = "/home"

    # Editable file extensions
    EDITABLE_EXTENSIONS = ['.txt', '.py', '.xml', '.csv', '.js', '.css', '.md', '.json', '.yml', '.yaml', '.sh', '.conf', '.ini']

    def _get_instance_base_path(self, instance):
        """Returns the instance's folder on the local filesystem."""
        if not instance.technical_name:
            _logger.warning(f"No technical_name for instance {instance.name}")
            return None

        base_path = os.path.join(self.INSTANCES_BASE_PATH, instance.technical_name)
        if not os.path.isdir(base_path):
            _logger.warning(f"Instance folder not found: {base_path}")
            return None

        return os.path.realpath(base_path)

    def _validate_path(self, base_path, requested_path):
        """Validates path and prevents traversal."""
        if not base_path:
            raise AccessError(_("Instance folder not found."))

        real_base_path = os.path.realpath(base_path)
        if not requested_path:
            return real_base_path

        full_requested_path = os.path.realpath(os.path.join(real_base_path, requested_path))
        if not full_requested_path.startswith(real_base_path):
            raise AccessError(_("Invalid path access detected."))

        return full_requested_path

    def _check_instance_access(self, instance_id):
        """Verifies portal user access."""
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if not instance.exists() or request.env.user.partner_id.id != instance.partner_id.id:
            raise AccessError(_("Access Denied."))
        return instance

    @http.route(['/my/saas/odoo-instance/<int:instance_id>/file-manager',
                 '/my/saas/odoo-instance/<int:instance_id>/file-manager/<path:folder_path>'],
                type='http', auth="user", website=True)
    def file_manager(self, instance_id, folder_path='', **kw):
        """Renders file manager UI."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)

            if not base_path:
                return request.render("saas_file_manager.error_page", {'error_message': _("Folder not found.")})

            current_path = self._validate_path(base_path, folder_path)
            folders, files = [], []

            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)
                stat_info = os.stat(item_path)
                is_dir = os.path.isdir(item_path)
                item_data = {
                    'name': item,
                    'size': stat_info.st_size,
                    'mtime': stat_info.st_mtime,
                    'path': os.path.relpath(item_path, base_path),
                    'is_dir': is_dir,
                    'is_editable': not is_dir and any(item.endswith(ext) for ext in self.EDITABLE_EXTENSIONS)
                }
                if is_dir:
                    folders.append(item_data)
                else:
                    files.append(item_data)

            folders.sort(key=lambda x: x['name'].lower())
            files.sort(key=lambda x: x['name'].lower())

            parent_path = os.path.dirname(folder_path) if folder_path else ''
            if parent_path == '/':
                parent_path = ''

            return request.render("saas_file_manager.portal_file_manager", {
                'instance': instance,
                'folders': folders,
                'files': files,
                'current_path': folder_path,
                'parent_path': parent_path,
                'page_name': 'file_manager',
            })

        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/upload',
                type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def upload_file(self, instance_id, current_path='', ufile=None, **kw):
        """Handles file uploads."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_dir = self._validate_path(base_path, current_path)

            if ufile:
                filename = werkzeug.utils.secure_filename(ufile.filename) or "unnamed_file"
                ufile.save(os.path.join(target_dir, filename))

            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
            return request.redirect(redirect_url)
        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/delete',
                type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def delete_file(self, instance_id, file_path='', current_path='', **kw):
        """Handles file deletion."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)

            if os.path.exists(target_file) and not os.path.isdir(target_file):
                os.remove(target_file)

            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
            return request.redirect(redirect_url)
        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/download',
                type='http', auth="user", website=True)
    def download_file(self, instance_id, file_path='', **kw):
        """Handles file downloading."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)

            filename = os.path.basename(target_file)
            with open(target_file, 'rb') as f:
                content = f.read()

            headers = [
                ('Content-Type', 'application/octet-stream'),
                ('Content-Disposition', content_disposition(filename)),
                ('Content-Length', len(content))
            ]
            return request.make_response(content, headers=headers)
        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/editor',
                type='http', auth="user", website=True)
    def edit_file(self, instance_id, file_path='', current_path='', **kw):
        """Renders the file editor UI."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)

            filename = os.path.basename(target_file)
            with open(target_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            return request.render("saas_file_manager.portal_file_editor", {
                'instance': instance,
                'file_path': file_path,
                'current_path': current_path,
                'filename': filename,
                'content': content,
                'page_name': 'file_manager',
            })
        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/save',
                type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def save_file(self, instance_id, file_path='', current_path='', file_content='', **kw):
        """Saves edited file content."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)

            with open(target_file, 'w', encoding='utf-8') as f:
                f.write(file_content)

            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
            return request.redirect(redirect_url)
        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/rename',
                type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def rename_file(self, instance_id, file_path='', current_path='', new_name='', **kw):
        """Handles file renaming."""
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)

            if not new_name:
                raise UserError(_("New filename cannot be empty"))

            new_name = werkzeug.utils.secure_filename(new_name)
            new_file_path = os.path.join(os.path.dirname(target_file), new_name)

            if os.path.exists(target_file):
                os.rename(target_file, new_file_path)

            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
            return request.redirect(redirect_url)
        except Exception as e:
            return request.render("saas_file_manager.error_page", {'error_message': str(e)})
