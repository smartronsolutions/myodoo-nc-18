{
    'name': 'SaaS File Manager',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Secure file manager for SaaS instance portals',
    'description': '''
        Provides secure file management (view, upload, delete) for SaaS customers.
        - Instance folder detection via technical_name
        - Path traversal protection
        - Per-instance access control
        - Simple and clean UI
        - Upload, Download, Edit, Delete files
        - Delete folders
    ''',
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'depends': ['portal', 'web', 's_odoo_saas_master'],
    'data': [
        'security/ir.model.access.csv',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'saas_file_manager/static/src/css/file_manager.css',
            'saas_file_manager/static/src/js/file_manager.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'application': False,
    'post_init_hook': 'post_init_hook',
}
