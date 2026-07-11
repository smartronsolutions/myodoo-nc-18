import os
import glob
import logging
import werkzeug
from odoo import http, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

class SaaSFileManager(http.Controller):

    def _get_instance_base_path(self, instance):
        """
        Detects the correct VPS folder for the instance.
        Example instance name: odoososi01.myodoo.nc
        Expected folder pattern: /home/odoososi01_myodoo_nc_*
        """
        # Get instance name from the instance object
        instance_name = instance.name if hasattr(instance, 'name') else str(instance)
        
        # Normalize instance name: remove spaces, replace dots with underscores
        normalized_name = instance_name.replace(' ', '').replace('.', '_')
        
        _logger.info(f"Searching for instance folder with normalized name: {normalized_name}")
        
        # Base pattern to search
        search_pattern = f"/home/{normalized_name}_*"
        
        _logger.info(f"Search pattern: {search_pattern}")
        
        # Find matching directories
        matching_dirs = glob.glob(search_pattern)
        
        _logger.info(f"Found {len(matching_dirs)} matching directories: {matching_dirs}")
        
        if not matching_dirs:
            _logger.warning(f"No folder found matching pattern: {search_pattern}")
            # Also try searching without the trailing underscore
            alt_pattern = f"/home/{normalized_name}"
            if os.path.isdir(alt_pattern):
                _logger.info(f"Found alternative folder: {alt_pattern}")
                return os.path.realpath(alt_pattern)
            return None
            
        # Get the first matching directory and ensure it's a directory
        base_path = matching_dirs[0]
        if not os.path.isdir(base_path):
            _logger.warning(f"Path is not a directory: {base_path}")
            return None
            
        _logger.info(f"Using instance folder: {base_path}")
        return os.path.realpath(base_path)

    def _validate_path(self, base_path, requested_path):
        """
        Validates that the requested path is within the base path to prevent path traversal.
        """
        if not base_path:
            raise AccessError(_("Instance folder not found."))
            
        # Resolve real paths
        real_base_path = os.path.realpath(base_path)
        
        # If no requested path, return base path
        if not requested_path:
            return real_base_path
            
        # Join and resolve requested path
        full_requested_path = os.path.realpath(os.path.join(real_base_path, requested_path))
        
        # Check if the requested path starts with the base path
        if not full_requested_path.startswith(real_base_path):
            raise AccessError(_("Invalid path access detected."))
            
        return full_requested_path

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

    @http.route(['/my/saas/odoo-instance/<int:instance_id>/file-manager', 
                 '/my/saas/odoo-instance/<int:instance_id>/file-manager/<path:folder_path>'], 
                type='http', auth="user", website=True)
    def file_manager(self, instance_id, folder_path='', **kw):
        """
        Renders the file manager UI for a specific instance.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            
            if not base_path:
                return request.render("saas_file_manager.error_page", {
                    'error_message': _("VPS folder not found for this instance. Please contact support.")
                })
                
            current_path = self._validate_path(base_path, folder_path)
            
            if not os.path.exists(current_path) or not os.path.isdir(current_path):
                raise UserError(_("Directory does not exist."))
                
            # Get directory contents
            files = []
            folders = []
            
            try:
                for item in os.listdir(current_path):
                    item_path = os.path.join(current_path, item)
                    stat = os.stat(item_path)
                    
                    item_data = {
                        'name': item,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'path': os.path.relpath(item_path, base_path),
                        'is_dir': os.path.isdir(item_path)
                    }
                    
                    if item_data['is_dir']:
                        folders.append(item_data)
                    else:
                        files.append(item_data)
            except PermissionError:
                return request.render("saas_file_manager.error_page", {
                    'error_message': _("Permission denied accessing this folder.")
                })
                
            # Sort folders and files alphabetically
            folders.sort(key=lambda x: x['name'].lower())
            files.sort(key=lambda x: x['name'].lower())
            
            # Calculate parent path for 'Up' button
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
            }
            
            return request.render("saas_file_manager.portal_file_manager", values)
            
        except AccessError as e:
            return request.redirect('/my')
        except Exception as e:
            _logger.exception("File manager error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/upload', type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def upload_file(self, instance_id, current_path='', ufile=None, **kw):
        """
        Handles file uploads to the specified path.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_dir = self._validate_path(base_path, current_path)
            
            if not ufile:
                raise UserError(_("No file uploaded."))
                
            if not os.path.isdir(target_dir):
                raise UserError(_("Target directory does not exist."))
                
            # Secure filename
            filename = werkzeug.utils.secure_filename(ufile.filename)
            if not filename:
                filename = "unnamed_file"
                
            file_path = os.path.join(target_dir, filename)
            
            # Save file
            ufile.save(file_path)
            
            # Redirect back to file manager
            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
                
            return request.redirect(redirect_url)
            
        except Exception as e:
            _logger.exception("File upload error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/delete', type='http', auth="user", methods=['POST'], website=True, csrf=True)
    def delete_file(self, instance_id, file_path='', current_path='', **kw):
        """
        Handles file deletion.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)
            
            if not os.path.exists(target_file):
                raise UserError(_("File does not exist."))
                
            if os.path.isdir(target_file):
                raise UserError(_("Cannot delete directories, only files."))
                
            # Delete file
            os.remove(target_file)
            
            # Redirect back to file manager
            redirect_url = f"/my/saas/odoo-instance/{instance_id}/file-manager"
            if current_path:
                redirect_url += f"/{current_path}"
                
            return request.redirect(redirect_url)
            
        except Exception as e:
            _logger.exception("File delete error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })

    @http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/download', type='http', auth="user", website=True)
    def download_file(self, instance_id, file_path='', **kw):
        """
        Handles file downloading.
        """
        try:
            instance = self._check_instance_access(instance_id)
            base_path = self._get_instance_base_path(instance)
            target_file = self._validate_path(base_path, file_path)
            
            if not os.path.exists(target_file) or os.path.isdir(target_file):
                raise UserError(_("File not found."))
                
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
            _logger.exception("File download error")
            return request.render("saas_file_manager.error_page", {
                'error_message': str(e)
            })
