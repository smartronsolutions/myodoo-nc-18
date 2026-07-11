# SaaS File Manager for Odoo

A secure file manager module for Odoo SaaS portals that allows customers to browse, upload, and delete files in their dedicated instance folders.

## Quick Start

1. **Copy module** to your Odoo addons directory
2. **Restart Odoo** service
3. **Install module** from Apps menu
4. **Fix VPS permissions** (see SETUP_GUIDE.md)
5. **Done!** File Manager button appears on instance portal pages

## Features

✅ Browse instance folders  
✅ Upload files  
✅ Download files  
✅ Delete files  
✅ Dynamic folder detection  
✅ Path traversal protection  
✅ Per-instance access control  

## File Structure

```
saas_file_manager/
├── controllers/main.py          # Backend logic
├── views/portal_templates.xml   # Frontend UI
├── security/ir.model.access.csv # Access control
├── __manifest__.py              # Module info
├── INSTALLATION_GUIDE.md        # Full documentation
├── SETUP_GUIDE.md              # VPS setup
└── README.md                    # This file
```

## How It Works

1. User clicks "File Manager" button on instance portal page
2. Module detects the instance's VPS folder automatically
3. User can browse, upload, and delete files
4. All operations are secured with path validation

## Example Instance Folder Detection

**Instance Name:** `odoososi01.myodoo.nc`  
**Normalized:** `odoososi01_myodoo_nc`  
**Pattern:** `/home/odoososi01_myodoo_nc_*`  
**Matched Folder:** `/home/odoososi01_myodoo_nc_06_01_2026`

## Security

* Path traversal protection with `realpath()` validation
* Per-instance access control
* CSRF token validation
* Secure filename handling
* User ownership verification

## Requirements

* Odoo 14+ (tested on 16+)
* Portal module installed
* s_odoo_saas_master module (your existing SaaS module)
* Ubuntu 24 VPS with proper permissions

## Installation

See `INSTALLATION_GUIDE.md` for detailed instructions.

## VPS Setup

See `SETUP_GUIDE.md` for VPS permission configuration.

## Support

For issues or questions, refer to the documentation files or contact your Odoo administrator.

---

**Version:** 1.0.0  
**License:** LGPL-3  
**Author:** Manus AI
