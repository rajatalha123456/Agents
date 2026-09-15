import re

def detect_hardship(text='', declared_category=None):
    if declared_category:
        return {'hardship_status':'DECLARED','category':declared_category,'source':'member_declared_form','evidence':None,'confidence':None}
    # Conservative text signals are not declared facts or calibrated confidence estimates.
    normalized = text.lower()
    if re.search(r'\b(no|not|never|without|resolved|used to)\b',normalized):
        return {'hardship_status':'UNKNOWN','category':None,'source':'text_requires_review','evidence':None,'confidence':None}
    patterns = [('temporary_income_disruption',r'(?:my )?(?:salary|income|wages?) (?:has been |is |was )?(?:delayed|stopped|reduced)'),
                ('payment_difficulty',r'(?:cannot|can.t|unable to) (?:manage|afford|pay)')]
    for category,pattern in patterns:
        match = re.search(pattern,normalized)
        if match:
            return {'hardship_status':'INFERRED_SIGNAL','category':category,'source':'member_text','evidence':match.group(),'confidence':None}
    return {'hardship_status':'UNKNOWN','category':None,'source':'unknown','evidence':None,'confidence':None}

def evaluate_policy(policies, hardship, days_past_due):
    if hardship['hardship_status'] != 'DECLARED' or days_past_due is None:
        return []
    return [{'policy_id':p['policy_id'],'name':p['name'],
             'requires_human_approval':p['requires_human_approval'],
             'status':'PENDING_HUMAN_APPROVAL' if p['requires_human_approval'] else 'ELIGIBLE',
             'action_executed':False}
            for p in policies if p['active'] and hardship['category'] in p['hardship_categories'] and 0 <= days_past_due <= p['max_days_past_due']]
