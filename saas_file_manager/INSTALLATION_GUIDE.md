# SaaS File Manager - Complete Installation & Integration Guide

## Overview

The **SaaS File Manager** is a secure Odoo portal module that allows SaaS customers to manage files on their dedicated VPS instance folders. It provides view, upload, and delete capabilities with built-in path traversal protection.

## Features

* **Secure File Browsing** - Browse files and folders within the instance's VPS directory
* **File Upload** - Upload files directly to any folder
* **File Download** - Download files from the instance folder
* **File Deletion** - Delete files with confirmation
* **Dynamic Folder Detection** - Automatically finds the correct instance folder using glob patterns
* **Path Traversal Protection** - Prevents access to unauthorized directories
* **Per-Instance Access Control** - Users can only access their own instance folders

## Module Structure

```
saas_file_manager/
├── __init__.py                 # Module initialization
├── __manifest__.py             # Module metadata
├── controllers/
│   ├── __init__.py
│   └── main.py                 # File manager routes and logic
├── security/
│   └── ir.model.access.csv     # Access control rules
├── views/
│   └── portal_templates.xml    # QWeb templates
├── static/
│   └── src/
│       ├── css/                # (Optional) Custom CSS
│       └── js/                 # (Optional) Custom JavaScript
├── SETUP_GUIDE.md              # VPS setup instructions
└── INSTALLATION_GUIDE.md       # This file
```

## Installation Steps

### Step 1: Copy Module to Odoo Addons

```bash
# Copy the saas_file_manager folder to your Odoo addons directory
cp -r saas_file_manager /path/to/odoo/addons/

# Or if using a custom addons path
cp -r saas_file_manager /var/lib/odoo/addons/
```

### Step 2: Restart Odoo Service

```bash
sudo systemctl restart odoo
```

### Step 3: Install Module in Odoo

1. Log in to your Odoo instance as an administrator
2. Go to **Apps** menu
3. Click **Update Apps List** (top-right)
4. Search for "**SaaS File Manager**"
5. Click the module and press **Install**

### Step 4: Configure VPS Permissions

Follow the instructions in `SETUP_GUIDE.md` to ensure the Odoo user has proper permissions on instance folders.

## How It Works

### User Flow

1. Portal user navigates to their SaaS instance detail page
2. Clicks the **File Manager** button (visible when instance is running)
3. File manager loads the instance's VPS folder
4. User can browse, upload, and delete files

### Backend Process

1. **Instance Validation** - Verifies the user owns the instance
2. **Folder Detection** - Converts instance name to folder pattern and finds matching directory
   * Example: `odoososi01.myodoo.nc` → `/home/odoososi01_myodoo_nc_*`
3. **Path Validation** - Ensures requested path is within the instance folder (prevents path traversal)
4. **File Operation** - Performs the requested action (list, upload, delete)

## Integration with Existing Module

### Adding the File Manager Button

The module automatically injects a "File Manager" button into your existing portal instance page. The button appears when:

* Instance state is "deploy"
* Instance operation state is "run" (running)

The button is added via template inheritance:

```xml
<template id="portal_instance_page_inherit_file_manager" 
          inherit_id="s_odoo_saas_master.portal_instance_page">
    <xpath expr="//div[hasclass('btn-toolbar')]" position="inside">
        <div t-if="instance.operation_state == 'run' and instance.state == 'deploy'" 
             class="btn-group flex-grow-1 mx-1 mt-2">
            <a class="btn btn-block btn-info o_instance_file_manager" 
               t-attf-href="/my/saas/odoo-instance/{{ instance.id }}/file-manager" 
               title="File Manager" target="_blank">
                <i class="fa fa-fw fa-folder-open"/> File Manager
            </a>
        </div>
    </xpath>
</template>
```

This inherits from your existing `s_odoo_saas_master.portal_instance_page` template and adds the button to the button toolbar.

## Routes & Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/my/saas/odoo-instance/<id>/file-manager` | GET | Display file manager UI |
| `/my/saas/odoo-instance/<id>/file-manager/<path>` | GET | Browse specific folder |
| `/my/saas/odoo-instance/<id>/file-manager/upload` | POST | Upload file |
| `/my/saas/odoo-instance/<id>/file-manager/delete` | POST | Delete file |
| `/my/saas/odoo-instance/<id>/file-manager/download` | GET | Download file |

## Security Features

### 1. Path Traversal Prevention

The module uses `os.path.realpath()` to resolve paths and verifies that the resolved path starts with the allowed base directory.

```python
def _validate_path(self, base_path, requested_path):
    real_base_path = os.path.realpath(base_path)
    full_requested_path = os.path.realpath(os.path.join(real_base_path, requested_path))
    
    if not full_requested_path.startswith(real_base_path):
        raise AccessError(_("Invalid path access detected."))
    
    return full_requested_path
```

### 2. Instance Ownership Verification

Every request verifies that the portal user owns the instance:

```python
def _check_instance_access(self, instance_id):
    instance = request.env['saas.odoo.instance'].sudo().browse(instance_id)
    if request.env.user.partner_id.id != instance.partner_id.id:
        raise AccessError(_("You do not have access to this instance."))
    return instance
```

### 3. Secure Filename Handling

File uploads use `werkzeug.utils.secure_filename()` to prevent malicious filenames:

```python
filename = werkzeug.utils.secure_filename(ufile.filename)
```

### 4. CSRF Protection

All POST requests include CSRF token validation (built into Odoo).

## Customization

### Changing the Button Style

Edit `portal_templates.xml` to modify button appearance:

```xml
<a class="btn btn-block btn-info o_instance_file_manager" 
   t-attf-href="/my/saas/odoo-instance/{{ instance.id }}/file-manager" 
   title="File Manager" target="_blank">
    <i class="fa fa-fw fa-folder-open"/> File Manager
</a>
```

Change `btn-info` to `btn-primary`, `btn-success`, etc.

### Adding Custom CSS

Create a CSS file in `static/src/css/file_manager.css`:

```css
.o_instance_file_manager {
    /* Your custom styles */
}
```

### Restricting File Types

To prevent certain file types from being uploaded, modify the upload route in `controllers/main.py`:

```python
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'}

@http.route('/my/saas/odoo-instance/<int:instance_id>/file-manager/upload', ...)
def upload_file(self, instance_id, current_path='', ufile=None, **kw):
    # ... existing code ...
    
    filename = werkzeug.utils.secure_filename(ufile.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if file_ext not in ALLOWED_EXTENSIONS:
        raise UserError(_("File type not allowed."))
    
    # ... rest of the code ...
```

## Troubleshooting

### Issue: "File Manager" button doesn't appear

**Possible Causes:**
* Module not installed - Check if "SaaS File Manager" is in installed apps
* Instance not running - Button only shows when instance is deployed and running
* Template not inherited correctly - Check if `s_odoo_saas_master.portal_instance_page` exists

**Solution:**
1. Verify module is installed: Go to Apps > Search "SaaS File Manager"
2. Check instance state in Odoo backend
3. Clear browser cache and refresh

### Issue: "VPS folder not found"

**Possible Causes:**
* Folder doesn't exist on VPS
* Folder naming doesn't match pattern
* Glob pattern not matching

**Solution:**
1. SSH into VPS and check: `ls -la /home/ | grep instance_name`
2. Verify folder name format: `instance_name_with_underscores_DD_MM_YYYY`
3. Check Odoo logs: `tail -f /var/log/odoo/odoo-server.log`

### Issue: "Permission denied"

**Possible Causes:**
* Odoo user doesn't own the folder
* Folder permissions are too restrictive

**Solution:**
```bash
sudo chown -R odoo:odoo /home/instance_folder_name
sudo chmod -R 755 /home/instance_folder_name
```

### Issue: File upload fails

**Possible Causes:**
* Not enough disk space
* Odoo user doesn't have write permissions
* File size exceeds limit

**Solution:**
1. Check disk space: `df -h`
2. Fix permissions (see above)
3. Increase upload limit in Odoo configuration if needed

## Performance Considerations

* **Large Directories** - If a folder contains thousands of files, listing may be slow. Consider implementing pagination.
* **Large File Uploads** - Configure Odoo's file size limits if needed.
* **Network** - File operations depend on network speed between Odoo server and VPS.

## Support & Maintenance

For issues or feature requests, refer to the module's documentation or contact your Odoo administrator.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-05-07 | Initial release |

## License

LGPL-3
