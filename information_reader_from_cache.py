from data_cache import cache, refresh_conversation_log_if_needed

def get_employee_info():
    return cache["employee_info"]

def get_partner_info():
    return cache["partner_info"]

def get_company_info():
    return cache["company_info"]

def get_conversation_log():
    refresh_conversation_log_if_needed()
    return cache["conversation_log"]

def get_aiko_experience_log():
    return cache["aiko_experience_log"]

def get_task_info():
    return cache["task_info"]

def get_attendance_info():
    return cache["attendance_info"]
