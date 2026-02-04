# -*- coding: utf-8 -*-
from odoo import fields, models

class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_billing_product_id = fields.Many2one(
        "product.product",
        string="Payroll Billing Product",
        help="Default product used when creating customer invoices from payslips.",
    )
    payroll_billing_journal_id = fields.Many2one(
        "account.journal",
        string="Payroll Billing Journal",
        domain=[("type", "=", "sale")],
        help="Default sales journal used when creating customer invoices from payslips.",
    )
