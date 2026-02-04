# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        help="Customer to be billed for this payslip.",
        domain=[("is_company", "=", True)],
    )
    location_id = fields.Many2one(
        "res.partner",
        string="Location",
        help="Customer location / site to be billed (usually a delivery address under the customer).",
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Customer Invoice",
        readonly=True,
        copy=False,
        help="Invoice generated from this payslip.",
    )
    invoiced = fields.Boolean(
        string="Invoiced",
        compute="_compute_invoiced",
        store=True,
    )

    @api.depends("invoice_id")
    def _compute_invoiced(self):
        for slip in self:
            slip.invoiced = bool(slip.invoice_id)

    @api.onchange("customer_id")
    def _onchange_customer_id_set_location_domain(self):
        if self.customer_id:
            # Suggest a location address under the customer if available.
            # Keep current location if it belongs to the same customer tree.
            if self.location_id and self.location_id not in self.customer_id.child_ids and self.location_id != self.customer_id:
                self.location_id = False

    def _get_overlapping_work_entries(self):
        """Return work entries for the payslip's employee overlapping the payslip period."""
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return self.env["hr.work.entry"]
        # date_from/date_to are dates; work entries are datetimes.
        dt_from = fields.Datetime.to_datetime(f"{self.date_from} 00:00:00")
        dt_to = fields.Datetime.to_datetime(f"{self.date_to} 23:59:59")
        return self.env["hr.work.entry"].search([
            ("employee_id", "=", self.employee_id.id),
            ("date_start", "<=", dt_to),
            ("date_stop", ">=", dt_from),
        ])

    def _set_customer_location_from_work_entries(self):
        """Populate customer/location from work entries when the period is consistent.
        - If all overlapping work entries share the same customer -> set customer_id
        - If all overlapping work entries share the same location -> set location_id
        Otherwise leave blank (or keep existing values).
        """
        for slip in self:
            if not slip.employee_id or not slip.date_from or not slip.date_to:
                continue
            wes = slip._get_overlapping_work_entries()
            if not wes:
                continue

            # CUSTOMER
            if not slip.customer_id:
                customers = wes.mapped("customer_id").filtered(lambda p: p)
                if customers and len(customers) == 1:
                    slip.customer_id = customers[0]

            # LOCATION
            if not slip.location_id:
                locations = wes.mapped("location_id").filtered(lambda p: p)
                if locations and len(locations) == 1:
                    slip.location_id = locations[0]



    @api.onchange("employee_id", "date_from", "date_to")
    def _onchange_employee_or_dates_autofill_billing(self):
        for slip in self:
            # Only auto-fill when empty, to avoid overwriting manual inputs.
            if not slip.customer_id or not slip.location_id:
                slip._set_customer_location_from_work_entries()

    @api.model_create_multi
    def create(self, vals_list):
        slips = super().create(vals_list)
        # Auto-fill billing fields from work entries when not provided.
        for slip, vals in zip(slips, vals_list):
            if not vals.get("customer_id") or not vals.get("location_id"):
                slip._set_customer_location_from_work_entries()
        return slips


    def action_view_customer_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("No invoice is linked to this payslip."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Invoice"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.invoice_id.id,
        }
