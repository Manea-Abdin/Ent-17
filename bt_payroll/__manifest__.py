
{
    'name': 'Payroll Custom',
    'version': '17.0',
    'category': 'Payroll',
    'summary': 'Payroll module for Biztras',
    'description': "Added fields inside Salary Information tab of Employees ",
    'website': 'https://biztras.com/',
    'author' : 'Biztras',
    'depends': ['base', 'hr_contract'],
    'data': [
        'views/payroll_config_view.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': True,
    'license': 'OEEL-1',
}
