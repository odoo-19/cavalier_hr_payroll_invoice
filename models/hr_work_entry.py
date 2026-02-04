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
        help="Customer location / site (res.partner) related to this work entry.",
    )

    # -------------------------------------------------------------------------
    # Onchanges
    # -------------------------------------------------------------------------
    @api.onchange("customer_id")
    def _onchange_customer_id_clear_location(self):
        for rec in self:
            if rec.customer_id and rec.location_id:
                # Only allow locations within customer's hierarchy.
                if rec.location_id != rec.customer_id and rec.location_id not in rec.customer_id.child_ids:
                    rec.location_id = False

    @api.onchange("employee_id", "date")
    def _onchange_employee_or_date_fill_customer_location(self):
        for rec in self:
            if rec.employee_id and rec.date and (not rec.customer_id or not rec.location_id):
                rec._apply_customer_location_from_work_location()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_employee_work_location_for_date(self, employee, work_date):
        """Return hr.work.location for an employee on a given date.

        Deterministic for your build (hr_homeworking):
        1) exceptional_location_id (if field exists and is set)
        2) <weekday>_location_id (monday_location_id .. sunday_location_id) (if exists and set)
        3) work_location_id fallback (if exists and set)
        """
        if not employee or not work_date:
            return self.env["hr.work.location"]

        work_date = fields.Date.to_date(work_date)
        if not work_date:
            return self.env["hr.work.location"]

        # 1) Exceptional location (one-off override)
        if "exceptional_location_id" in employee._fields and employee.exceptional_location_id:
            return employee.exceptional_location_id

        # 2) Weekday usual location
        weekday_map = {
            0: "monday_location_id",
            1: "tuesday_location_id",
            2: "wednesday_location_id",
            3: "thursday_location_id",
            4: "friday_location_id",
            5: "saturday_location_id",
            6: "sunday_location_id",
        }
        fname = weekday_map.get(work_date.weekday())
        if fname and fname in employee._fields:
            val = employee[fname]
            if val:
                return val

        # 3) Generic work location fallback
        if "work_location_id" in employee._fields and employee.work_location_id:
            return employee.work_location_id

        return self.env["hr.work.location"]

    def _apply_customer_location_from_work_location(self):
        """Populate customer/location based on the employee's work location mapping."""
        for rec in self:
            if not rec.employee_id or not rec.date:
                continue

            work_loc = rec._get_employee_work_location_for_date(rec.employee_id, rec.date)
            if not work_loc:
                continue

            # Only fill missing values so manual overrides are respected.
            if not rec.customer_id and getattr(work_loc, "customer_id", False):
                rec.customer_id = work_loc.customer_id
            if not rec.location_id and getattr(work_loc, "location_id", False):
                rec.location_id = work_loc.location_id

            # If location was set but customer is missing, try to infer customer from partner hierarchy.
            if not rec.customer_id and rec.location_id and rec.location_id.parent_id:
                rec.customer_id = rec.location_id.parent_id

    # -------------------------------------------------------------------------
    # ORM Overrides
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Auto-populate billing fields after generation/import if not provided.
        records.filtered(lambda r: not r.customer_id or not r.location_id)._apply_customer_location_from_work_location()
        return records
