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

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_employee_work_location_for_date(self, employee, work_date):
        """Return hr.work.location for an employee and date.

        We support different field names across builds by checking which fields
        exist on hr.employee.
        """
        if not employee or not work_date:
            return self.env["hr.work.location"]

        # Ensure date object
        work_date = fields.Date.to_date(work_date)

        # Prefer per-weekday "Usual Work Location" fields if present.
        # User described fields Monday..Sunday. Common naming patterns are:
        # - usual_work_location_id_monday ... _sunday
        # - usual_work_location_monday_id ... _sunday_id
        day = work_date.weekday()  # 0=Mon
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        dname = day_names[day]

        candidates = [
            f"usual_work_location_id_{dname}",
            f"usual_work_location_{dname}_id",
            f"usual_work_location_{dname}",
        ]
        for fname in candidates:
            if fname in employee._fields:
                val = employee[fname]
                if val:
                    return val

        # Fallback to generic work location
        if "work_location_id" in employee._fields and employee.work_location_id:
            return employee.work_location_id

        return self.env["hr.work.location"]

    def _apply_customer_location_from_work_location(self):
        """Populate customer/location on work entries based on hr.work.location mapping."""
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

    @api.onchange("employee_id", "date")
    def _onchange_employee_or_date_fill_customer_location(self):
        for rec in self:
            if rec.employee_id and rec.date and (not rec.customer_id or not rec.location_id):
                rec._apply_customer_location_from_work_location()
