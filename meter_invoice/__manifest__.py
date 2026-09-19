{
    'name': 'Meter Reading Invoice',
    'version': '18.0.8.0.0',
    'category': 'Accounting',
    'depends': ['account', 'product'],
   'data': [
		'security/ir.model.access.csv',
		'data/customer_category_data.xml',
		'views/account_move_views.xml',
		'views/customer_category_views.xml',
		'views/meter_swap_wizard_views.xml',
		'views/partner_views.xml',
		'views/product_views.xml',
		'views/meter_history_views.xml',
		'report/invoice_report.xml',
	],
    'installable': True,
    'license': 'LGPL-3',
}
