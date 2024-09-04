# -*- coding: utf-8 -*-
{
    "name": "Tax invoice report",
    "version": "17.0.0.0",
    "author": "Biztras",
    'website': 'https://biztras.com/',
    "category": "Tax invoice Report",
    "description": """Tax invoice Report""",
    "depends": ['account', 'l10n_ae'],
    'data': [
        'reports/tax_invoice_header.xml',
        'reports/tax_invoice_report.xml',
        'views/tax_invoice_report_field_views.xml',

    ],
    "application": False,

}
