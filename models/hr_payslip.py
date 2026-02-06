# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain

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
        help="If set, the payslip computation uses ONLY these work entries. Used when splitting a payslip by location.",
    )


    allocated_net_wage = fields.Monetary(
        string="Allocated Net Wage",
        currency_field="currency_id",
        copy=False,
        help="For split payslips: the allocated net pay amount (proportional by work entry hours).",
    )
    allocated_gross_wage = fields.Monetary(
        string="Allocated Gross Wage",
        currency_field="currency_id",
        copy=False,
        help="For split payslips: the allocated gross wage amount (proportional by work entry hours).",
    )
    allocated_employer_cost = fields.Monetary(
        string="Allocated Employer Cost",
        currency_field="currency_id",
        copy=False,
        help="For split payslips: the allocated employer cost amount (proportional by work entry hours).",
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
    # Payroll computation scoping
    # -------------------------------------------------------------------------
    def _get_worked_day_lines(self, domain=None):
        """Scope worked days computation to work_entry_ids when splitting."""
        self.ensure_one()
        if self.work_entry_ids:
            domain = Domain.AND([domain or [], [("id", "in", self.work_entry_ids.ids)]])
        return super()._get_worked_day_lines(domain=domain)

    def _get_worked_day_lines_values(self, domain=None):
        """Scope worked days computation to work_entry_ids when splitting."""
        self.ensure_one()
        if self.work_entry_ids:
            domain = Domain.AND([domain or [], [("id", "in", self.work_entry_ids.ids)]])
        return super()._get_worked_day_lines_values(domain=domain)



    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def action_split_by_location(self):
    """Split selected payslip(s) into multiple payslips by location (allocation-only).

    Less-complicated allocation strategy:
    - Keep the original payslip generation + computation unchanged.
    - Detect multiple locations via overlapping work entries.
    - When splitting:
        * Create one child payslip per location.
        * Allocate the base payslip totals proportionally by WORK ENTRY HOURS per location.
        * Do NOT recompute payroll rules on child slips (these are intended for invoicing allocation).
    - Mark the base payslip as not invoiceable (so invoicing uses only split slips).
    """
    WorkEntry = self.env["hr.work.entry"]
    new_slips = self.env["hr.payslip"]

    def _round(amount):
        # Use currency rounding (2 decimals typically)
        cur = self.env.company.currency_id
        return cur.round(amount) if cur else round(amount, 2)

        for slip in self:
            if slip.split_state != "none":
                continue

            if slip.invoice_id:
                raise UserError(_("Cannot split a payslip that is already linked to an invoice."))

            if not slip.employee_id or not slip.date_from or not slip.date_to:
                raise UserError(_("Payslip must have Employee and Date range before splitting."))

            # Ensure base slip is computed so totals exist
            if not slip.line_ids:
                slip.compute_sheet()

            # Work entries for the payslip period
            wes = slip._get_overlapping_work_entries()
            if not wes:
                raise UserError(_("No work entries found for this payslip period."))

            # Require locations on work entries (split by location only)
            missing_loc = wes.filtered(lambda w: not w.location_id)
            if missing_loc:
                raise UserError(_(
                    "Some work entries in this payslip period have no Location. "
                    "Please fix work entries first before splitting."
                ))

            # If customer is already set on the payslip, ensure work entries don't contain multiple customers
            if slip.customer_id:
                cust_ids = set((w.customer_id.id or 0) for w in wes)
                if len(cust_ids) > 1:
                    raise UserError(_(
                        "Multiple Customers detected in work entries for this period. "
                        "This split action is configured to split by Location only."
                    ))

            # Group work entries by location and compute total hours per location
            groups = {}  # location -> work_entry recordset
            hours_by_loc = {}  # location -> float hours
            total_hours = 0.0

            for we in wes:
                groups.setdefault(we.location_id, WorkEntry)
                groups[we.location_id] |= we

            if len(groups) <= 1:
                raise UserError(_("This payslip does not have multiple locations to split."))

            for location, we_set in groups.items():
                # duration is usually in hours
                loc_hours = sum((we.duration or 0.0) for we in we_set)
                hours_by_loc[location] = loc_hours
                total_hours += loc_hours

            if total_hours <= 0:
                raise UserError(_("Total work entry hours is 0 for this period; cannot split proportionally."))

            # Base totals to allocate
            base_net = float(slip.net_wage or 0.0)
            base_gross = float(slip.gross_wage or 0.0)
            base_employer = float(slip.employer_cost or 0.0)

            # Create split slips per location (draft) and allocate amounts
            split_slips = self.env["hr.payslip"]

            # Sort locations by hours desc for remainder assignment
            locs_sorted = sorted(hours_by_loc.items(), key=lambda kv: kv[1], reverse=True)

            # First pass allocations with rounding
            allocs = []
            for location, loc_hours in locs_sorted:
                ratio = (loc_hours / total_hours) if total_hours else 0.0
                allocs.append({
                    "location": location,
                    "we_set": groups[location],
                    "ratio": ratio,
                    "net": _round(base_net * ratio),
                    "gross": _round(base_gross * ratio),
                    "employer": _round(base_employer * ratio),
                })

    # Fix rounding remainders so totals match base exactly
    def _fix_remainder(field, base_total):
        s = sum(a[field] for a in allocs)
        diff = _round(base_total - s)
        if allocs and diff:
            allocs[0][field] = _round(allocs[0][field] + diff)

        _fix_remainder("net", base_net)
        _fix_remainder("gross", base_gross)
        _fix_remainder("employer", base_employer)

        for a in allocs:
            location = a["location"]
            we_set = a["we_set"]
            vals = {
                "customer_id": slip.customer_id.id if slip.customer_id else (we_set[:1].customer_id.id or False),
                "location_id": location.id,
                "invoice_id": False,
                "invoiceable": True,
                "split_state": "split",
                "split_base_id": slip.id,
                "work_entry_ids": [(6, 0, we_set.ids)],
                # Allocation totals
                "allocated_net_wage": a["net"],
                "allocated_gross_wage": a["gross"],
                "allocated_employer_cost": a["employer"],
                # Keep as draft (allocation-only)
                "state": "draft",
            }
            child = slip.copy(vals)

            # Do not compute payroll on child slips; they are allocation records
            split_slips |= child
            new_slips |= child

        # Mark base as non-invoiceable to prevent billing the unsplit slip
        slip.write({
            "invoiceable": False,
            "split_state": "base",
        })

        new_slips |= slip.split_child_ids

        if new_slips:
            return {
                "type": "ir.actions.act_window",
                "name": _("Split Payslips"),
                "res_model": "hr.payslip",
                "view_mode": "list,form",
                "domain": [("id", "in", new_slips.ids)],
                "target": "current",
            }
        return True

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
