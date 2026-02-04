# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class HrPayslipToInvoiceWizard(models.TransientModel):
    _name = "hr.payslip.to.invoice.wizard"
    _description = "Create Customer Invoice from Payslips"

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        if "journal_id" in fields_list and not res.get("journal_id"):
            res["journal_id"] = company.payroll_billing_journal_id.id or self.env["account.journal"].search([("type", "=", "sale"), ("company_id", "=", company.id)], limit=1).id
        if "product_id" in fields_list and not res.get("product_id"):
            res["product_id"] = company.payroll_billing_product_id.id or self.env["product.product"].search([("name", "ilike", "Payroll"), ("company_id", "in", [company.id, False])], limit=1).id
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

        slips = self.env["hr.payslip"].search(self._get_payslip_domain(), order="employee_id, date_from, id")
        if not slips:
            raise UserError(_("No eligible payslips found for the given filters (state must be Validated/Paid and not yet invoiced)."))

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
                lines.append((0, 0, {
                    "product_id": self.product_id.id,
                    "name": _("Payroll billing - %(employee)s (%(from)s to %(to)s)") % {
                        "employee": emp.name,
                        "from": self.date_from,
                        "to": self.date_to,
                    },
                    "quantity": 1.0,
                    "price_unit": amount,
                }))
        else:
            total = sum(self._amount_from_slip(s) for s in slips)
            if not total:
                raise UserError(_("The computed total is 0. Please check payslip amounts and the selected invoice basis."))
            location_label = self.location_id.display_name if self.location_id else _("All locations")
            lines.append((0, 0, {
                "product_id": self.product_id.id,
                "name": _("Payroll billing - %(customer)s / %(location)s (%(from)s to %(to)s) - %(count)s payslip(s)") % {
                    "customer": self.customer_id.display_name,
                    "location": location_label,
                    "from": self.date_from,
                    "to": self.date_to,
                    "count": len(slips),
                },
                "quantity": 1.0,
                "price_unit": total,
            }))

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
