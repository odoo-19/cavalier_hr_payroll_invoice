# Cavalier HR Payroll Invoicing

This module extends **Odoo HR Payroll** to support **customer- and location-based payroll invoicing**, including automatic **payslip splitting by work location** and a flexible **Payslip → Invoice** workflow.

It is designed for service-oriented companies where payroll costs must be billed accurately to clients and operational locations.

---

## Key Features

### 1. Payroll-to-Invoice Wizard

Generate customer invoices directly from validated or paid payslips using a guided wizard.

**Supported invoice bases:**
- Gross Wage
- Employer Cost
- Net Wage

**Core capabilities:**
- Select multiple payslips manually or launch the wizard from list view
- Automatically computes invoice amounts based on the selected basis
- Prevents invoicing of:
  - draft or cancelled payslips
  - already-invoiced payslips
  - payslips explicitly marked as non-invoiceable
- Links generated invoices back to the source payslips for traceability

---

### 2. Grouping Options (Advanced)

The wizard supports two invoicing modes:

- **Single summary line**
  - Aggregates all selected payslips into one invoice line

- **Group by Employee**
  - Creates one invoice line per employee
  - Each line aggregates the selected basis (gross, net, or employer cost) for that employee

This allows flexible billing layouts depending on customer requirements.

---

### 3. Payslip Splitting by Work Location

Payslips that contain work entries across multiple locations can be **split automatically**.

#### Split workflow:
- A **“Split by Location”** button appears when multiple work locations are detected
- One child payslip is generated per location
- Each split payslip:
  - Computes payroll only from its assigned work entries
  - Represents a single customer/location combination
- The original payslip becomes a **base payslip** and is excluded from invoicing

#### Deduction handling:
- Deduction lines are removed from all split payslips
- Deductions are reassigned to the split payslip with the **largest employer cost**
- Ensures deductions are counted once and not duplicated

If the original payslip was already validated or paid, all generated split payslips are automatically validated as well.

---

### 4. Location-Scoped Payroll Computation

Split payslips compute payroll values strictly from their assigned **Work Entries**.

This ensures:
- Worked days, wages, and totals reflect only the relevant location
- Accurate per-location costing
- Clean separation for downstream invoicing

---

### 5. Controlled Invoice Selection Logic

When the invoicing wizard is launched from selected payslips:

- Only the explicitly selected payslips are processed
- No automatic expansion of the selection is performed
- All validation rules still apply (state, invoice status, invoiceable flag)

This guarantees **“what you select is what gets invoiced”**, preventing accidental overbilling.

---

## Typical Use Case

1. Payroll is generated and validated as usual
2. Payslips with multiple work locations are split using **Split by Location**
3. Eligible payslips are selected
4. The **Payslip to Invoice** wizard is launched
5. An invoice is generated per customer, accurately reflecting payroll cost by location and/or employee

---

## Technical Notes

- Compatible with Odoo HR Payroll and Accounting
- Does not modify core payroll rules
- Designed to be additive and safe for existing payroll processes
- Fully traceable links between payslips and invoices

---

## Status

This module is production-ready and actively used for customer payroll billing workflows.
