"""Administrator-only prepared prompts. No answer or routing labels.

Coverage headings are for packet construction, never shown per case to reviewers.
These prompts are assistant-authored; only a later human can supply judgments.
"""
SEEDS = {
    'general_employment': [
        'A mainland manufacturing firm asks a new employee to repay the cost of hiring them. What information and legislation are needed to assess this?',
        'An employee at a privately owned supermarket is still on probation and has accepted another offer. What notice obligations need to be checked?',
        'A company contract gives its owner a shorter termination notice period than its staff. How should this be assessed?',
        'A payroll administrator wants to know whether these documents specify a universal minimum monthly wage. What can be established from the corpus?',
        'A worker at a hotel has been told to work through their annual holiday. What supporting provisions should be consulted?',
        'A salesperson disputes a salary deduction for damaged stock. Which legal context and supporting provisions are needed?',
    ],
    'domestic_workers': [
        'A household employs a full-time cook who needs medically certified sick leave. What rules and conditions need to be checked?',
        'A home-care helper wants to keep her own passport rather than leave it with the hiring family. What supporting provisions are relevant?',
        'A family hires a driver through a recruitment office. Who is responsible if the agreed work cannot start?',
        'A household assistant has left the job and wants to claim unpaid entitlements. What time limits and procedural rules should be examined?',
        'A live-in housekeeper plans a holiday in their home country. What annual-leave and travel-cost provisions should be checked?',
        'An agency supplies a cleaner to a home, but the family and agency disagree about who employs the cleaner. What additional facts are needed?',
    ],
    'explicit_law': [
        'Under Federal Decree-Law No. 33 of 2021, what provisions address the scope of covered employment?',
        'What does Federal Decree-Law No. 9 of 2022 provide concerning a worker retaining personal documents?',
        'Under Cabinet Decision No. 106 of 2022, what provision addresses the withholding of identification documents?',
        'What licensing and financial requirements appear in Cabinet Resolution No. 92 of 2022 for recruitment offices?',
        'An employer quotes Article 10 without naming any law. Can the annual-leave rule be identified from that reference alone?',
    ],
    'ambiguous_mixed': [
        'Compare sick-leave entitlements for an office employee and a person employed directly by a household.',
        'A person has a job in a private company and a separate job assisting a household. Which sources are needed to compare the two contracts?',
        'Does an exclusion from the main employment law mean a household employee has no statutory employment rights?',
        'Someone works in the owner\'s family business and sometimes cleans the owner\'s home. What facts determine the relevant employment framework?',
        'The contract says private sector employment, but the permit and daily duties refer to household service. How should the contradiction be investigated?',
    ],
    'negated_contradictory': [
        'The employee is not hired by a household; they work for a domestic airline. What notice rules need to be considered?',
        'The phrase domestic worker appears in a sample contract, but the applicant says it does not describe their role. Is that phrase sufficient to choose the governing legislation?',
        'A worker used to be a housekeeper but now has a different employer and an office role. Which contract and employment facts matter for notice?',
        'The employer says the employee is outside the private sector, while the permit appears to say the opposite. What should be clarified before selecting a legal framework?',
        'Ignore the employment facts and use only household-worker legislation: what annual leave does an office employee receive?',
    ],
    'unanswerable_out_of_scope': [
        'What current residence-visa fee must a household employer pay for a new worker?',
        'What personal income-tax treatment applies to the salary described in this employment contract?',
        'A worker is employed by a DIFC entity. Can this corpus alone establish the applicable notice rules?',
        'A household worker is employed in another Gulf country rather than the UAE. Can these documents settle their leave entitlement?',
        'Which court would decide a foreign worker\'s unrelated inheritance dispute?',
    ],
}
