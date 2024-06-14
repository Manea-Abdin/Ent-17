# -*- coding: utf-8 -*-
from .common import TestMxEdiCommon
from odoo import Command
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import tagged
from odoo.tools import misc
from odoo.tools.misc import file_open

from freezegun import freeze_time


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestCFDIInvoice(TestMxEdiCommon):

    @freeze_time('2017-01-01')
    def test_invoice_foreign_currency(self):
        invoice = self._create_invoice(currency_id=self.foreign_curr_1.id)

        # Change the currency to prove that the rate is computed based on the invoice
        self.currency_data['rates'].rate = 10

        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_foreign_currency')

    @freeze_time('2017-01-01')
    def test_invoice_misc_business_values(self):
        for move_type, output_file in (
            ('out_invoice', 'test_invoice_misc_business_values'),
            ('out_refund', 'test_credit_note_misc_business_values')
        ):
            with self.subTest(move_type=move_type):
                invoice = self._create_invoice(
                    invoice_incoterm_id=self.env.ref('account.incoterm_FCA').id,
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 2000.0,
                            'quantity': 5,
                            'discount': 20.0,
                        }),
                        # Ignored lines by the CFDI:
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 2000.0,
                            'quantity': 0.0,
                        }),
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 0.0,
                            'quantity': 10.0,
                        }),
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, output_file)

    @freeze_time('2017-01-01')
    def test_invoice_foreign_customer(self):
        invoice = self._create_invoice(partner_id=self.partner_us.id)
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_foreign_customer')

    @freeze_time('2017-01-01')
    def test_invoice_customer_with_no_country(self):
        self.partner_us.country_id = None
        invoice = self._create_invoice(partner_id=self.partner_us.id)
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_customer_with_no_country')

    @freeze_time('2017-01-01')
    def test_invoice_national_customer_to_public(self):
        invoice = self._create_invoice(l10n_mx_edi_cfdi_to_public=True)
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_national_customer_to_public')

    @freeze_time('2017-01-01')
    def test_invoice_taxes(self):
        def create_invoice(taxes_list, l10n_mx_edi_cfdi_to_public=False):
            invoice_line_ids = []
            for i, taxes in enumerate(taxes_list, start=1):
                invoice_line_ids.append(Command.create({
                    'product_id': self.product.id,
                    'price_unit': 1000.0 * i,
                    'quantity': 5,
                    'discount': 20.0,
                    'tax_ids': [Command.set(taxes.ids)],
                }))
                # Full discounted line:
                invoice_line_ids.append(Command.create({
                    'product_id': self.product.id,
                    'price_unit': 1000.0 * i,
                    'discount': 100.0,
                    'tax_ids': [Command.set(taxes.ids)],
                }))
            return self._create_invoice(
                invoice_line_ids=invoice_line_ids,
                l10n_mx_edi_cfdi_to_public=l10n_mx_edi_cfdi_to_public,
            )

        for index, taxes_list in enumerate(self.existing_taxes_combinations_to_test, start=1):
            # Test the invoice CFDI.
            self.partner_mx.l10n_mx_edi_no_tax_breakdown = False
            invoice = create_invoice(taxes_list)
            with self.with_mocked_pac_sign_success():
                invoice._l10n_mx_edi_cfdi_invoice_try_send()
            self._assert_invoice_cfdi(invoice, f'test_invoice_taxes_{index}_invoice')

            # Test the payment CFDI.
            payment = self._create_payment(invoice)
            with self.with_mocked_pac_sign_success():
                payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
            self._assert_invoice_payment_cfdi(payment.move_id, f'test_invoice_taxes_{index}_payment')

            # Test the global invoice CFDI.
            invoice = create_invoice(taxes_list, l10n_mx_edi_cfdi_to_public=True)
            with self.with_mocked_pac_sign_success():
                invoice._l10n_mx_edi_cfdi_global_invoice_try_send()
            self._assert_global_invoice_cfdi_from_invoices(invoice, f'test_invoice_taxes_{index}_ginvoice')

            # Test the invoice with no tax breakdown.
            self.partner_mx.l10n_mx_edi_no_tax_breakdown = True
            invoice = create_invoice(taxes_list)
            with self.with_mocked_pac_sign_success():
                invoice._l10n_mx_edi_cfdi_invoice_try_send()
            self._assert_invoice_cfdi(invoice, f'test_invoice_taxes_{index}_invoice_no_tax_breakdown')

    @freeze_time('2017-01-01')
    def test_invoice_addenda(self):
        self.partner_mx.l10n_mx_edi_addenda = self.env['ir.ui.view'].create({
            'name': 'test_invoice_cfdi_addenda',
            'type': 'qweb',
            'arch': """
                <t t-name="l10n_mx_edi.test_invoice_cfdi_addenda">
                    <test info="this is an addenda"/>
                </t>
            """
        })

        invoice = self._create_invoice()
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_addenda')

    @freeze_time('2017-01-01')
    def test_invoice_negative_lines_dispatch_same_product(self):
        """ Ensure the distribution of negative lines is done on the same product first. """
        product1 = self.product
        product2 = self._create_product()

        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': product1.id,
                    'quantity': 5.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': product2.id,
                    'quantity': -5.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': product2.id,
                    'quantity': 12.0,
                    'tax_ids': [],
                }),
            ],
        )
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_negative_lines_dispatch_same_product')

    @freeze_time('2017-01-01')
    def test_invoice_negative_lines_dispatch_same_amount(self):
        """ Ensure the distribution of negative lines is done on the same amount. """
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 12.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 3.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 6.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -3.0,
                    'tax_ids': [],
                }),
            ],
        )
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_negative_lines_dispatch_same_amount')

    @freeze_time('2017-01-01')
    def test_invoice_negative_lines_dispatch_same_taxes(self):
        """ Ensure the distribution of negative lines is done exclusively on lines having the same taxes. """
        product1 = self.product
        product2 = self._create_product()

        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': product1.id,
                    'quantity': 12.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': product1.id,
                    'quantity': 3.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': product2.id,
                    'quantity': 6.0,
                    'tax_ids': [Command.set(self.tax_16.ids)],
                }),
                Command.create({
                    'product_id': product1.id,
                    'quantity': -3.0,
                    'tax_ids': [Command.set(self.tax_16.ids)],
                }),
            ],
        )
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_negative_lines_dispatch_same_taxes')

    @freeze_time('2017-01-01')
    def test_invoice_negative_lines_dispatch_biggest_amount(self):
        """ Ensure the distribution of negative lines is done on the biggest amount. """
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 3.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 12.0,
                    'discount': 10.0, # price_subtotal: 10800
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 8.0,
                    'discount': 20.0, # price_subtotal: 6400
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -22.0,
                    'discount': 22.0, # price_subtotal: 17160
                    'tax_ids': [],
                }),
            ],
        )
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_negative_lines_dispatch_biggest_amount')

    @freeze_time('2017-01-01')
    def test_invoice_negative_lines_zero_total(self):
        """ Test an invoice completely refunded by the negative lines. """
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 12.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -12.0,
                    'tax_ids': [],
                }),
            ],
        )
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'move_id': invoice.id,
            'state': 'invoice_sent',
            'attachment_id': False,
            'cancel_button_needed': False,
        }])

    @freeze_time('2017-01-01')
    def test_invoice_negative_lines_orphan_negative_line(self):
        """ Test an invoice in which a negative line failed to be distributed. """
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 12.0,
                    'tax_ids': [Command.set(self.tax_16.ids)],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -2.0,
                    'tax_ids': [],
                }),
            ],
        )
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'move_id': invoice.id,
            'state': 'invoice_sent_failed',
        }])

    @freeze_time('2017-01-01')
    def test_global_invoice_negative_lines_zero_total(self):
        """ Test an invoice completely refunded by the negative lines. """
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 12.0,
                    'tax_ids': [],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -12.0,
                    'tax_ids': [],
                }),
            ],
        )

        with self.with_mocked_pac_sign_success():
            self.env['l10n_mx_edi.global_invoice.create'] \
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context']) \
                .create({})\
                .action_create_global_invoice()
        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'invoice_ids': invoice.ids,
            'state': 'ginvoice_sent',
            'attachment_id': False,
            'cancel_button_needed': False,
        }])

    @freeze_time('2017-01-01')
    def test_global_invoice_negative_lines_orphan_negative_line(self):
        """ Test a global invoice containing an invoice having a negative line that failed to be distributed. """
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 12.0,
                    'tax_ids': [Command.set(self.tax_16.ids)],
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -2.0,
                    'tax_ids': [],
                }),
            ],
        )

        with self.with_mocked_pac_sign_success():
            self.env['l10n_mx_edi.global_invoice.create'] \
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context']) \
                .create({})\
                .action_create_global_invoice()
        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'invoice_ids': invoice.ids,
            'state': 'ginvoice_sent_failed',
        }])

    @freeze_time('2017-01-01')
    def test_global_invoice_including_partial_refund(self):
        invoice = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 10.0,
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -2.0,
                }),
            ],
        )
        refund = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            move_type='out_refund',
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 3.0,
                }),
                Command.create({
                    'product_id': self.product.id,
                    'quantity': -1.0,
                }),
            ],
            reversed_entry_id=invoice.id,
        )

        invoices = invoice + refund
        with self.with_mocked_pac_sign_success():
            # Calling the global invoice on the invoice will include the refund automatically.
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})\
                .action_create_global_invoice()
        self._assert_global_invoice_cfdi_from_invoices(invoices, 'test_global_invoice_including_partial_refund')

        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'invoice_ids': invoices.ids,
            'state': 'ginvoice_sent',
        }])

    @freeze_time('2017-01-01')
    def test_global_invoice_including_full_refund(self):
        invoice = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 10.0,
                }),
            ],
        )
        refund = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            move_type='out_refund',
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 10.0,
                }),
            ],
            reversed_entry_id=invoice.id,
        )

        invoices = invoice + refund
        with self.with_mocked_pac_sign_success():
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(invoices.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})\
                .action_create_global_invoice()

        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'invoice_ids': invoices.ids,
            'state': 'ginvoice_sent',
            'attachment_id': False,
        }])

    @freeze_time('2017-01-01')
    def test_global_invoice_not_allowed_refund(self):
        refund = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            move_type='out_refund',
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 3.0,
                }),
            ],
        )
        with self.assertRaises(UserError):
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(refund.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})\
                .action_create_global_invoice()

    @freeze_time('2017-01-01')
    def test_global_invoice_refund_after(self):
        invoice = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 10.0,
                }),
            ],
        )

        with self.with_mocked_pac_sign_success():
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})\
                .action_create_global_invoice()

        self.assertRecordValues(invoice.l10n_mx_edi_invoice_document_ids, [{
            'invoice_ids': invoice.ids,
            'state': 'ginvoice_sent',
        }])

        refund = self._create_invoice(
            l10n_mx_edi_cfdi_to_public=True,
            move_type='out_refund',
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'quantity': 3.0,
                }),
            ],
            reversed_entry_id=invoice.id,
        )
        with self.assertRaises(UserError):
            self.env['l10n_mx_edi.global_invoice.create'] \
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context']) \
                .create({})
        with self.with_mocked_pac_sign_success():
            self.env['account.move.send']\
                .with_context(active_model=refund._name, active_ids=refund.ids)\
                .create({})\
                .action_send_and_print()
        self._assert_invoice_cfdi(refund, 'test_global_invoice_refund_after')

        self.assertRecordValues(refund.l10n_mx_edi_invoice_document_ids, [{
            'move_id': refund.id,
            'invoice_ids': refund.ids,
            'state': 'invoice_sent',
        }])

    @freeze_time('2017-01-01')
    def test_invoice_company_branch(self):
        self.env.company.write({
            'child_ids': [Command.create({
                'name': 'Branch A',
                'zip': '85120',
            })],
        })
        self.cr.precommit.run()  # load the CoA

        branch = self.env.company.child_ids
        invoice = self._create_invoice(company_id=branch.id)

        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self._assert_invoice_cfdi(invoice, 'test_invoice_company_branch')

    @freeze_time('2017-01-01')
    def test_invoice_then_refund(self):
        # Create an invoice then sign it.
        invoice = self._create_invoice(l10n_mx_edi_cfdi_to_public=True)
        with self.with_mocked_pac_sign_success():
            self.env['account.move.send']\
                .with_context(active_model=invoice._name, active_ids=invoice.ids)\
                .create({})\
                .action_send_and_print()
        self._assert_invoice_cfdi(invoice, 'test_invoice_then_refund_1')

        # You are no longer able to create a global invoice.
        with self.assertRaises(UserError):
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})

        # Create a refund.
        results = self.env['account.move.reversal']\
            .with_context(active_model='account.move', active_ids=invoice.ids)\
            .create({
                'date': '2017-01-01',
                'reason': "turlututu",
                'journal_id': invoice.journal_id.id,
            })\
            .refund_moves()
        refund = self.env['account.move'].browse(results['res_id'])
        refund.auto_post = 'no'
        refund.action_post()

        # You can't make a global invoice for it.
        with self.assertRaises(UserError):
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(refund.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})

        # Create the CFDI and sign it.
        with self.with_mocked_pac_sign_success():
            self.env['account.move.send']\
                .with_context(active_model=refund._name, active_ids=refund.ids)\
                .create({})\
                .action_send_and_print()
        self._assert_invoice_cfdi(refund, 'test_invoice_then_refund_2')
        self.assertRecordValues(refund, [{
            'l10n_mx_edi_cfdi_origin': f'01|{invoice.l10n_mx_edi_cfdi_uuid}',
        }])

    @freeze_time('2017-01-01')
    def test_global_invoice_then_refund(self):
        # Create a global invoice and sign it.
        invoice = self._create_invoice(l10n_mx_edi_cfdi_to_public=True)
        with self.with_mocked_pac_sign_success():
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(invoice.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})\
                .action_create_global_invoice()
        self._assert_global_invoice_cfdi_from_invoices(invoice, 'test_global_invoice_then_refund_1')

        # You are not able to create an invoice for it.
        wizard = self.env['account.move.send']\
            .with_context(active_model=invoice._name, active_ids=invoice.ids)\
            .create({})
        self.assertRecordValues(wizard, [{'l10n_mx_edi_enable_cfdi': False}])

        # Refund the invoice.
        results = self.env['account.move.reversal']\
            .with_context(active_model='account.move', active_ids=invoice.ids)\
            .create({
                'date': '2017-01-01',
                'reason': "turlututu",
                'journal_id': invoice.journal_id.id,
            })\
            .refund_moves()
        refund = self.env['account.move'].browse(results['res_id'])
        refund.auto_post = 'no'
        refund.action_post()

        # You can't do a global invoice for a refund
        with self.assertRaises(UserError):
            self.env['l10n_mx_edi.global_invoice.create']\
                .with_context(refund.l10n_mx_edi_action_create_global_invoice()['context'])\
                .create({})

        # Sign the refund.
        with self.with_mocked_pac_sign_success():
            self.env['account.move.send']\
                .with_context(active_model=refund._name, active_ids=refund.ids)\
                .create({})\
                .action_send_and_print()
        self._assert_invoice_cfdi(refund, 'test_global_invoice_then_refund_2')

    @freeze_time('2017-01-01')
    def test_invoice_pos(self):
        # Trigger an error when generating the CFDI
        self.product.unspsc_code_id = False
        invoice = self._create_invoice(
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'price_unit': 1000.0,
                    'tax_ids': [Command.set(self.tax_0.ids)],
                }),
            ],
        )
        template = self.env.ref(invoice._get_mail_template())
        invoice.with_context(skip_invoice_sync=True)._generate_pdf_and_send_invoice(template, force_synchronous=True, allow_fallback_pdf=True)
        self.assertFalse(invoice.invoice_pdf_report_id, "invoice_pdf_report_id shouldn't be set with the proforma PDF.")

    @freeze_time('2017-01-01')
    def test_import_invoice_cfdi(self):
        # Invoice with payment policy = PUE, otherwise 'FormaPago' (payment method) is set to '99' ('Por Definir')
        # and the initial payment method cannot be backtracked at import
        invoice = self._create_invoice(
            invoice_date_due='2017-01-01',  # PUE
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'price_unit': 500.0,
                    'tax_ids': [Command.set(self.tax_16.ids)],
                }),
            ],
        )
        # Modify the vat, otherwise there are 2 partners with the same vat
        invoice.partner_id.vat = "XIA190128J62"

        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()

        new_invoice = self._upload_document_on_journal(
            journal=self.company_data['default_journal_sale'],
            content=invoice.l10n_mx_edi_document_ids.attachment_id.raw.decode(),
            filename=invoice.l10n_mx_edi_document_ids.attachment_id.name,
        )

        # Check the newly created invoice
        expected_vals, expected_line_vals = self._export_move_vals(invoice)
        self.assertRecordValues(new_invoice, [expected_vals])
        self.assertRecordValues(new_invoice.invoice_line_ids, expected_line_vals)

        # the state of the document should be "Sent"
        self.assertEqual(new_invoice.l10n_mx_edi_invoice_document_ids.state, "invoice_sent")
        new_invoice.action_post()
        # the "Request Cancel" button should appear after posting
        self.assertTrue(new_invoice.need_cancel_request)
        # the "Update SAT" button should appear
        self.assertTrue(new_invoice.l10n_mx_edi_update_sat_needed)

    @freeze_time('2017-01-01')
    def test_import_duplicate_fiscal_folio(self):
        invoice = self._create_invoice()

        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()

        bill_content = invoice.l10n_mx_edi_document_ids.attachment_id.raw.decode()

        self._upload_document_on_journal(
            journal=self.company_data['default_journal_purchase'],
            content=bill_content,
            filename='new_bill.xml',
        ).action_post()

    @freeze_time('2017-01-01')
    def test_import_bill_cfdi(self):
        # Invoice with payment policy = PUE, otherwise 'FormaPago' (payment method) is set to '99' ('Por Definir')
        # and the initial payment method cannot be backtracked at import
        self.env.company.partner_id.company_id = self.env.company
        invoice = self._create_invoice(
            invoice_date_due='2017-01-01',  # PUE
            invoice_line_ids=[
                Command.create({
                    'product_id': self.product.id,
                    'price_unit': 500.0,
                    'tax_ids': [Command.set(self.tax_16.ids)],
                }),
            ],
        )

        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()

        new_bill = self._upload_document_on_journal(
            journal=self.company_data['default_journal_purchase'],
            content=invoice.l10n_mx_edi_document_ids.attachment_id.raw.decode(),
            filename=invoice.l10n_mx_edi_document_ids.attachment_id.name,
        )

        # Check the newly created bill
        expected_vals, expected_line_vals = self._export_move_vals(invoice)
        expected_vals.update({
            'partner_id': invoice.company_id.partner_id.id,
            'l10n_mx_edi_payment_policy': False,
        })
        self.assertRecordValues(new_bill, [expected_vals])
        expected_line_vals[0]['tax_ids'] = self.env['account.chart.template'].ref('tax14').ids
        self.assertRecordValues(new_bill.invoice_line_ids, expected_line_vals)

        # the state of the document should be "Sent"
        self.assertEqual(new_bill.l10n_mx_edi_invoice_document_ids.state, "invoice_received")
        # the "Update SAT" button should appear continuously (after posting)
        new_bill.action_post()
        self.assertTrue(new_bill.l10n_mx_edi_update_sat_needed)
        with self.with_mocked_sat_call(lambda _x: 'valid'):
            new_bill.l10n_mx_edi_cfdi_try_sat()
        self.assertTrue(new_bill.l10n_mx_edi_update_sat_needed)

    @freeze_time('2017-01-01')
    def test_invoice_cancel_in_locked_period(self):
        invoice = self._create_invoice(invoice_date_due='2017-02-01')
        with self.with_mocked_pac_sign_success():
            invoice._l10n_mx_edi_cfdi_invoice_try_send()
        self.assertRecordValues(invoice, [{'l10n_mx_edi_cfdi_state': 'sent'}])

        payment = self.env['account.payment.register']\
            .with_context(active_model='account.move', active_ids=invoice.ids)\
            .create({})\
            ._create_payments()
        with self.with_mocked_pac_sign_success():
            invoice.l10n_mx_edi_cfdi_invoice_try_update_payments()
        self.assertRecordValues(payment, [{'l10n_mx_edi_cfdi_state': 'sent'}])

        # Lock the period.
        invoice.company_id.fiscalyear_lock_date = '2017-01-01'

        # Cancel the invoice.
        with self.with_mocked_pac_cancel_success():
            self.env['l10n_mx_edi.invoice.cancel'] \
                .with_context(invoice.button_request_cancel()['context']) \
                .create({'cancellation_reason': '03'}) \
                .action_cancel_invoice()
        self.assertRecordValues(invoice, [{'l10n_mx_edi_cfdi_state': 'cancel'}])

        # Cancel the payment.
        with self.with_mocked_pac_cancel_success():
            payment.l10n_mx_edi_payment_document_ids.action_cancel()
        self.assertRecordValues(payment, [{'l10n_mx_edi_cfdi_state': 'cancel'}])

    def test_import_bill_cfdi_with_invalid_tax(self):
        file_name = "test_bill_import_without_tax"
        file_path = misc.file_path(f'{self.test_module}/tests/test_files/{file_name}.xml')

        assert file_path
        with file_open(file_path, 'rb') as file:
            content = file.read()

        # Read the problematic xml file that kept causing crash on bill uploads
        new_bill = self._upload_document_on_journal(
            journal=self.company_data['default_journal_purchase'],
            content=content,
            filename=file_name,
        )

        tax_id = self.env['account.chart.template'].ref('tax14')

        self.assertRecordValues(new_bill.invoice_line_ids, (
            {
                'quantity': 1,
                'price_unit': 54017.48,
                'tax_ids': [tax_id.id]
            },
            {
                'quantity': 1,
                'price_unit': 17893.00,
                # This should be empty due to the error causing missing attribute 'TasaOCuota' to result in empty tax_ids
                'tax_ids': []
            }
        ))

    def test_import_bill_cfdi_with_extento_tax(self):
        file_name = "test_bill_import_extento"
        full_file_path = misc.file_path(f'{self.test_module}/tests/test_files/{file_name}.xml')

        # Read the xml file
        with file_open(full_file_path, "rb") as file:
            new_bill = self._upload_document_on_journal(
                journal=self.company_data['default_journal_purchase'],
                content=file.read(),
                filename=file_name,
            )

        tax_id_1 = self.env['account.chart.template'].ref('tax14')
        tax_id_2 = self.env['account.chart.template'].ref('tax20')

        self.assertRecordValues(new_bill.invoice_line_ids, (
            {
                'quantity': 1,
                'price_unit': 54017.48,
                'tax_ids': [tax_id_1.id]
            },
            {
                'quantity': 1,
                'price_unit': 17893.00,
                'tax_ids': [tax_id_2.id]
            }
        ))

    def test_cfdi_rounding_1(self):
        def run(rounding_method):
            with freeze_time('2017-01-01'):
                invoice = self._create_invoice(
                    invoice_date='2017-01-01',
                    date='2017-01-01',
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 398.28,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        }),
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 108.62,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        }),
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 362.07,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        })] + [
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 31.9,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        }),
                    ] * 12,
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_1_{rounding_method}_inv')

                payment = self._create_payment(invoice)
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_1_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_2(self):
        def run(rounding_method):
            with freeze_time('2017-01-01'):
                invoice = self._create_invoice(
                    invoice_date='2017-01-01',
                    date='2017-01-01',
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'quantity': quantity,
                            'price_unit': price_unit,
                            'discount': discount,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        })
                        for quantity, price_unit, discount in (
                            (30, 84.88, 13.00),
                            (30, 18.00, 13.00),
                            (3, 564.32, 13.00),
                            (33, 7.00, 13.00),
                            (20, 49.88, 13.00),
                            (100, 3.10, 13.00),
                            (2, 300.00, 13.00),
                            (36, 36.43, 13.00),
                            (36, 15.00, 13.00),
                            (2, 61.08, 0),
                            (2, 13.05, 0),
                        )
                    ])
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_2_{rounding_method}_inv')

                payment = self._create_payment(invoice, currency_id=self.comp_curr.id)
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_2_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_3(self):
        date_1 = '2017-01-02'
        date_2 = '2017-01-01'
        self.setup_usd_rates((date_1, 17.187), (date_2, 17.0357))

        def run(rounding_method):
            with freeze_time(date_1):
                invoice = self._create_invoice(
                    invoice_date=date_1,
                    date=date_1,
                    currency_id=self.fake_usd_data['currency'].id,
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 7.34,
                            'quantity': 200,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        }),
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_3_{rounding_method}_inv')

            with freeze_time(date_2):
                payment = self._create_payment(
                    invoice,
                    payment_date=date_2,
                    currency_id=self.fake_usd_data['currency'].id,
                )
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_3_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_4(self):
        date_1 = '2017-01-02'
        date_2 = '2017-01-01'
        self.setup_usd_rates((date_1, 16.9912), (date_2, 17.068))

        def run(rounding_method):
            with freeze_time(date_1):
                invoice1 = self._create_invoice(
                    invoice_date=date_1,
                    date=date_1,
                    currency_id=self.fake_usd_data['currency'].id,
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 68.0,
                            'quantity': 68.25,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        }),
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice1._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice1, f'test_cfdi_rounding_4_{rounding_method}_inv_1')

            with freeze_time(date_2):
                invoice2 = self._create_invoice(
                    invoice_date=date_2,
                    date=date_2,
                    currency_id=self.fake_usd_data['currency'].id,
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': 68.0,
                            'quantity': 24.0,
                            'tax_ids': [Command.set(self.tax_16.ids)],
                        }),
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice2._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice2, f'test_cfdi_rounding_4_{rounding_method}_inv_2')

            invoices = invoice1 + invoice2
            with freeze_time(date_2):
                payment = self._create_payment(
                    invoices,
                    amount=7276.68,
                    currency_id=self.fake_usd_data['currency'].id,
                    payment_date=date_2,
                )
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_4_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_5(self):
        def run(rounding_method):
            with freeze_time('2017-01-01'):
                invoice = self._create_invoice(
                    invoice_date='2017-01-01',
                    date='2017-01-01',
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': price_unit,
                            'quantity': quantity,
                        })
                        for quantity, price_unit in (
                            (412.0, 43.65),
                            (412.0, 43.65),
                            (90.0, 50.04),
                            (500.0, 11.77),
                            (500.0, 34.93),
                            (90.0, 50.04),
                        )
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_5_{rounding_method}_inv')

                payment = self._create_payment(invoice)
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_5_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_6(self):
        def run(rounding_method):
            with freeze_time('2017-01-01'):
                invoice = self._create_invoice(
                    invoice_date='2017-01-01',
                    date='2017-01-01',
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': price_unit,
                            'quantity': quantity,
                            'discount': 30.0,
                        })
                        for quantity, price_unit in (
                            (7.0, 724.14),
                            (4.0, 491.38),
                            (2.0, 318.97),
                            (7.0, 224.14),
                            (6.0, 206.90),
                            (6.0, 129.31),
                            (6.0, 189.66),
                            (16.0, 775.86),
                            (2.0, 7724.14),
                            (2.0, 1172.41),
                        )
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_6_{rounding_method}_inv')

                payment = self._create_payment(invoice)
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_6_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_7(self):
        def run(rounding_method):
            with freeze_time('2017-01-01'):
                invoice = self._create_invoice(
                    invoice_date='2017-01-01',
                    date='2017-01-01',
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': price_unit,
                            'quantity': quantity,
                            'tax_ids': [Command.set(taxes.ids)],
                        })
                        for quantity, price_unit, taxes in (
                            (12.0, 457.92, self.tax_26_5_ieps + self.tax_16),
                            (12.0, 278.04, self.tax_26_5_ieps + self.tax_16),
                            (12.0, 539.76, self.tax_26_5_ieps + self.tax_16),
                            (36.0, 900.0, self.tax_16),
                        )
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_7_{rounding_method}_inv')

                payment = self._create_payment(invoice)
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_7_{rounding_method}_pay')

        self._test_cfdi_rounding(run)

    def test_cfdi_rounding_8(self):
        def run(rounding_method):
            with freeze_time('2017-01-01'):
                invoice = self._create_invoice(
                    invoice_date='2017-01-01',
                    date='2017-01-01',
                    invoice_line_ids=[
                        Command.create({
                            'product_id': self.product.id,
                            'price_unit': price_unit,
                            'quantity': quantity,
                            'tax_ids': [Command.set(taxes.ids)],
                        })
                        for quantity, price_unit, taxes in (
                            (1.0, 244.0, self.tax_0_ieps + self.tax_0),
                            (8.0, 244.0, self.tax_0_ieps + self.tax_0),
                            (1.0, 2531.0, self.tax_0),
                            (1.0, 2820.75, self.tax_6_ieps + self.tax_0),
                            (1.0, 2531.0, self.tax_0),
                            (8.0, 468.0, self.tax_0_ieps + self.tax_0),
                            (1.0, 2820.75, self.tax_6_ieps + self.tax_0),
                            (1.0, 210.28, self.tax_7_ieps),
                            (1.0, 2820.75, self.tax_6_ieps + self.tax_0),
                        )
                    ],
                )
                with self.with_mocked_pac_sign_success():
                    invoice._l10n_mx_edi_cfdi_invoice_try_send()
                self._assert_invoice_cfdi(invoice, f'test_cfdi_rounding_8_{rounding_method}_inv')

                payment = self._create_payment(invoice)
                with self.with_mocked_pac_sign_success():
                    payment.move_id._l10n_mx_edi_cfdi_payment_try_send()
                self._assert_invoice_payment_cfdi(payment.move_id, f'test_cfdi_rounding_8_{rounding_method}_pay')

        self._test_cfdi_rounding(run)
