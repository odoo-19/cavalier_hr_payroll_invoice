# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # -------------------------------------------------------------------------
    # Billing fields
    # -------------------------------------------------------------------------

    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        domain=[("is_company", "=", True)],
        help="Customer to be billed for this payslip.",
    )

    location_id = fields.Many2one(
        "res.partner",
        string="Location",
        help="Customer location / site to be billed.",
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

    # -------------------------------------------------------------------------
    # Split (Billing-only)
    # -------------------------------------------------------------------------

    invoiceable = fields.Boolean(
        string="Invoiceable",
        default=True,
        help="If False, this payslip must not be used for invoicing.",
    )

    split_state = fields.Selection(
        [
            ("none", "Not Split"),
            ("base", "Base (Split)"),
            ("split", "Split Payslip"),
        ],
        default="none",
        copy=False,
        readonly=True,
    )

    split_base_id = fields.Many2one(
        "hr.payslip",
        string="Split Base Payslip",
        copy=False,
        readonly=True,
    )

    split_child_ids = fields.One2many(
        "hr.payslip",
        "split_base_id",
        string="Split Payslips",
        readonly=True,
    )

    work_entry_ids = fields.Many2many(
        "hr.work.entry",
        "hr_payslip_hr_work_entry_rel",
        "payslip_id",
        "work_entry_id",
        string="Work Entries (Billing Trace)",
        copy=False,
        help="Work entries linked for billing traceability only.",
    )

    billing_amount = fields.Monetary(
        string="Billing Amount",
        currency_field="currency_id",
        copy=False,
        readonly=True,
    )

    billing_hours = fields.Float(
        string="Billing Hours",
        copy=False,
        readonly=True,
    )

    billing_ratio = fields.Float(
        string="Billing Ratio",
        digits=(16, 6),
        copy=False,
        readonly=True,
    )

    has_multiple_locations = fields.Boolean(
        compute="_compute_split_flags",
        store=True,
    )

    split_needed = fields.Boolean(
        compute="_compute_split_flags",
        store=True,
    )

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------

    @api.depends("employee_id", "date_from", "date_to")
    def _compute_split_flags(self):
        for slip in self:
            slip.has_multiple_locations = False
            slip.split_needed = False

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                continue

            wes = slip._get_overlapping_work_entries()
            if not wes:
                continue

            loc_ids = set()
            has_blank = False
            for we in wes:
                if we.location_id:
                    loc_ids.add(we.location_id.id)
                else:
                    has_blank = True

            distinct = len(loc_ids) + (1 if has_blank else 0)
            slip.has_multiple_locations = distinct > 1
            slip.split_needed = (
                slip.has_multiple_locations
                and slip.invoiceable
                and slip.split_state == "none"
            )

    @api.depends("invoice_id")
    def _compute_invoiced(self):
        for slip in self:
            slip.invoiced = bool(slip.invoice_id)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_overlapping_work_entries(self):
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return self.env["hr.work.entry"]

        domain = [
            ("employee_id", "=", self.employee_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("state", "!=", "cancelled"),
        ]
        return self.env["hr.work.entry"].search(domain)

    def _set_customer_location_from_work_entries(self):
        for slip in self:
            wes = slip._get_overlapping_work_entries()
            if not wes:
                continue

            if not slip.customer_id:
                customers = wes.mapped("customer_id").filtered(lambda p: p)
                if customers and len(customers) == 1:
                    slip.customer_id = customers[0]

            if not slip.location_id:
                locations = wes.mapped("location_id").filtered(lambda p: p)
                if locations and len(locations) == 1:
                    slip.location_id = locations[0]

    @api.onchange("employee_id", "date_from", "date_to")
    def _onchange_employee_or_dates_autofill_billing(self):
        for slip in self:
            if not slip.customer_id or not slip.location_id:
                slip._set_customer_location_from_work_entries()

    @api.model_create_multi
    def create(self, vals_list):
        slips = super().create(vals_list)
        for slip, vals in zip(slips, vals_list):
            if not vals.get("customer_id") or not vals.get("location_id"):
                slip._set_customer_location_from_work_entries()
        return slips

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_split_by_location(self):
        WorkEntry = self.env["hr.work.entry"]
        new_slips = self.env["hr.payslip"]

        def _we_hours(we):
            if "duration" in we._fields and we.duration:
                return float(we.duration)
            return 0.0

        for slip in self:
            if slip.split_state != "none":
                continue

            if slip.invoice_id:
                raise UserError(_("Cannot split a payslip already linked to an invoice."))

            if slip.state not in ("validated", "paid"):
                raise UserError(_("Payslip must be validated or paid before billing split."))

            wes = slip._get_overlapping_work_entries()
            if not wes:
                raise UserError(_("No work entries found for this payslip period."))

            if wes.filtered(lambda w: not w.location_id):
                raise UserError(_("All work entries must have a Location before splitting."))

            groups = {}
            for we in wes:
                groups.setdefault(we.location_id.id, WorkEntry)
                groups[we.location_id.id] |= we

            loc_hours = {
                loc_id: sum(_we_hours(we) for we in we_set)
                for loc_id, we_set in groups.items()
            }

            total_hours = sum(loc_hours.values())
            if total_hours <= 0:
                raise UserError(_("Total work entry hours is zero."))

            base_amount = float(slip.net_wage or 0.0)
            if not base_amount:
                raise UserError(_("Net wage is zero; nothing to split."))

            currency = slip.company_id.currency_id
            precision = currency.decimal_places or 2

            allocations = {}
            for loc_id, hours in loc_hours.items():
                ratio = hours / total_hours
                allocations[loc_id] = {
                    "hours": hours,
                    "ratio": ratio,
                    "amount": round(base_amount * ratio, precision),
                }

            diff = round(base_amount - sum(v["amount"] for v in allocations.values()), precision)
            if diff:
                largest = max(allocations, key=lambda k: allocations[k]["hours"])
                allocations[largest]["amount"] = round(
                    allocations[largest]["amount"] + diff, precision
                )

            for loc_id, data in allocations.items():
                vals = {
                    "name": "%s (%s)" % (
                        slip.name or _("Payslip"),
                        self.env["res.partner"].browse(loc_id).display_name,
                    ),
                    "employee_id": slip.employee_id.id,
                    "company_id": slip.company_id.id,
                    "struct_id": slip.struct_id.id,
                    "version_id": slip.version_id.id,
                    "date_from": slip.date_from,
                    "date_to": slip.date_to,
                    "customer_id": slip.customer_id.id,
                    "location_id": loc_id,
                    "split_state": "split",
                    "split_base_id": slip.id,
                    "invoiceable": True,
                    "billing_amount": data["amount"],
                    "billing_hours": data["hours"],
                    "billing_ratio": data["ratio"],
                }
                new_slips |= self.create(vals)

            slip.write({
                "invoiceable": False,
                "split_state": "base",
            })

        return {"type": "ir.actions.client", "tag": "reload"}

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