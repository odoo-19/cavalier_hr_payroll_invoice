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

    
    # -------------------------------------------------------------------------
    # Split by Location (post-generation)
    # -------------------------------------------------------------------------
    invoiceable = fields.Boolean(
        string="Invoiceable",
        default=True,
        help="If False, this payslip must not be used for invoicing (e.g., it has been split).",
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
        help="If this payslip was created by splitting another payslip, this points to the base payslip.",
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
        string="Work Entries (Split Scope)",
        copy=False,
        help="Work entries associated with this split payslip (for billing traceability). No payroll recomputation is performed.",
    )


    billing_amount = fields.Monetary(
        string="Billing Amount",
        currency_field="currency_id",
        copy=False,
        readonly=True,
        help="Billing-only amount allocated to this split payslip. Used for invoicing (no payroll recomputation).",
    )
    billing_hours = fields.Float(
        string="Billing Hours",
        copy=False,
        readonly=True,
        help="Total hours for this location used to compute the billing allocation.",
    )
    billing_ratio = fields.Float(
        string="Billing Ratio",
        digits=(16, 6),
        copy=False,
        readonly=True,
        help="Allocation ratio (billing_hours / total_hours) used for computing billing_amount.",
    )

    has_multiple_locations = fields.Boolean(
        string="Multiple Locations",
        compute="_compute_split_flags",
        store=True,
        help="True if overlapping work entries contain multiple distinct locations (including blank).",
    )
    split_needed = fields.Boolean(
        string="Split Needed",
        compute="_compute_split_flags",
        store=True,
        help="True if this payslip should be split by location before invoicing.",
    )


    @api.depends("employee_id", "date_from", "date_to")
    def _compute_split_flags(self):
        """Compute split indicators based on overlapping work entries.

        A payslip is flagged when overlapping work entries span more than one
        distinct location (including missing location).
        """
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
            slip.split_needed = slip.has_multiple_locations and slip.invoiceable and slip.split_state == 'none'

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
        """Return work entries for the payslip's employee overlapping the payslip period.

        Note: In Odoo 19 hr_work_entry, the work entry date range is represented by a single
        date field (`date`) + duration, not `date_start/date_stop`.
        """
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


    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    
    
    def action_split_by_location(self):
        """Split selected payslip(s) into billing-only split payslips by Location.

        Billing-only strategy:
        - The base payslip remains the true payroll document (computed normally).
        - Split payslips are created PER location and store an allocated Billing Amount only.
        - Allocation is proportional to Work Entry hours per location over the payslip period.
        - No payroll recomputation is performed on split payslips.

        Requirements:
        - Base payslip must be Validated/Paid (Net Wage must be final).
        - All overlapping work entries must have Location.
        """

        WorkEntry = self.env["hr.work.entry"]
        new_slips = self.env["hr.payslip"]

        def _we_hours(we):
            # Prefer native duration when present; otherwise compute from dates.
            if "duration" in we._fields and we.duration:
                return float(we.duration)
            if we.date_start and we.date_stop:
                delta = fields.Datetime.to_datetime(we.date_stop) - fields.Datetime.to_datetime(we.date_start)
                return float(delta.total_seconds() / 3600.0)
            return 0.0

        for slip in self:
            # Only split base payslips once
            if slip.split_state != "none":
                continue

            if slip.invoice_id:
                raise UserError(_("Cannot split a payslip that is already linked to an invoice."))

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                raise UserError(_("Payslip must have Employee and Date range before splitting."))

            # Billing-only splits should be based on a final net wage
            if slip.state not in ("validated", "paid"):
                raise UserError(_("Please validate (or pay) the payslip before splitting for billing-only invoicing."))

            # Ensure base slip is computed so net_wage is available
            if not slip.line_ids:
                slip.compute_sheet()

            wes = slip._get_overlapping_work_entries()
            if not wes:
                raise UserError(_("No work entries found for this payslip period."))

            # Require locations on work entries
            missing_loc = wes.filtered(lambda w: not w.location_id)
            if missing_loc:
                raise UserError(_(
                    "Some work entries in this payslip period have no Location. "
                    "Please fix work entries first before splitting."
                ))

            # Group work entries by location
            groups = {}
            for we in wes:
                loc_id = we.location_id.id
                groups.setdefault(loc_id, WorkEntry)
                groups[loc_id] |= we

            # Compute hours per location and total hours
            loc_hours = {loc_id: sum(_we_hours(we) for we in we_set) for loc_id, we_set in groups.items()}
            total_hours = sum(loc_hours.values())
            if total_hours <= 0:
                raise UserError(_("Total work entry hours is zero for this payslip period; cannot split proportionally."))

            currency = slip.company_id.currency_id
            base_amount = float(slip.net_wage or 0.0)
            if not base_amount:
                raise UserError(_("Net Wage is zero; nothing to split for billing."))

            # Prepare allocations with currency rounding
            precision = currency.decimal_places if currency and hasattr(currency, "decimal_places") else 2
            allocations = {}
            for loc_id, hours in loc_hours.items():
                ratio = hours / total_hours
                amt = round(base_amount * ratio, precision)
                allocations[loc_id] = {
                    "hours": hours,
                    "ratio": ratio,
                    "amount": amt,
                }

            # Fix rounding remainder to ensure totals match exactly
            allocated_sum = sum(v["amount"] for v in allocations.values())
            remainder = round(base_amount - allocated_sum, precision)
            if remainder:
                # Add remainder to the largest allocation by hours (stable & intuitive)
                largest_loc = max(allocations.keys(), key=lambda k: allocations[k]["hours"])
                allocations[largest_loc]["amount"] = round(allocations[largest_loc]["amount"] + remainder, precision)

            # Create child payslips
            for loc_id, data in allocations.items():
                child_vals = {
                    "name": "%s (%s)" % (slip.name or _("Payslip"), self.env["res.partner"].browse(loc_id).display_name),
                    "employee_id": slip.employee_id.id,
                    "company_id": slip.company_id.id,
                    "struct_id": slip.struct_id.id,
                    "contract_id": slip.contract_id.id,
                    "date_from": slip.date_from,
                    "date_to": slip.date_to,
                    "customer_id": slip.customer_id.id,
                    "location_id": loc_id,
                    "split_state": "split",
                    "split_base_id": slip.id,
                    "invoiceable": True,
                    # Billing-only fields
                    "billing_amount": data["amount"],
                    "billing_hours": data["hours"],
                    "billing_ratio": data["ratio"],
                }
                child = self.create(child_vals)
                new_slips |= child

            # Mark base payslip as base/non-invoiceable
            slip.write({
                "invoiceable": False,
                "split_state": "base",
            })

        # Refresh the UI so user sees created split slips immediately
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