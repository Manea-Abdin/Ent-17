from odoo import models, fields


class HRContract(models.Model):
    _inherit = "hr.contract"

    wage = fields.Monetary('Basic Salary', required=True, tracking=True, help="Employee's monthly gross wage.")
    fixed_overtime = fields.Monetary(string="Fixed Overtime")
    cost_of_living = fields.Monetary(string="Cost of Living Allowance")
    car_children_allowance = fields.Monetary(string="Car & Children Allowances")
    air_ticket = fields.Monetary(string="Air Ticket Allowance ")

