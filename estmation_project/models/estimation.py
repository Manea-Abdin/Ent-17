# -*- coding: utf-8 -*-

from datetime import date
from datetime import datetime
from odoo.exceptions import UserError, ValidationError
from odoo import models, fields, api, _
from odoo.addons import decimal_precision as dp


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    job_cost_id = fields.Many2one(
        'job.costing',
        string='Estimation',
        readonly=True,
        copy=False
    )
    message_main_attachment_id = fields.Many2one(
        comodel_name='ir.attachment',
        string="Main Attachment",
        copy=False
    )

    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order.company_id.po_double_validation == 'one_step' \
                    or (order.company_id.po_double_validation == 'two_step' \
                        and order.amount_total < self.env.user.company_id.currency_id._convert(
                        order.company_id.po_double_validation_amount, order.currency_id, order.company_id,
                        order.date_order or fields.Date.today())) \
                    or order.user_has_groups('purchase.group_purchase_manager'):
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            if not order.message_main_attachment_id:
                raise ValidationError(_('No Attachment! Please upload vendor quotation.'))

        return True

    #     @api.onchange('partner_id', 'company_id')
    #     def onchange_partner_id(self):
    #         if self.job_cost_id:
    #             print(l)
    #
    #         if not self.partner_id:
    #             self.fiscal_position_id = False
    #             self.payment_term_id = False
    #             self.currency_id = self.env.user.company_id.currency_id.id
    #         else:
    #             self.fiscal_position_id = self.env['account.fiscal.position'].with_context(company_id=self.company_id.id).get_fiscal_position(self.partner_id.id)
    #             self.payment_term_id = self.partner_id.property_supplier_payment_term_id.id
    #             self.currency_id = self.partner_id.property_purchase_currency_id.id or self.env.user.company_id.currency_id.id
    #         return {}

    @api.onchange('job_cost_id')
    def _onchange_job_cost_id(self):
        order_lines = []
        for mline in self.job_cost_id.job_cost_line_ids:
            lines = {}
            if mline.product_qty:
                price = mline.margin_total / mline.product_qty
            else:
                price = 0.00
            a = mline.product_id.write({'standard_price': price})
            lines = {
                'product_id': mline.product_id.id,
                'name': mline.description,
                'product_qty': mline.product_qty,
                #                 'order_id':purchase.id,
                'date_planned': datetime.now(),
                'product_uom': mline.uom_id.id,
                'price_unit': mline.margin_total,
                'account_analytic_id': self.job_cost_id.analytic_id.id
            }
            order_lines.append((0, 0, lines))
        for lline in self.job_cost_id.job_labour_line_ids:
            lines = {}
            if lline.hours:
                price = lline.margin_total / lline.hours
            else:
                price = 0.00
            l = lline.product_id.write({'standard_price': price})
            lines = {
                'product_id': lline.product_id.id,
                'name': lline.description,
                'product_qty': lline.hours,
                'price_unit': 1.00,
                #                 'order_id':purchase.id,
                'date_planned': datetime.now(),
                'product_uom': 1,
                'account_analytic_id': self.job_cost_id.analytic_id.id
            }
            order_lines.append((0, 0, lines))
        for oline in self.job_cost_id.job_overhead_line_ids:
            lines = {}
            if oline.product_qty:
                price = oline.margin_total / oline.product_qty
            else:
                price = 0.00
            o = oline.product_id.write({'standard_price': price})
            lines = {
                'product_id': oline.product_id.id,
                'name': oline.description,
                'product_qty': oline.product_qty,
                'price_unit': oline.margin_total,
                #                 'order_id':purchase.id,
                'date_planned': datetime.now(),
                'product_uom': oline.uom_id.id,
                'account_analytic_id': self.job_cost_id.analytic_id.id
            }
            order_lines.append((0, 0, lines))
        self.order_line = order_lines

    def action_view_estimate(self):
        self.ensure_one()
        job_obj = self.env['job.costing']
        cost_ids = job_obj.search([('id', '=', self.job_cost_id.id)]).ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Sale Order',
            'res_model': 'job.costing',
            'res_id': self.id,
            'domain': "[('id','in',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'target': self.id,
        }
        return action


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    price_unit = fields.Float(string='Unit Price', default=0.00, digits=dp.get_precision('Product Price'))

    @api.depends('product_qty', 'price_unit', 'taxes_id')
    def _compute_amount(self):
        for line in self:
            vals = line._prepare_compute_all_values()
            if line.price_unit:
                price = line.price_unit
            else:
                price = vals['product'].standard_price
            taxes = line.taxes_id.compute_all(
                price,
                vals['currency_id'],
                vals['product_qty'],
                vals['product'],
                vals['partner'])
            if not line.price_unit:
                line.update({
                    'price_unit': vals['product'].standard_price, })

            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })

    def _prepare_compute_all_values(self):
        self.ensure_one()
        return {
            'price_unit': self.price_unit,
            'currency_id': self.order_id.currency_id,
            'product_qty': self.product_qty,
            'product': self.product_id,
            'partner': self.order_id.partner_id,
        }


class SaleOrder(models.Model):
    _inherit = "sale.order"

    job_cost_id = fields.Many2one(
        'job.costing',
        string='Estimation',
        readonly=True, copy=False
    )

    def action_view_estimate(self):
        self.ensure_one()
        job_obj = self.env['job.costing']
        cost_ids = job_obj.search([('id', '=', self.job_cost_id.id)]).ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Sale Order',
            'res_model': 'job.costing',
            'res_id': self.id,
            'domain': "[('id','in',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'target': self.id,
        }
        return action


class JobCosting(models.Model):
    _name = 'job.costing'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']  # odoo11
    #    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _description = "Job Costing"
    _rec_name = 'number'

    @api.model
    def create(self, vals):
        number = self.env['ir.sequence'].next_by_code('job.costing')
        vals.update({
            'number': number,
        })

        if vals['calculation_method_material'] == 'percentage':
            if vals['perc_material'] and vals.get('job_cost_line_ids', False):
                for cline in vals['job_cost_line_ids']:
                    cline[2].update(
                        {'margin': (cline[2]['product_qty'] * cline[2]['cost_price']) * (vals['perc_material'] / 100)})
        if vals['calculation_method_material'] == 'lumsum':
            if vals['lumsum_material'] and vals.get('job_cost_line_ids', False):
                material_total = sum([(p[2]['product_qty'] * p[2]['cost_price']) for p in vals['job_cost_line_ids']])

                for cline in vals['job_cost_line_ids']:
                    if material_total:
                        cline[2]['margin'] = (float(vals['lumsum_material'] / material_total) * (
                                cline[2]['product_qty'] * cline[2]['cost_price']))
            if not vals['lumsum_material']:
                raise ValidationError(_('Please fill up the lumsum amount.'))

        if vals['calculation_method_overhead'] == 'percentage':
            if vals['perc_overhead'] and vals.get('job_overhead_line_ids', False):
                for cline in vals['job_overhead_line_ids']:
                    cline[2].update(
                        {'margin': (cline[2]['product_qty'] * cline[2]['cost_price']) * (vals['perc_overhead'] / 100)})

        if vals['calculation_method_overhead'] == 'lumsum':
            if vals['lumsum_overhead'] and vals.get('job_overhead_line_ids', False):
                overhead_total = sum(
                    [(p[2]['product_qty'] * p[2]['cost_price']) for p in vals['job_overhead_line_ids']])

                for cline in vals['job_overhead_line_ids']:
                    if overhead_total:
                        cline[2]['margin'] = (float(vals['lumsum_overhead'] / overhead_total) * (
                                cline[2]['product_qty'] * cline[2]['cost_price']))
            if not vals['lumsum_overhead']:
                raise ValidationError(_('Please fill up the lumsum amount.'))

        if vals['calculation_method_labour'] == 'percentage':
            if vals['perc_labour'] and vals.get('job_labour_line_ids', False):

                for cline in vals['job_labour_line_ids']:
                    cline[2]['margin'] = (cline[2]['hours'] * cline[2]['cost_price']) * (vals['perc_labour'] / 100)

        if vals['calculation_method_labour'] == 'lumsum':
            if vals['lumsum_labour'] and vals.get('job_labour_line_ids', False):
                labour_total = sum([(p[2]['hours'] * p[2]['cost_price']) for p in vals['job_labour_line_ids']])

                for cline in vals['job_labour_line_ids']:
                    if labour_total:
                        cline[2]['margin'] = (float(vals['lumsum_labour'] / labour_total) * (
                                cline[2]['hours'] * cline[2]['cost_price']))
                    else:
                        cline[2].update({'margin': vals['lumsum_labour']})
            if not vals['lumsum_labour']:
                raise ValidationError(_('Please fill up the lumsum amount.'))
        result = super(JobCosting, self).create(vals)
        return result

    def _write(self, vals):
        for self1 in self:
            res = super(JobCosting, self1)._write(vals)
            if self1.calculation_method_material == 'percentage':
                if self1.perc_material:
                    for cline in self1.job_cost_line_ids:
                        cline.margin = (cline.product_qty * cline.cost_price) * (cline.direct_id.perc_material / 100)

            if self1.calculation_method_material == 'lumsum':
                if self1.lumsum_material:
                    material_total = sum([(p.product_qty * p.cost_price) for p in self1.job_cost_line_ids])
                    for cline in self1.job_cost_line_ids:
                        if material_total:
                            cline.margin = (float(cline.direct_id.lumsum_material / cline.direct_id.material_total) * (
                                    cline.product_qty * cline.cost_price))

            if self1.calculation_method_material == 'linewise':
                for cline in self1.job_cost_line_ids:
                    cline.margin_total = (cline.product_qty * cline.cost_price) + cline.margin

            if self1.calculation_method_material == 'line_by_per':
                for lab in self1.job_cost_line_ids:
                    lab.margin_total = (lab.margin / 100 * lab.total_cost) + lab.total_cost

            if self1.calculation_method_labour == 'percentage':
                if self1.perc_labour:
                    for cline in self1.job_labour_line_ids:
                        cline.margin = (cline.hours * cline.cost_price) * (cline.direct_id.perc_labour / 100)

            if self1.calculation_method_labour == 'lumsum':
                if self1.lumsum_labour:
                    labour_total = sum([(p.hours * p.cost_price) for p in self1.job_labour_line_ids])
                    for cline in self1.job_labour_line_ids:
                        if labour_total:
                            cline.margin = (
                                    float(self1.lumsum_labour / labour_total) * (cline.hours * cline.cost_price))

            if self1.calculation_method_labour == 'linewise':
                for cline in self1.job_labour_line_ids:
                    cline.margin_total = (cline.hours * cline.cost_price) + cline.margin

            if self1.calculation_method_labour == 'line_by_per':
                for lab in self1.job_labour_line_ids:
                    lab.margin_total = (lab.margin / 100 * lab.total_cost) + lab.total_cost

            if self1.calculation_method_overhead == 'percentage':
                if self1.perc_overhead:
                    for cline in self1.job_overhead_line_ids:
                        cline.margin = (cline.product_qty * cline.cost_price) * (cline.direct_id.perc_overhead / 100)

            if self1.calculation_method_overhead == 'lumsum':
                if self1.lumsum_overhead:
                    labour_total = sum([(p.product_qty * p.cost_price) for p in self1.job_overhead_line_ids])
                    for cline in self1.job_overhead_line_ids:
                        if labour_total:
                            cline.margin = (float(self1.lumsum_overhead / labour_total) * (
                                    cline.product_qty * cline.cost_price))

            if self1.calculation_method_overhead == 'linewise':
                for cline in self1.job_overhead_line_ids:
                    cline.margin_total = (cline.product_qty * cline.cost_price) + cline.margin

            if self1.calculation_method_overhead == 'line_by_per':
                for lab in self1.job_overhead_line_ids:
                    lab.margin_total = (lab.margin / 100 * lab.total_cost) + lab.total_cost

            return res

    def action_view_sale_order(self):
        ctx = dict(self.env.context)
        if ctx:
            ctx.update(default_job_cost_id=self.id)
            ctx.update(search_default_job_cost_id=self.id)
        self.ensure_one()
        sale_order_obj = self.env['sale.order']
        cost_ids = sale_order_obj.search([('job_cost_id', '=', self.id)]).ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Sale Order',
            'res_model': 'sale.order',
            'res_id': self.id,
            'domain': "[('id','in',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'context': ctx,
            'target': self.id,
        }
        return action

    def action_view_crm(self):
        ctx = dict(self.env.context)
        self.ensure_one()
        crm_obj = self.env['crm.lead']
        cost_ids = crm_obj.search([('id', '=', self.lead_id.id)]).ids
        view_id = self.env.ref('crm.crm_lead_view_form').id
        if not cost_ids:
            return {
                'type': 'ir.actions.act_window_close'
            }
        action = {
            'type': 'ir.actions.act_window',
            'name': 'CRM',
            'res_model': 'crm.lead',
            'views': [(view_id, 'form')],
            'res_id': cost_ids[0],
            'domain': "[('id','=',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'target': self.id,
        }
        return action

    def action_view_purchase(self):
        ctx = dict(self.env.context)
        if ctx:
            ctx.update(default_job_cost_id=self.id)
            ctx.update(search_default_job_cost_id=self.id)
        self.ensure_one()
        purchase_obj = self.env['purchase.order']
        cost_ids = purchase_obj.search([('job_cost_id', '=', self.id)]).ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'res_id': self.id,
            'domain': "[('id','in',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'context': ctx,
            'target': self.id,
        }
        return action

    def action_rfq_new(self):

        ctx = dict(self.env.context)
        if ctx:
            ctx.update(default_job_cost_id=self.id)
            ctx.update(search_default_job_cost_id=self.id)
        self.ensure_one()
        purchase_obj = self.env['purchase.order']
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('purchase.purchase_order_form').id,
            'context': ctx,
            'target': self.id,
        }

        return action

    @api.depends(
        'job_cost_line_ids',
        'job_cost_line_ids.product_qty',
        'job_cost_line_ids.cost_price',
    )
    def _compute_material_total(self):
        for rec in self:
            rec.material_total = sum([(p.product_qty * p.cost_price) for p in rec.job_cost_line_ids])

    @api.depends(
        'job_labour_line_ids',
        'job_labour_line_ids.hours',
        'job_labour_line_ids.cost_price'
    )
    def _compute_labor_total(self):
        for rec in self:
            rec.labor_total = sum([(p.hours * p.cost_price) for p in rec.job_labour_line_ids])

    @api.depends(
        'job_overhead_line_ids',
        'job_overhead_line_ids.product_qty',
        'job_overhead_line_ids.cost_price'
    )
    def _compute_overhead_total(self):
        for rec in self:
            rec.overhead_total = sum([(p.product_qty * p.cost_price) for p in rec.job_overhead_line_ids])

    @api.depends(
        'job_cost_line_ids',
        'job_cost_line_ids.product_qty',
        'job_cost_line_ids.cost_price',
    )
    def _compute_jobcost_total_material(self):
        for rec in self:
            rec.jobcost_total_material = sum([(p.margin_total) for p in rec.job_cost_line_ids])

    @api.depends(
        'job_labour_line_ids',
        'job_labour_line_ids.hours',
        'job_labour_line_ids.cost_price'
    )
    def _compute_jobcost_total_labour(self):
        for rec in self:
            rec.jobcost_total_labour = sum([(p.margin_total) for p in rec.job_labour_line_ids])

    @api.depends(
        'job_overhead_line_ids',
        'job_overhead_line_ids.product_qty',
        'job_overhead_line_ids.cost_price'
    )
    def _compute_jobcost_total_overhead(self):
        for rec in self:
            rec.jobcost_total_overhead = sum([(p.margin_total) for p in rec.job_overhead_line_ids])

    @api.depends(
        'material_total',
        'labor_total',
        'overhead_total'
    )
    def _compute_jobcost_total(self):
        for rec in self:
            rec.jobcost_total = rec.material_total + rec.labor_total + rec.overhead_total

    @api.depends(
        'jobcost_total_material',
        'jobcost_total_labour',
        'jobcost_total_overhead'
    )
    def _compute_total(self):
        for rec in self:
            rec.total = rec.jobcost_total_material + rec.jobcost_total_labour + rec.jobcost_total_overhead

    @api.depends(
        'jobcost_total_material',
        'jobcost_total_labour',
        'jobcost_total_overhead',
        'material_total',
        'labor_total',
        'overhead_total'
    )
    def _compute_tot(self):
        for rec in self:
            rec.total_m = self.jobcost_total_material - self.material_total
            rec.total_l = self.jobcost_total_labour - self.labor_total
            rec.total_o = self.jobcost_total_overhead - self.overhead_total
            rec.mtotal = self.total - self.jobcost_total

    #     @api.multi
    #     def _purchase_order_line_count(self):
    #         purchase_order_lines_obj = self.env['purchase.order.line']
    #         for order_line in self:
    #             order_line.purchase_order_line_count = purchase_order_lines_obj.search_count([('job_cost_id','=',order_line.id)])
    #
    #     @api.multi
    #     def _timesheet_line_count(self):
    #         hr_timesheet_obj = self.env['account.analytic.line']
    #         for timesheet_line in self:
    #             timesheet_line.timesheet_line_count = hr_timesheet_obj.search_count([('job_cost_id', '=', timesheet_line.id)])
    #
    #     @api.multi
    #     def _account_invoice_line_count(self):
    #         account_invoice_lines_obj = self.env['account.invoice.line']
    #         for invoice_line in self:
    #             invoice_line.account_invoice_line_count = account_invoice_lines_obj.search_count([('job_cost_id', '=', invoice_line.id)])

    @api.constrains('perc_material', 'perc_labour', 'perc_overhead')
    def _check_field(self):
        if self.perc_material:
            if self.perc_material < 0.00 or self.perc_material > 100.00:
                raise ValidationError(_('The amount of Percentage in material is not correct.'))
        if self.perc_labour:
            if self.perc_labour < 0.00 or self.perc_labour > 100.00:
                raise ValidationError(_('The amount of Percentage in labour is not correct.'))
        if self.perc_overhead:
            if self.perc_overhead < 0.00 or self.perc_overhead > 100.00:
                raise ValidationError(_('The amount of  Percentage in overhead is not correct.'))
        return True

    #     @api.onchange('project_id')
    #     def _onchange_project_id(self):
    #         for rec in self:
    #             rec.analytic_id = rec.project_id.analytic_account_id.id
    #
    number = fields.Char(
        readonly=True,
        default='New',
        copy=False,
    )
    name = fields.Char(
        required=True,
        copy=True,
        default='New',
        string='Name',
    )
    notes_job = fields.Text(
        required=False,
        copy=True,
        string='Job Cost Details'
    )
    user_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        string='Created By',
        readonly=True
    )
    lead_id = fields.Many2one(
        'crm.lead',
        string='CRM',
        readonly=True
    )

    description = fields.Char(
        string='Description',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.user.company_id.currency_id,
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.user.company_id,
        string='Company',
        readonly=True
    )
    #     project_id = fields.Many2one(
    #         'project.project',
    #         string='Project',
    #     )
    analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account')

    contract_date = fields.Date(
        string='Contract Date',
    )
    start_date = fields.Date(
        string='Create Date',
        readonly=True,
        default=fields.Date.today(),
    )
    complete_date = fields.Date(
        string='Closed Date',
        readonly=True,
    )
    material_total = fields.Float(
        string='Total Material Cost',
        compute='_compute_material_total',
        store=True
    )
    labor_total = fields.Float(
        string='Total Resources Cost',
        compute='_compute_labor_total',
    )
    overhead_total = fields.Float(
        string='Total Overhead Cost',
        compute='_compute_overhead_total',
    )
    jobcost_total = fields.Float(
        store=True,
        string='Total Cost',
        compute='_compute_jobcost_total',
    )
    total = fields.Float(
        string='Total',
        compute='_compute_total',
    )

    jobcost_total_material = fields.Float(
        string='Total Cost',
        compute='_compute_jobcost_total_material',
    )
    jobcost_total_overhead = fields.Float(
        string='Total Cost',
        compute='_compute_jobcost_total_overhead',
    )
    jobcost_total_labour = fields.Float(
        string='Total Cost',
        compute='_compute_jobcost_total_labour',
    )
    job_cost_line_ids = fields.One2many(
        'job.cost.line',
        'direct_id',
        string='Direct Materials',
        domain=[('job_type', '=', 'material')],
    )
    job_labour_line_ids = fields.One2many(
        'job.labour.line',
        'direct_id',
        string='Direct Materials',
        domain=[('job_type', '=', 'labour')],
    )
    job_overhead_line_ids = fields.One2many(
        'job.overhead.line',
        'direct_id',
        string='Direct Materials',
        domain=[('job_type', '=', 'overhead')],
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        domain=[('customer_rank', '>', 0)],
    )
    #     task_id = fields.Many2one(
    #         'project.task',
    #         string='Job Order',
    #     )
    so_number = fields.Char(
        string='Sale Reference'
    )
    calculation_method_material = fields.Selection(
        selection=[('percentage', 'Total percentage margin'),
                   ('lumsum', 'Total lumsum margin'),
                   ('linewise', 'Linewise margin'),
                   ('line_by_per', 'Line by percenage margin')
                   ], default='percentage',
        copy=True,
        string="Margin calculation method",
    )
    calculation_method_overhead = fields.Selection(
        selection=[('percentage', 'Total percentage margin'),
                   ('lumsum', 'Total lumsum margin'),
                   ('linewise', 'Linewise margin'),
                   ('line_by_per', 'Line by percenage margin')
                   ], default='percentage',
        copy=True,
        string="Margin calculation method",
    )
    calculation_method_labour = fields.Selection(
        selection=[('percentage', 'Total percentage margin'),
                   ('lumsum', 'Total lumsum margin'),
                   ('linewise', 'Linewise margin'),
                   ('line_by_per', 'Line by percenage margin')
                   ], default='percentage',
        copy=True,
        string="Margin calculation method",
    )
    perc_material = fields.Float(
        string='Percent'
    )
    perc_overhead = fields.Float(
        string='Percent'
    )
    perc_labour = fields.Float(
        string='Percent'
    )
    lumsum_material = fields.Float(
        string='Lumsum Amount'
    )
    lumsum_overhead = fields.Float(
        string='Lumsum Amount'
    )
    lumsum_labour = fields.Float(
        string='Lumsum Amount'
    )
    total_m = fields.Float(
        string='Total Cost',
        compute='_compute_tot',
    )
    total_o = fields.Float(
        string='Total Cost',
        compute='_compute_tot',
    )
    total_l = fields.Float(
        string='Total Cost',
        compute='_compute_tot',
    )
    mtotal = fields.Float(
        string='Total Cost',
        compute='_compute_tot',
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit_r1', 'Submitted to R1 Approval'),
        ('submit_r2', 'Submitted to R2 Approval'),
        ('approve', 'Approve Estimation'),
        ('cancel', 'Cancel'),

    ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False, )

    _constraints = [
        (_check_field, 'Please give proper percentage value.', ['perc_material', 'perc_labour', 'perc_overhead'])
    ]

    #    issue_id = fields.Many2one(
    #        'project.issue',
    #        string='Job Issue',
    #    ) #odoo11

    #     purchase_order_line_count = fields.Integer(
    #         compute='_purchase_order_line_count'
    #     )
    #
    #     purchase_order_line_ids = fields.One2many(
    #         "purchase.order.line",
    #         'job_cost_id',
    #     )
    #
    #     timesheet_line_count = fields.Integer(
    #         compute='_timesheet_line_count'
    #     )
    #
    #     timesheet_line_ids = fields.One2many(
    #         'account.analytic.line',
    #         'job_cost_id',
    #     )
    #
    #     account_invoice_line_count = fields.Integer(
    #         compute='_account_invoice_line_count'
    #     )
    #
    #     account_invoice_line_ids = fields.One2many(
    #         "account.invoice.line",
    #         'job_cost_id',
    #     )
    #
    def action_done(self):
        #         lines={}
        lst = []
        for rec in self:
            sale = self.env['sale.order'].create({'state': 'draft',
                                                  'partner_id': rec.partner_id.id,
                                                  'job_cost_id': rec.id,
                                                  'analytic_account_id': rec.analytic_id.id
                                                  })
            for mline in rec.job_cost_line_ids:
                lines = {}
                if mline.product_qty:
                    price = mline.margin_total / mline.product_qty
                else:
                    price = 0.00
                mline.product_id.write({'lst_price': price})
                lines = {
                    'product_id': mline.product_id.id,
                    'name': mline.description,
                    'product_uom_qty': mline.product_qty,
                    'price_unit': price,
                    'order_id': sale.id
                }
                self.env['sale.order.line'].create(lines)
            for lline in rec.job_labour_line_ids:
                lines = {}
                if lline.hours:
                    price = lline.margin_total / lline.hours
                else:
                    price = 0.00
                lline.product_id.write({'lst_price': price})
                lines = {
                    'product_id': lline.product_id.id,
                    'name': lline.description,
                    'product_uom_qty': lline.hours,
                    'price_unit': price,
                    'order_id': sale.id
                }
                sol = self.env['sale.order.line'].create(lines)
            for oline in rec.job_overhead_line_ids:
                lines = {}
                if oline.product_qty:
                    price = oline.margin_total / oline.product_qty
                else:
                    price = 0.00
                oline.product_id.write({'lst_price': price})
                lines = {
                    'product_id': oline.product_id.id,
                    'name': oline.description,
                    'product_uom_qty': oline.product_qty,
                    'price_unit': price,
                    'order_id': sale.id
                }
                self.env['sale.order.line'].create(lines)

            vendor = self.env['res.partner'].search([('name', '=', 'PO Draft')])
            purchase = self.env['purchase.order'].create({'state': 'draft',
                                                          'partner_id': vendor.id,
                                                          'job_cost_id': rec.id,
                                                          })
            for mline in rec.job_cost_line_ids:
                lines = {}
                if mline.product_qty:
                    price = mline.product_id.standard_price
                else:
                    price = 0.00
                lines = {
                    'product_id': mline.product_id.id,
                    'name': mline.description,
                    'product_qty': mline.product_qty,
                    'order_id': purchase.id,
                    'date_planned': datetime.now(),
                    'product_uom': mline.uom_id.id,
                    'price_unit': price,
                    'account_analytic_id': rec.analytic_id.id
                }
                pline = self.env['purchase.order.line'].create(lines)
                pline.write({'price_unit': price})
            for lline in rec.job_labour_line_ids:
                lines = {}
                if lline.hours:
                    price = lline.product_id.standard_price
                else:
                    price = 0.00
                lines = {
                    'product_id': lline.product_id.id,
                    'name': lline.description,
                    'product_qty': lline.hours,
                    'price_unit': 1.00,
                    'order_id': purchase.id,
                    'date_planned': datetime.now(),
                    'product_uom': 1,
                    'account_analytic_id': rec.analytic_id.id
                }
                pline = self.env['purchase.order.line'].create(lines)
                pline.write({'price_unit': price})
            for oline in rec.job_overhead_line_ids:
                lines = {}
                if oline.product_qty:
                    price = oline.product_id.standard_price
                else:
                    price = 0.00
                lines = {
                    'product_id': oline.product_id.id,
                    'name': oline.description,
                    'product_qty': oline.product_qty,
                    'price_unit': price,
                    'order_id': purchase.id,
                    'date_planned': datetime.now(),
                    'product_uom': oline.uom_id.id,
                    'account_analytic_id': rec.analytic_id.id
                }
                pline = self.env['purchase.order.line'].create(lines)
                pline.write({'price_unit': price})
            #             print(k)

            rec.write({
                'state': 'approve',
                'complete_date': date.today(),
            })

    def action_confirm(self):
        for rec in self:
            rec.write({
                'state': 'submit_r2',
            })

    def action_submit(self):
        for rec in self:
            rec.write({
                'state': 'submit_r1',
            })

    def action_cancel(self):
        for rec in self:
            rec.write({
                'state': 'cancel',
            })

    def action_draft(self):
        for rec in self:
            rec.write({
                'state': 'draft',
            })

    def create_rfq(self):
        for rec in self:
            for i in range(1, 6):
                vendor = self.env['res.partner'].search([('name', '=', 'PO Draft')])
                purchase = self.env['purchase.order'].create({'state': 'draft',
                                                              'partner_id': vendor.id,
                                                              'job_cost_id': rec.id,
                                                              })
                for mline in rec.job_cost_line_ids:
                    lines = {}
                    if mline.product_qty:
                        price = mline.product_id.standard_price
                    else:
                        price = 0.00
                    lines = {
                        'product_id': mline.product_id.id,
                        'name': mline.description,
                        'product_qty': mline.product_qty,
                        'order_id': purchase.id,
                        'date_planned': datetime.now(),
                        'product_uom': mline.uom_id.id,
                        'price_unit': price,
                        'account_analytic_id': rec.analytic_id.id
                    }
                    pline = self.env['purchase.order.line'].create(lines)
                    pline.write({'price_unit': price})
                for lline in rec.job_labour_line_ids:
                    lines = {}
                    if lline.hours:
                        price = lline.product_id.standard_price
                    else:
                        price = 0.00
                    lines = {
                        'product_id': lline.product_id.id,
                        'name': lline.description,
                        'product_qty': lline.hours,
                        'price_unit': 1.00,
                        'order_id': purchase.id,
                        'date_planned': datetime.now(),
                        'product_uom': 1,
                        'account_analytic_id': rec.analytic_id.id
                    }
                    pline = self.env['purchase.order.line'].create(lines)
                    pline.write({'price_unit': price})
                for oline in rec.job_overhead_line_ids:
                    lines = {}
                    if oline.product_qty:
                        price = oline.product_id.standard_price
                    else:
                        price = 0.00
                    lines = {
                        'product_id': oline.product_id.id,
                        'name': oline.description,
                        'product_qty': oline.product_qty,
                        'price_unit': price,
                        'order_id': purchase.id,
                        'date_planned': datetime.now(),
                        'product_uom': oline.uom_id.id,
                        'account_analytic_id': rec.analytic_id.id
                    }
                    pline = self.env['purchase.order.line'].create(lines)
                    pline.write({'price_unit': price})
        cost_ids = self.env['purchase.order'].search([('job_cost_id', '=', self.id)]).ids
        action = {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'res_id': self.id,
            'domain': "[('id','in',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'target': self.id,
        }
        return action


#     @api.multi
#     def action_approve(self):
#         for rec in self:
#             rec.write({
#                 'state' : 'approve',
#             })
#     
#     @api.multi
#     def action_done(self):
#         for rec in self:
#             rec.write({
#                 'state' : 'done',
#                 'complete_date':date.today(),
#             })
#         
#     @api.multi
#     def action_cancel(self):
#         for rec in self:
#             rec.write({
#                 'state' : 'cancel',
#             })
#     @api.multi
#     def action_view_purchase_order_line(self):
#         self.ensure_one()
#         purchase_order_lines_obj = self.env['purchase.order.line']
#         cost_ids = purchase_order_lines_obj.search([('job_cost_id','=',self.id)]).ids
#         action = {
#             'type': 'ir.actions.act_window',
#             'name': 'Purchase Order Line',
#             'res_model': 'purchase.order.line',
#             'res_id': self.id,
#             'domain': "[('id','in',[" + ','.join(map(str, cost_ids)) + "])]",
#             'view_type': 'form',
#             'view_mode': 'tree,form',
#             'target' : self.id,
#         }
class JobCostLine(models.Model):
    _name = 'job.cost.line'
    _rec_name = 'description'

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            rec.description = rec.product_id.name
            rec.product_qty = 1.0
            rec.uom_id = rec.product_id.uom_id.id
            rec.cost_price = rec.product_id.standard_price  # lst_price

    @api.depends('product_qty', 'hours', 'cost_price', 'direct_id')
    def _compute_total_cost(self):
        for rec in self:
            rec.hours = 0.0
            rec.total_cost = rec.product_qty * rec.cost_price

    @api.depends('margin', 'total_cost')
    def _compute_margin_total(self):
        for rec in self:
            if rec.direct_id.calculation_method_material == 'line_by_per':
                rec.margin_total = (rec.margin / 100 * rec.total_cost) + rec.total_cost
            else:
                rec.margin_total = rec.margin + rec.total_cost

    #     @api.multi
    #     @a    pi.depends('product_qty','cost_price')
    #     def _compute_margin(self):
    #         for rec in self:
    #             print ("!!!!!!11111",rec.direct_id.calculation_method_material)
    #             if rec.direct_id.calculation_method_material =='percentage':
    #                 print ("0000000000000000000000000000")
    #                 if rec.direct_id.perc_material:
    #                     print ("kkkkkkkkkkkkkkkkkkk",rec.direct_id.perc_material)
    #                     rec.margin=(rec.product_qty * rec.cost_price)*(rec.direct_id.perc_material/100)
    #                     print("**************************",(rec.product_qty * rec.cost_price)*(rec.direct_id.perc_material/100))
    #             if  rec.direct_id.calculation_method_material =='lumsum':
    #                 print ("0000000000000000000000000000")
    #                 if rec.direct_id.lumsum_material:
    #                     if rec.direct_id.jobcost_total:
    #                         print ("!!!!!!!!!!!!!!!!!!!!------------->>>>>>>>>",rec.direct_id.job_cost_line_ids)
    #                         for line in rec.direct_id.job_cost_line_ids:
    #                             line.margin=((line.product_qty * line.cost_price)/(rec.direct_id.jobcost_total+(line.product_qty * line.cost_price)))*rec.direct_id.lumsum_material
    #                     else:
    #                         rec.margin=rec.direct_id.lumsum_material
    #                         print ("kkkkkkkkkkkkkkkkkkk",rec.direct_id.lumsum_material)
    #             print (k)

    sl_num = fields.Char(
        string='Sl Number',
        copy=False,
    )
    direct_id = fields.Many2one(
        'job.costing',
        string='Job Costing'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        copy=False,
        required=True,
    )
    description = fields.Char(
        string='Description',
        copy=False,
    )
    reference = fields.Char(
        string='Reference',
        copy=False,
    )
    product_qty = fields.Float(
        string='Planned Qty',
        copy=False,
    )
    uom_id = fields.Many2one(
        'uom.uom',  # product.uom
        string='Uom',
    )
    cost_price = fields.Float(
        string='Cost / Unit',
        copy=False,
    )
    total_cost = fields.Float(
        string='Cost Price Sub Total',
        compute='_compute_total_cost',
        store=True,
    )
    analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.user.company_id.currency_id,
        readonly=True
    )
    #     job_type_id = fields.Many2one(
    #         'job.type',
    #         string='Job Type',
    #     )
    job_type = fields.Selection(
        selection=[('material', 'Material'),
                   ('labour', 'Labour'),
                   ('overhead', 'Overhead')
                   ],
        string="Type",
        required=True,
    )
    basis = fields.Char(
        string='Basis'
    )
    hours = fields.Float(
        string='Hours'
    )
    margin = fields.Float(
        string='Margin',

    )
    margin_total = fields.Float(
        string='Total with Margin',
        compute='_compute_margin_total',
        store=True,
    )


class JobOverheadLine(models.Model):
    _name = 'job.overhead.line'
    _rec_name = 'description'

    @api.depends('margin', 'total_cost')
    def _compute_margin_total(self):
        for rec in self:
            if rec.direct_id.calculation_method_overhead == 'line_by_per':
                rec.margin_total = (rec.margin / 100 * rec.total_cost) + rec.total_cost
            else:
                rec.margin_total = rec.margin + rec.total_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            rec.description = rec.product_id.name
            rec.product_qty = 1.0
            rec.uom_id = rec.product_id.uom_id.id
            rec.cost_price = rec.product_id.standard_price  # lst_price

    @api.depends('product_qty', 'hours', 'cost_price', 'direct_id')
    def _compute_total_cost(self):
        for rec in self:
            if rec.job_type == 'labour':
                rec.product_qty = 0.0
                rec.total_cost = rec.hours * rec.cost_price
            else:
                rec.hours = 0.0
                rec.total_cost = rec.product_qty * rec.cost_price

    #     #@api.depends('purchase_order_line_ids', 'purchase_order_line_ids.product_qty')
    #     @api.depends('purchase_order_line_ids', 'purchase_order_line_ids.product_qty', 'purchase_order_line_ids.order_id.state')
    #     def _compute_actual_quantity(self):
    #         for rec in self:
    #             #rec.actual_quantity = sum([p.product_qty for p in rec.purchase_order_line_ids])
    #             rec.actual_quantity = sum([p.order_id.state in ['purchase', 'done'] and p.product_qty for p in rec.purchase_order_line_ids])
    #
    #     @api.depends('timesheet_line_ids','timesheet_line_ids.unit_amount')
    #     def _compute_actual_hour(self):
    #         for rec in self:
    #             rec.actual_hour = sum([p.unit_amount for p in rec.timesheet_line_ids])
    #
    #     #@api.depends('account_invoice_line_ids','account_invoice_line_ids.quantity')
    #     @api.depends('account_invoice_line_ids','account_invoice_line_ids.quantity', 'account_invoice_line_ids.invoice_id.state')
    #     def _compute_actual_invoice_quantity(self):
    #         for rec in self:
    #             #rec.actual_invoice_quantity = sum([p.quantity for p in rec.account_invoice_line_ids])
    #             rec.actual_invoice_quantity = sum([p.invoice_id.state in ['open', 'paid'] and p.quantity or 0.0 for p in rec.account_invoice_line_ids])

    sl_num = fields.Char(
        string='Sl Number',
        copy=False,
    )
    direct_id = fields.Many2one(
        'job.costing',
        string='Job Costing'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        copy=False,
        required=True,
    )
    description = fields.Char(
        string='Description',
        copy=False,
    )
    reference = fields.Char(
        string='Reference',
        copy=False,
    )
    product_qty = fields.Float(
        string='Planned Qty',
        copy=False,
    )
    uom_id = fields.Many2one(
        'uom.uom',  # product.uom
        string='Uom',
    )
    cost_price = fields.Float(
        string='Cost / Unit',
        copy=False,
    )
    total_cost = fields.Float(
        string='Cost Price Sub Total',
        compute='_compute_total_cost',
        store=True,
    )
    analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.user.company_id.currency_id,
        readonly=True
    )

    job_type = fields.Selection(
        selection=[('material', 'Material'),
                   ('labour', 'Labour'),
                   ('overhead', 'Overhead')
                   ],
        string="Type",
        required=True,
    )
    basis = fields.Char(
        string='Basis'
    )
    hours = fields.Float(
        string='Hours'
    )
    margin = fields.Float(
        string='Margin'
    )
    margin_total = fields.Float(
        string='Total with Margin',
        compute='_compute_margin_total',
        store=True,
    )


class JoblabourLine(models.Model):
    _name = 'job.labour.line'
    _rec_name = 'description'

    @api.depends('margin', 'total_cost')
    def _compute_margin_total(self):
        for rec in self:
            if rec.direct_id.calculation_method_labour == 'line_by_per':
                rec.margin_total = (rec.margin / 100 * rec.total_cost) + rec.total_cost
            else:
                rec.margin_total = rec.margin + rec.total_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            rec.description = rec.product_id.name
            rec.product_qty = 1.0
            rec.uom_id = rec.product_id.uom_id.id
            rec.cost_price = rec.product_id.standard_price  # lst_price

    @api.depends('product_qty', 'hours', 'cost_price', 'direct_id')
    def _compute_total_cost(self):
        for rec in self:
            if rec.job_type == 'labour':
                rec.product_qty = 0.0
                rec.total_cost = rec.hours * rec.cost_price
            else:
                rec.hours = 0.0
                rec.total_cost = rec.product_qty * rec.cost_price

    #     #@api.depends('purchase_order_line_ids', 'purchase_order_line_ids.product_qty')
    #     @api.depends('purchase_order_line_ids', 'purchase_order_line_ids.product_qty', 'purchase_order_line_ids.order_id.state')
    #     def _compute_actual_quantity(self):
    #         for rec in self:
    #             #rec.actual_quantity = sum([p.product_qty for p in rec.purchase_order_line_ids])
    #             rec.actual_quantity = sum([p.order_id.state in ['purchase', 'done'] and p.product_qty for p in rec.purchase_order_line_ids])
    #
    #     @api.depends('timesheet_line_ids','timesheet_line_ids.unit_amount')
    #     def _compute_actual_hour(self):
    #         for rec in self:
    #             rec.actual_hour = sum([p.unit_amount for p in rec.timesheet_line_ids])
    #
    #     #@api.depends('account_invoice_line_ids','account_invoice_line_ids.quantity')
    #     @api.depends('account_invoice_line_ids','account_invoice_line_ids.quantity', 'account_invoice_line_ids.invoice_id.state')
    #     def _compute_actual_invoice_quantity(self):
    #         for rec in self:
    #             #rec.actual_invoice_quantity = sum([p.quantity for p in rec.account_invoice_line_ids])
    #             rec.actual_invoice_quantity = sum([p.invoice_id.state in ['open', 'paid'] and p.quantity or 0.0 for p in rec.account_invoice_line_ids])

    sl_num = fields.Char(
        string='Sl Number',
        copy=False,
    )
    direct_id = fields.Many2one(
        'job.costing',
        string='Job Costing'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        copy=False,
        required=True,
    )
    description = fields.Char(
        string='Description',
        copy=False,
    )
    reference = fields.Char(
        string='Reference',
        copy=False,
    )
    product_qty = fields.Float(
        string='Planned Qty',
        copy=False,
    )
    uom_id = fields.Many2one(
        'uom.uom',  # product.uom
        string='Uom',
    )
    cost_price = fields.Float(
        string='Cost / Unit',
        copy=False,
    )
    total_cost = fields.Float(
        string='Cost Price Sub Total',
        compute='_compute_total_cost',
        store=True,
    )
    analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.user.company_id.currency_id,
        readonly=True
    )
    #     job_type_id = fields.Many2one(
    #         'job.type',
    #         string='Job Type',
    #     )
    job_type = fields.Selection(
        selection=[('material', 'Material'),
                   ('labour', 'Labour'),
                   ('overhead', 'Overhead')
                   ],
        string="Type",
        required=True,
    )
    basis = fields.Char(
        string='Basis'
    )
    hours = fields.Float(
        string='Hours'
    )
    margin = fields.Float(
        string='Margin'
    )
    margin_total = fields.Float(
        string='Total with Margin',
        compute='_compute_margin_total',
        store=True,
    )


class Lead(models.Model):
    _inherit = "crm.lead"

    ref = fields.Char(
        string='Client Reference'
    )
    submit_date = fields.Date(
        string='Expected Submission Date',
    )
    lead_source = fields.Many2one(
        'lead.source',
        string='Lead Source',
    )
    lead_details = fields.Char(
        string='Lead Details'
    )

    def action_view_estimations(self):
        print("111111111111111111111")
        self.ensure_one()
        crm_obj = self.env['job.costing']
        print("22222222222222", crm_obj)
        cost_ids = crm_obj.search([('lead_id', '=', self.id)]).ids
        print("22222222222222", cost_ids)

        action = {
            'type': 'ir.actions.act_window',
            'name': 'CRM',
            'res_model': 'job.costing',
            'res_id': self.id,
            'domain': "[('id','=',[" + ','.join(map(str, cost_ids)) + "])]",
            'view_type': 'form',
            'view_mode': 'tree,form',
            'target': self.id,
        }
        return action


class LeadSource(models.Model):
    _name = "lead.source"

    name = fields.Char(string="Name")
