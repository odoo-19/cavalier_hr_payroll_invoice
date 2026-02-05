# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipToInvoiceWizard(models.TransientModel):
    _name = "hr.payslip.to.invoice.wizard"
    _description = "Create Customer Invoice from Payslips"

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    payslip_ids = fields.Many2many("hr.payslip", string="Payslips", readonly=True)

    customer_id = fields.Many2one("res.partner", string="Customer", required=True)
    location_id = fields.Many2one(
        "res.partner",
        string="Location",
        help="Optional. If set, only payslips for this location are included.",
    )

    invoice_date = fields.Date(default=fields.Date.context_today, required=True)

    journal_id = fields.Many2one(
        "account.journal",
        domain=[("type", "=", "sale")],
        help="Sales journal to use for the invoice.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Invoice Product",
        required=True,
        help="Product used on invoice lines. Configure its income account properly.",
    )

    invoice_basis = fields.Selection(
        [
            ("employer_cost", "Employer Cost"),
            ("gross_wage", "Gross Wage"),
            ("net_wage", "Net Wage"),
        ],
        default="employer_cost",
        required=True,
        help="Which payslip amount to bill.",
    )

    group_by_employee = fields.Boolean(
        default=False,
        help="If enabled, creates one invoice line per employee (summed over the selected payslips).",
    )

    @api.onchange("customer_id")
    def _onchange_customer_id(self):
        if self.customer_id and self.location_id:
            if self.location_id != self.customer_id and self.location_id not in self.customer_id.child_ids:
                self.location_id = False

    @api.onchange("payslip_ids")
    def _onchange_payslip_ids_autofill(self):
        if not self.payslip_ids:
            return

        slips = self.payslip_ids

        # auto dates
        self.date_from = min(slips.mapped("date_from"))
        self.date_to = max(slips.mapped("date_to"))

        # auto customer if consistent
        customers = slips.mapped("customer_id").filtered(lambda p: p)
        self.customer_id = customers[0] if customers and len(customers) == 1 else False

        # auto location if consistent
        locations = slips.mapped("location_id").filtered(lambda p: p)
        self.location_id = locations[0] if locations and len(locations) == 1 else False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company

        # Existing defaults
        if not res.get("journal_id"):
            res["journal_id"] = (
                company.payroll_billing_journal_id.id
                or self.env["account.journal"].search(
                    [("type", "=", "sale"), ("company_id", "=", company.id)],
                    limit=1,
                ).id
            )

        if not res.get("product_id"):
            res["product_id"] = (
                company.payroll_billing_product_id.id
                or self.env["product.product"].search(
                    [("name", "ilike", "Payroll"), ("company_id", "in", [company.id, False])],
                    limit=1,
                ).id
            )

        # Derive defaults from selected payslips (active_ids)
        active_ids = self.env.context.get("active_ids") or []
        if not active_ids:
            return res

        slips = self.env["hr.payslip"].browse(active_ids).exists()
        if not slips:
            return res

        # Safety: ensure single company selection
        companies = slips.mapped("company_id")
        if len(companies) > 1:
            raise UserError(_("Please select payslips from only ONE company."))

        # Always set payslip_ids (do not depend on fields_list)
        res["payslip_ids"] = [(6, 0, slips.ids)]

        # Dates: min/max
        if not res.get("date_from"):
            res["date_from"] = min(slips.mapped("date_from"))
        if not res.get("date_to"):
            res["date_to"] = max(slips.mapped("date_to"))

        # Customer: only set if all slips share the same customer
        customers = slips.mapped("customer_id").filtered(lambda p: p)
        if not res.get("customer_id"):
            if customers and len(customers) == 1:
                res["customer_id"] = customers.id

        # Location: only set if all slips share the same location
        locations = slips.mapped("location_id").filtered(lambda p: p)
        if not res.get("location_id"):
            if locations and len(locations) == 1:
                res["location_id"] = locations.id

        return res

    def _get_payslip_domain(self):
        self.ensure_one()
        domain = [
            ("state", "in", ["validated", "paid"]),
            ("date_from", ">=", self.date_from),
            ("date_to", "<=", self.date_to),
            ("customer_id", "=", self.customer_id.id),
            ("invoice_id", "=", False),
            ("company_id", "=", self.env.company.id),
        ]
        if self.location_id:
            domain.append(("location_id", "=", self.location_id.id))
        return domain

    def _amount_from_slip(self, slip):
        field_name = self.invoice_basis
        return float(getattr(slip, field_name) or 0.0)

    def action_create_invoice(self):
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_("Invalid date range: Date From must be earlier than or equal to Date To."))

        if not self.product_id:
            raise UserError(_("Please select an invoice product."))

        if not self.journal_id:
            raise UserError(_("Please select a sales journal."))

        # ✅ Invoice exactly what the user selected (if provided)
        slips = self.payslip_ids

        # If wizard was launched from a payslip list selection, do NOT fallback to domain search.
        active_ids = self.env.context.get("active_ids") or []
        if active_ids and not slips:
            raise UserError(_("No payslips were carried into the wizard. Please relaunch from your selection."))

        # Only allow domain search when not launched from a selection (e.g., opened from menu)
        if not slips:
            slips = self.env["hr.payslip"].search(self._get_payslip_domain(), order="employee_id, date_from, id")
            if not slips:
                raise UserError(
                    _("No eligible payslips found for the given filters (state must be Validated/Paid and not yet invoiced).")
                )

        # ✅ Enforce eligibility rules even for manually selected payslips
        bad_state = slips.filtered(lambda s: s.state not in ("validated", "paid"))
        if bad_state:
            raise UserError(_("Some selected payslips are not Validated/Paid."))

        already_invoiced = slips.filtered(lambda s: s.invoice_id)
        if already_invoiced:
            raise UserError(_("Some selected payslips are already linked to an invoice."))

        companies = slips.mapped("company_id")
        if len(companies) != 1 or companies[0] != self.env.company:
            raise UserError(_("Please select payslips from the active company only."))

        if self.customer_id:
            bad = slips.filtered(lambda s: s.customer_id != self.customer_id)
            if bad:
                raise UserError(_("Some selected payslips have a different customer than the wizard Customer."))

        if self.location_id:
            bad = slips.filtered(lambda s: s.location_id != self.location_id)
            if bad:
                raise UserError(_("Some selected payslips have a different location than the wizard Location."))

        # Prepare invoice lines
        lines = []
        if self.group_by_employee:
            grouped = {}
            for s in slips:
                grouped.setdefault(s.employee_id, 0.0)
                grouped[s.employee_id] += self._amount_from_slip(s)

            for emp, amount in grouped.items():
                if not amount:
                    continue
                lines.append(
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_id.id,
                            "name": _("Payroll billing - %(employee)s (%(from)s to %(to)s)")
                            % {
                                "employee": emp.name,
                                "from": self.date_from,
                                "to": self.date_to,
                            },
                            "quantity": 1.0,
                            "price_unit": amount,
                        },
                    )
                )
        else:
            total = sum(self._amount_from_slip(s) for s in slips)
            if not total:
                raise UserError(_("The computed total is 0. Please check payslip amounts and the selected invoice basis."))
            location_label = self.location_id.display_name if self.location_id else _("All locations")
            lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": self.product_id.id,
                        "name": _(
                            "Payroll billing - %(customer)s / %(location)s (%(from)s to %(to)s) - %(count)s payslip(s)"
                        )
                        % {
                            "customer": self.customer_id.display_name,
                            "location": location_label,
                            "from": self.date_from,
                            "to": self.date_to,
                            "count": len(slips),
                        },
                        "quantity": 1.0,
                        "price_unit": total,
                    },
                )
            )

        move_vals = {
            "move_type": "out_invoice",
            "partner_id": self.customer_id.id,
            "invoice_date": self.invoice_date,
            "journal_id": self.journal_id.id,
            "invoice_origin": _("Payroll %(from)s to %(to)s") % {"from": self.date_from, "to": self.date_to},
            "invoice_line_ids": lines,
        }

        # If a location is provided, set shipping address when field exists
        if self.location_id and "partner_shipping_id" in self.env["account.move"]._fields:
            move_vals["partner_shipping_id"] = self.location_id.id

        invoice = self.env["account.move"].create(move_vals)

        # Link slips to invoice
        slips.write({"invoice_id": invoice.id})

        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Invoice"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": invoice.id,
            "target": "current",
        }
