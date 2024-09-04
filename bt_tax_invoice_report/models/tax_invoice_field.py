from odoo import api, models, _, fields


class TaxInvoice(models.Model):
    _inherit = 'account.move'

    project_name = fields.Char(string='Project Name', default='BNPP,AUH', required=True)
    location = fields.Char(string='Location', required=True)
    contract_ref = fields.Char(string='Contract Ref', required=True)
    customer_lpo = fields.Char(string='Customer LPO')

class ResCompany(models.Model):
    _inherit = 'res.company'

    bank_name = fields.Char(string='Bank Name')
    account_no = fields.Char(string='Account Number')
    iban_number = fields.Integer(string='IBAN Number')
    ben_no = fields.Char(string='Beneficiary Name')
