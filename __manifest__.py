# -*- coding: utf-8 -*-
{
    "name": "Cavalier Payroll Invoicing",
    "summary": "Create customer invoices from payroll payslips (date range, customer, location)",
    "version": "19.0.1.3.1",
    "category": "Human Resources/Payroll",
    "author": "Cavalier Security / Obanana Corp",
    "license": "LGPL-3",
    "depends": ["hr_payroll", "account", "hr", "hr_work_entry"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_payslip_views.xml",
        "views/hr_work_entry_views.xml",
        "views/hr_work_location_views.xml",
        "wizard/payslip_to_invoice_wizard_views.xml",
    ],
    "application": False,
    "installable": True,
}
