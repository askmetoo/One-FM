import frappe


def set_justification_needed_on_deduction_in_salary_slip(doc, method):
    '''
        Function to set Justification Needed on Deduction if it exceeds the Limit
        It will trigger on validate of Salary Slip from hooks
    '''
    doc.justification_needed_on_deduction = False
    if doc.deductions and doc.total_deduction:
        maximum_deduction_percentage = frappe.db.get_single_value('HR and Payroll Additional Settings', 'maximum_salary_deduction_percentage')
        work_permit_salary = 0
        total_deduction = doc.total_deduction
        if maximum_deduction_percentage > 0:
            work_permit_salary = frappe.db.get_value('Employee', doc.employee, 'work_permit_salary')
            if work_permit_salary > 0:
                allowed_deduction = work_permit_salary * maximum_deduction_percentage * 0.01
                exclude_salary_component = frappe.db.get_single_value('HR and Payroll Additional Settings', 'exclude_salary_component')
                if exclude_salary_component:
                    total_deduction = 0
                    for deduction in doc.deductions:
                        if deduction.salary_component != exclude_salary_component:
                            total_deduction += deduction.amount
                if total_deduction > allowed_deduction:
                    doc.justification_needed_on_deduction = True
    update_payroll_entry_details(doc)

def update_payroll_entry_details(salary_slip):
    '''
        Function used to update payroll entry details
        args: Salary Slip Object
        Update the Payroll Entry Details
            by cross checking the employee id in the Payroll Entry Child and Salary Slip
    '''
    if salary_slip.payroll_entry:
        query = """
            update
                `tabPayroll Employee Detail`
            set
                justification_needed_on_deduction = %(justification_needed_on_deduction)s,
                payment_amount = %(payment_amount)s
            where
				parenttype = 'Payroll Entry' and parent = %(payroll_entry)s
				and employee = %(employee)s
        """
        return frappe.db.sql(query,
			{
				'justification_needed_on_deduction': salary_slip.justification_needed_on_deduction,
                'payment_amount': salary_slip.net_pay,
				'payroll_entry': salary_slip.payroll_entry,
				'employee': salary_slip.employee
			}
		)
