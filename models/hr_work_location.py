# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        help="Customer to be billed for work performed at this work location.",
        domain=[("is_company", "=", True)],
    )
    location_id = fields.Many2one(
        "res.partner",
        string="Customer Location",
        help="Customer site / address (res.partner) corresponding to this work location.",
    )

    @api.onchange("customer_id")
    def _onchange_customer_id_clear_location(self):
        for rec in self:
            if rec.customer_id and rec.location_id:
                if rec.location_id != rec.customer_id and rec.location_id not in rec.customer_id.child_ids:
                    rec.location_id = False
