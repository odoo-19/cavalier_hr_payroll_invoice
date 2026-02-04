# Cavalier Payroll Invoicing – Current State Summary

_Odoo 19 | Enterprise Payroll–compatible | DTR-driven_

---

## 1. Purpose (Big Picture)

This module bridges **HR → Payroll → Invoicing** for **Cavalier Security**, where:

- Guards are assigned to **customer sites**
- Time is captured via **manual DTR**
- DTR is imported into **Work Entries**
- Payroll is computed from Work Entries
- **Customer invoices are generated from payroll**, traceable down to site and period

Everything is designed to be:

- **Deterministic**
- **Audit-safe**
- **Location-accurate**

---

## 2. Data Model Enhancements

### A. `hr.work.location` (Single Source of Truth)

Work Locations are extended to carry **billing context**:

- `customer_id` → the client (company)
- `location_id` → the customer’s site / address (`res.partner`)

> **Design decision:**  
> Billing is defined at the **Work Location** level, not per employee and not per payslip.

This makes site-based billing explicit, reusable, and auditable.

---

### B. `hr.work.entry` (DTR → Payroll Backbone)

Each Work Entry now includes:

- `customer_id`
- `location_id`

These fields are **auto-populated**, not manually maintained.

#### Deterministic location resolution (based on `hr_homeworking`)

For a given **employee + date**, the Work Location is resolved in this order:

1. `exceptional_location_id` (one-off override)
2. `<weekday>_location_id`  
   (`monday_location_id`, `tuesday_location_id`, …)
3. fallback to `work_location_id`

Then the following mappings occur:

- `work_location.customer_id` → Work Entry `customer_id`
- `work_location.location_id` → Work Entry `location_id`

This logic applies to:

- Work Entry generation
- CSV imports
- Manual creation

No heuristics are used — all mappings are explicit and deterministic.

---

### C. `hr.payslip`

Payslips are extended with:

- `customer_id`
- `location_id`
- `invoice_id` (link to generated invoice)

During payslip creation (manual or via payroll run):

- Customer and Location are inferred from **overlapping Work Entries**
- Values are set **only if consistent** across the payslip period (safe by default)

This preserves data integrity and prevents cross-site contamination.

---

## 3. Payroll → Invoice Flow

### A. Invoice Wizard

A custom wizard is provided under:

**Accounting → Invoicing → Payroll Invoicing → Create Invoice from Payslips**

It supports:

- Date range
- Customer
- Location (optional)
- Invoice basis:
  - Employer Cost
  - Gross Wage
  - Net Wage
- Launch sources:
  - Payslip list (batch)
  - Payslip form

When launched from selected payslips, the wizard auto-fills:

- Customer
- Location
- Date range

---

### B. Invoice Generation Rules

- Only **validated / paid** payslips are eligible
- Double invoicing is prevented via `invoice_id`
- Generates `account.move` records (`out_invoice`)
- Maintains traceability:
  - Invoice → Payslip(s)

---

## 4. UI Enhancements (Carefully Scoped)

### Work Location UI

You can now edit:

- Customer
- Customer Location

directly on the **Work Location** list and form views.

---

### Work Entry UI

- Customer and Location fields are visible and editable when needed
- Views are bound to the **actual core XMLIDs** used in this Odoo 19 build

---

### Payslip UI

- Added a **Billing** group
- Added an **Invoice smart button**

All UI changes are:

- Fully **Odoo 17+ compliant** (no `attrs` / `states`)
- Upgrade-safe and isolated to inherited views

---

## 5. What This Enables (Strategically)

This module now provides:

- **Site-accurate payroll**
- **Site-accurate billing**
- **Full traceability**:  
  Invoice → Payslip → Work Entry → Work Location → Customer
- **Deterministic behavior** suitable for audit and compliance

This forms a strong, extensible foundation for **security-industry payroll and billing**, especially for DTR-driven operations.
