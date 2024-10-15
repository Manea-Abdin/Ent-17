# -*- coding: utf-8 -*-
{
    'name': 'Estimation',
    'version': '17.0',
    'website': 'https://www.biztras.com',
    'category': 'Marketing',
    'author': 'Biztras',
    'summary': 'Enhance purchase and sales order processes with job costing and validation checks.',
    'description': """
    Estimation Project Management
    ==============================
    This module extends the functionalities of the purchase and sales order processes by integrating job costing and validation checks. Key features include:

    - **Job Costing Integration**: Link purchase and sales orders to job costing records.
    - **Attachment Handling**: Ensure vendor quotations are uploaded before confirming purchase orders.
    - **Margin Calculation**: Support for various margin calculation methods (percentage, lump sum, linewise, etc.).
    - **Enhanced Views**: Add fields and views to manage job costing, purchase orders, and sales orders effectively.
    - **Approval Process**: Implement a double validation process for purchase orders based on company settings.
    - **Custom Actions**: Provide custom actions to create and view estimations, sales orders, and purchase orders.

    """,
    'depends': ['base', 'sale_management', 'purchase', 'crm', 'sale_crm',],
    'data': [
        'security/estimation_security.xml',
        'security/ir.model.access.csv',
        'views/estimation_view.xml',
        'views/jobcost_sequence.xml',
        'data/data_view.xml',
        'views/estimation_crm.xml'
    ],
    'installable': True,
    'auto_install': False,
}
