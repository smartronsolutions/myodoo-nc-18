import os
import glob
import logging
import werkzeug
import paramiko
import io
from odoo import http, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

class SaaSFileManager(http.Controller):

    # VPS Connection Details (Configure these)
    VPS_HOST = "208.87.135.215"
    VPS_USER = "root"
    VPS_PASSWORD = "Sosi771180!!!"
    VPS_BASE_PATH = "/home"
    
    # Try local access first, then SFTP
    USE_LOCAL_ACCESS = True
    USE_SFTP_FALLBACK = True

    def _get_sftp_client(self):
        """
        Creates and returns an SFTP client connected to the VPS.
        """
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.VPS_HOST,
                username=self.VPS_USER,
                password=self.VPS_PASSWORD,
                timeout=10
            )
            sftp = ssh.open_sftp()
            return sftp, ssh
        except Exception as e:
            _logger.error(f"SFTP connection failed: {e}")
            return None, None

    def _get_instance_base_path(self, instance):
        """
        Detects the correct VPS folder for the instance.
        Tries local access first, then SFTP.
        """
        instance_name = instance.name if hasattr(instance, 'name') else str(instance)
        normalized_name = instance_name.replace(' ', '').replace('.', '_')
        
        _logger.info(f"Searching for instance folder: {normalized_name}")
        
        # Try 1: Local filesystem access
        if self.USE_LOCAL_ACCESS:
            search_pattern = f"{self.VPS_BASE_PATH}/{normalized_name}_*"
            matching_dirs = glob.glob(search_pattern)
            
            if matching_dirs:
                base_path = matching_dirs[0]
                if os.path.isdir(base_path):
                    _logger.info(f"Found via local access: {base_path}")
                    return base_path, "local"
        
        # Try 2: SFTP access (for Docker containers)
        if self.USE_SFTP_FALLBACK:
            _logger.info("Trying SFTP access...")
            sftp, ssh = self._get_sftp_client()
            
            if sftp:
                try:
                    # List /home directory
                    files = sftp.listdir_attr(self.VPS_BASE_PATH)
                    
                    # Find matching folder
                    for attr in files:
                        if normalized_name in attr.filename:
                            folder_path = f"{self.VPS_BASE_PATH}/{attr.filename}"
                            _logger.info(f"Found via SFTP: {folder_path}")
                            return folder_path, "sftp"
                finally:
                    sftp.close()
                    ssh.close()
        
        _logger.warning(f"No folder found for: {normalized_name}")
        return None, None

    def _validate_path(self, base_path, requested_path, access_type="local"):
        """
        Validates that the requested path is within the base path.
        """
        if not base_path:
            raise AccessError(_("Instance folder not found."))
        
        if access_type == "local":
            # Local path validation
            real_base_path = os.path.realpath(base_path)
            
            if not requested_path:
                return real_base_path
            
            full_requested_path = os.path.realpath(os.path.join(real_base_path, requested_path))
            
            if not full_requested_path.startswith(real_base_path):
                raise AccessError(_("Invalid path access detected."))
            
            return full_requested_path
        
        elif access_type == "sftp":
            # SFTP path validation (simpler, just concatenate)
            if not requested_path:
                return base_path
            
            # Prevent path traversal
            if ".." in requested_path or requested_path.startswith("/"):
                raise AccessError(_("Invalid path access detected."))
            
            return f"{base_path}/{requested_path}".replace("//", "/")
        
        return None

    def _check_instance_access(self, instance_id):
        """
        Verifies that the current portal user has access to this instance.
        """
        instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
        if not instance.exists():
            raise AccessError(_("Instance not found."))
        
        if request.env.user.partner_id.id != instance.partner_id.id:
            raise AccessError(_("You do not have access to this instance."))
        
        return instance

    def _list_files_local(self, path):
        """List files using local filesystem access."""
        files = []
        folders = []
        
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                stat = os.stat(item_path)
                
                item_data = {
                    'name': item,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'path': os.path.relpath(item_path, path),
                    'is_dir': os.path.isdir(item_path)
                }
                
                if item_data['is_dir']:
                    folders.append(item_data)
                else:
                    files.append(item_data)
        except PermissionError:
            raise UserError(_("Permission denied accessing this folder."))
        
        return folders, files

    def _list_files_sftp(self, sftp, path):
        """List files using SFTP access."""
        files = []
        folders = []
        
        try:
            items = sftp.listdir_attr(path)
            
            for attr in items:
                item_data = {
                    'name': attr.filename,
                    'size': attr.st_size,
                    'mtime': attr.st_mtime,
                    'path': f"{path}/{attr.filename}".replace("//", "/"),
                    'is_dir': paramiko.stat.S_ISDIR(attr.st_mode)
                }
                
                if item_data['is_dir']:
                    folders.append(item_data)
                else:
                    files.append(item_data)
        except Exception as e:
            _logger.error(f"SFTP list error: {e}")
            raise UserError(_("Error accessing folder."))
        
        return folders, files

    @http.route(['/my/saas/odoo-instance/<int:instance_id>/file-manager', 
                 '/my/saas/odoo-instance/<int:instance_id>/file-manager/<path:folder_path>'], 
                type='http', auth="user", website=True)
    def file_manager(self, instance_id, folder_path='', **kw):
        """
        Renders the file manager UI for a specific instance.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path, access_type = self._get_instance_base_path(instance)
            
            if not base_path:
                return request.render("saas_file_manager.error_page", {
                    'error_message': _("VPS folder not found for this instance. Please contact support.")
                })
            
            current_path = self._validate_path(base_path, folder_path, access_type)
            
            # Get file listing based on access type
            if access_type == "local":
                if not os.path.exists(current_path) or not os.path.isdir(current_path):
                    raise UserError(_("Directory does not exist."))
                folders, files = self._list_files_local(current_path)
            
            elif access_type == "sftp":
                sftp, ssh = self._get_sftp_client()
                if not sftp:
                    raise UserError(_("Cannot connect to VPS."))
                
                try:
                    folders, files = self._list_files_sftp(sftp, current_path)
                finally:
                    sftp.close()
                    ssh.close()
            
            # Sort
            folders.sort(key=lambda x: x['name'].lower())
            files.sort(key=lambda x: x['name'].lower())
            
            # Calculate parent path
            parent_path = ''
            if folder_path:
                parent_path = os.path.dirname(folder_path)
                if parent_path == '/':
                    parent_path = ''
            
            values = {
                'instance': instance,
                'folders': folders,
                'files': files,
                'current_path': folder_path,
                'parent_path': parent_path,
                'page_name': 'file_manager',
                'access_type': access_type,
            }
            
            return request.render("saas_file_manager.portal_file_manager", values)
        
        except AccessError as e:
            return request.redirect('/my')
        except Exception as e:
            _logger.exception("File manager error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/upload', 
                type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def upload_file(self, instance_id, current_path='', ufile=None, **kw):
        """
        Handles file uploads to the specified path.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path, access_type = self._get_instance_base_path(instance)
            target_dir = self._validate_path(base_path, current_path, access_type)
            
            if not ufile:
                raise UserError(_("No file uploaded."))
            
            filename = werkzeug.utils.secure_filename(ufile.filename)
            if not filename:
                filename = "unnamed_file"
            
            if access_type == "local":
                if not os.path.isdir(target_dir):
                    raise UserError(_("Target directory does not exist."))
                
                file_path = os.path.join(target_dir, filename)
                ufile.save(file_path)
            
            elif access_type == "sftp":
                sftp, ssh = self._get_sftp_client()
                if not sftp:
                    raise UserError(_("Cannot connect to VPS."))
                
                try:
                    file_path = f"{target_dir}/{filename}".replace("//", "/")
                    
                    # Upload file via SFTP
                    with io.BytesIO(ufile.read()) as f:
                        sftp.putfo(f, file_path)
                finally:
                    sftp.close()
                    ssh.close()
            
            # Redirect back
            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
            
            return request.redirect(redirect_url)
        
        except Exception as e:
            _logger.exception("File upload error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/delete', 
                type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def delete_file(self, instance_id, file_path='', current_path='', **kw):
        """
        Handles file deletion.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path, access_type = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path, access_type)
            
            if access_type == "local":
                if not os.path.exists(target_file):
                    raise UserError(_("File does not exist."))
                
                if os.path.isdir(target_file):
                    raise UserError(_("Cannot delete directories, only files."))
                
                os.remove(target_file)
            
            elif access_type == "sftp":
                sftp, ssh = self._get_sftp_client()
                if not sftp:
                    raise UserError(_("Cannot connect to VPS."))
                
                try:
                    sftp.remove(target_file)
                finally:
                    sftp.close()
                    ssh.close()
            
            # Redirect back
            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
            
            return request.redirect(redirect_url)
        
        except Exception as e:
            _logger.exception("File delete error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/download', 
                type='http', auth="user", website=True)
    def download_file(self, instance_id, file_path='', **kw):
        """
        Handles file downloading.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path, access_type = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path, access_type)
            
            filename = os.path.basename(target_file)
            
            if access_type == "local":
                if not os.path.exists(target_file) or os.path.isdir(target_file):
                    raise UserError(_("File not found."))
                
                with open(target_file, 'rb') as f:
                    content = f.read()
            
            elif access_type == "sftp":
                sftp, ssh = self._get_sftp_client()
                if not sftp:
                    raise UserError(_("Cannot connect to VPS."))
                
                try:
                    with io.BytesIO() as f:
                        sftp.getfo(target_file, f)
                        content = f.getvalue()
                finally:
                    sftp.close()
                    ssh.close()
            
            headers = [
                ('Content-Type', 'application/octet-stream'),
                ('Content-Disposition', content_disposition(filename)),
                ('Content-Length', len(content))
            ]
            
            return request.make_response(content, headers=headers)
        
        except Exception as e:
            _logger.exception("File download error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })
