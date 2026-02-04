# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        help="Customer to be billed for this work entry.",
        domain=[("is_company", "=", True)],
    )
    location_id = fields.Many2one(
        "res.partner",
        string="Location",
        help="Customer location / site related to this work entry.",
    )

    @api.onchange("customer_id")
    def _onchange_customer_id_clear_location(self):
        for rec in self:
            if rec.customer_id and rec.location_id:
                # If location is not under customer hierarchy, clear it.
                if rec.location_id != rec.customer_id and rec.location_id not in rec.customer_id.child_ids:
                    rec.location_id = False
