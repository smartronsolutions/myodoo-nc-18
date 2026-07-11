# SaaS File Manager - VPS Setup Guide

This guide explains how to set up your Ubuntu 24 VPS to ensure the Odoo File Manager works securely and correctly.

## 1. Directory Permissions

The File Manager runs under the Odoo service user (usually `odoo`). For the file manager to read, upload, and delete files, the `odoo` user must have appropriate permissions on the instance folders.

Run this script to fix permissions on existing folders:

```bash
#!/bin/bash
# Fix permissions for all SaaS instance folders

# Set the base directory where instance folders are stored
BASE_DIR="/home"

# Set the Odoo user
ODOO_USER="odoo"

echo "Setting permissions for SaaS instance folders..."

# Find all folders that match the pattern and change ownership
# Assuming your folders look like odoososi01_myodoo_nc_06_01_2026
find $BASE_DIR -maxdepth 1 -type d -name "*_*" | while read folder; do
    echo "Processing $folder..."
    chown -R $ODOO_USER:$ODOO_USER "$folder"
    chmod -R 755 "$folder"
done

echo "Done!"
```

## 2. Automation for New Instances

When your SaaS system creates a new instance folder, ensure the creation script assigns ownership to the `odoo` user. 

If your instances are created by another user (e.g., `root`), add this to your instance creation script:

```bash
chown -R odoo:odoo /home/new_instance_folder_name
```

## 3. Security Considerations

The module includes built-in path traversal protection (`os.path.realpath` and path prefix checking). However, you should also ensure:

1. The `odoo` user does not have `sudo` privileges without a password.
2. The `odoo` user does not have access to sensitive system directories (`/root`, `/etc`).
3. If you're running Odoo in Docker, ensure the `/home` directory from the host is mounted correctly into the container with proper permissions.

## 4. Module Installation

1. Copy the `saas_file_manager` folder to your Odoo addons path.
2. Restart the Odoo service: `sudo systemctl restart odoo`
3. Activate Developer Mode in Odoo.
4. Go to Apps > Update Apps List.
5. Search for "SaaS File Manager" and install it.

## 5. Troubleshooting

**Error: "VPS folder not found for this instance"**
* Check if the folder actually exists in `/home`.
* Check if the folder name matches the pattern: `instance_name_with_underscores_*`.

**Error: "Permission denied accessing this folder"**
* The `odoo` user doesn't have read access. Run the permission script above.

**Error: Upload fails**
* The `odoo` user doesn't have write access. Run the permission script above.
* Check if the VPS has enough free disk space: `df -h`
