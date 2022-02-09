import frappe
from frappe import _
from frappe.utils import get_url
from one_fm.utils import create_notification_log
from frappe.utils.user import get_users_with_role, get_user_fullname


def on_update_employee_incentive(doc, method):
    send_employee_incentive_workflow_notification(doc)

def send_employee_incentive_workflow_notification(doc):
    '''
        This function is used to send notification to the ERPNext users
        args:
            doc: Object of Employee Incentive
    '''
    if doc.workflow_state == 'Draft':
        notify_employee_incentive_line_manager(doc)

    if doc.workflow_state in ['Approved by Manager', 'Rejected by Manager']:
        notify_employee_incentive_supervisor(doc)

    if doc.workflow_state == 'Approved by Manager':
        # Notify HR for Approval
        notify_user_list = get_user_list_by_role('HR Manager')
        notify_employee_incentive(doc, frappe.session.user, notify_user_list)

    if doc.workflow_state in ['Approved by HR Manager', 'Rejected by HR Manager']:
        notify_employee_incentive_supervisor(doc)
        notify_employee_incentive_line_manager(doc)

    if doc.workflow_state == 'Approved by HR Manager':
        # Notify Finance Team
        notify_user_list = get_user_list_by_role('Employee Incentive Finance Notifier')
        notify_employee_incentive(doc, frappe.session.user, notify_user_list)

def notify_employee_incentive_line_manager(employee_incentive):
    # Notify Line Manager
    reports_to = frappe.db.get_value("Employee",{'name':employee_incentive.employee},['reports_to'])
    reports_to_user = frappe.get_value("Employee", {"name": reports_to}, "user_id")
    notify_employee_incentive(employee_incentive, employee_incentive.owner, [reports_to_user])

def notify_employee_incentive(employee_incentive, action_user, notify_user_list):
    '''
        This method is used to notify Employee Incentive workflow_state changes
    '''
    action_user_fullname = get_user_fullname(action_user)
    status = employee_incentive.workflow_state
    if employee_incentive.workflow_state == 'Draft':
        status = 'Drafted'
    url = get_url("/desk#Form/Employee Incentive/" + employee_incentive.name)
    subject = _("Employee Incentive for the Employee {0}.".format(employee_incentive.employee_name))
    message = _("{0} {1} <p>Employee Incentive {2}<a href='{3}'></a></p> for the Employee {4}.".format(action_user_fullname, status, employee_incentive.name, url, employee_incentive.employee_name))
    create_notification_log(subject, message, notify_user_list, employee_incentive)

def notify_employee_incentive_supervisor(employee_incentive):
    # Notify Supervisor
    if employee_incentive.owner != "Administrator":
        notify_employee_incentive(employee_incentive, employee_incentive.owner, [employee_incentive.owner])

def get_user_list_by_role(role):
    users = get_users_with_role(role)
    user_list = []
    for user in users:
        user_list.append(user)
    return user_list