# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    payroll_billing_product_id = fields.Many2one(
        related="company_id.payroll_billing_product_id",
        readonly=False,
    )
    payroll_billing_journal_id = fields.Many2one(
        related="company_id.payroll_billing_journal_id",
        readonly=False,
    )
