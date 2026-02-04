# -*- coding: utf-8 -*-
{
    "name": "Cavalier Payroll Invoicing",
    "summary": "Create customer invoices from payroll payslips (date range, customer, location)",
    "version": "19.0.1.1.0",
    "category": "Human Resources/Payroll",
    "author": "Cavalier Security / Obanana Corp",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_payslip_views.xml",
        "wizard/payslip_to_invoice_wizard_views.xml",
    ],
    "application": False,
    "installable": True,
}
