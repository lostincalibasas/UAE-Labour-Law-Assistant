"""Generates eval_set.json (kept so the set is reproducible/editable as code)."""
import json

L33 = "Federal Decree-Law No. 33 of 2021"
L9 = "Federal Decree-Law No. 9 of 2022"
C106 = "Cabinet Decision No. 106 of 2022"
C92 = "Cabinet Resolution No. 92 of 2022"

def A(doc, art):
    return {"source_document": doc, "article": f"Article {art}"}

def F(fact, doc=None, art=None, quote=None):
    f = {"fact": fact}
    if quote:
        f.update({"source_document": doc, "article": f"Article {art}", "quote": quote})
    return f

QS = []
def Q(cat, question, expected, facts, avoid=(), not_cite=(), note="", answerable=True):
    QS.append({
        "id": f"Q{len(QS)+1:03d}", "category": cat, "question": question,
        "answerable": answerable, "expected_articles": expected,
        "must_include": facts, "must_not_include": list(avoid),
        "must_not_cite": list(not_cite), "notes": note,
        "provenance": {"drafted_by": "LLM (Claude)", "reviewed_by": None, "review_status": "unreviewed"},
    })

# ---------------- Probation / notice (private sector, L33) ----------------
Q("scenario", "I am on probation and want to join another company in the UAE. How much notice should I give?",
  [A(L33, 9)],
  [F("The worker must notify the original employer in writing at least one month from the date of the wish to terminate.", L33, 9,
     "he shall notify the original employer of the same in writing within not less than one month from the date of his wish to terminate the contract"),
   F("The new employer compensates the original employer for recruitment/contracting costs, unless otherwise agreed.", L33, 9,
     "the new employer shall compensate the original employer for the costs of recruitment or contracting with the worker, unless otherwise agreed upon")],
  avoid=["States 14 days as the notice for moving to another UAE employer", "States 30/60/90 days notice under Article 43 as the probation rule"],
  note="Core example from the user. 14 days applies to leaving the State (Art 9(4)) and to employer termination (Art 9(1)), not to moving to another UAE employer.")
Q("single_fact", "What is the maximum probation period for a private sector employee?", [A(L33, 9)],
  [F("Probation may not exceed six months from the date work commences.", L33, 9,
     "not exceeding (6) six months from the date of commencement of work")])
Q("single_fact", "Can my employer put me on probation a second time with the same company?", [A(L33, 9)],
  [F("A worker may not be placed on probation more than once at the same employer.", L33, 9,
     "It is not permissible to appoint a worker under probationary period more than once at one employer")])
Q("single_fact", "How much notice must an employer give to end a worker's employment during probation?", [A(L33, 9)],
  [F("The employer must give written notice at least 14 days before the termination date.", L33, 9,
     "after notifying the latter of the same in writing fourteen (14) days at least before the date specified for the termination of service")])
Q("scenario", "I'm a foreign worker on probation and want to leave the UAE altogether. What notice do I give and what are the risks?",
  [A(L33, 9)],
  [F("The foreign worker must notify the employer in writing at least 14 days before the termination date.", L33, 9,
     "he shall notify the employer of the same in writing not less than fourteen (14) days from the date specified for the termination of the contract"),
   F("If the worker returns within three months and obtains a new permit, the new employer pays the compensation, unless the worker and original employer agree otherwise.", L33, 9,
     "If he wishes to return to the State and obtain a new work permit within (3) three months from the date of departure, the new employer shall pay the compensation"),
   F("Leaving the State without following the Article causes a one-year work permit ban.", L33, 9,
     "he shall not be granted a work permit to work in the State for one year from the date of leaving the State")],
  note="Article 9(7): the Ministry may exclude some job categories from the ban. A complete answer may mention it.")
Q("single_fact", "What happens if either party ends the contract during probation without following the probation rules?", [A(L33, 9)],
  [F("The breaching party pays the other compensation equal to the worker's wages for the notice period or the remaining part of it.", L33, 9,
     "it shall pay to the other party compensation equal to the worker's wages for the notice period or the remaining period of the notice period")])
Q("scenario", "I have passed probation and want to resign. How much notice do I have to give?", [A(L33, 43)],
  [F("Notice period agreed in the contract must be not less than 30 days and not more than 90 days.", L33, 43,
     "provided that such period is not less than ( 30) thirty days and not more than ( 90) ninety days"),
   F("Notice must be given in writing.", L33, 43, "provided that the other party is notified in writing")],
  avoid=["Says the notice is 14 days or one month as the general resignation rule (those are probation figures)"],
  note="Contrast with Q001: tests probation vs post-probation confusion.")
Q("single_fact", "What do I owe if I leave without serving my notice period?", [A(L33, 43)],
  [F("The party that did not abide by the notice pays notice period allowance equal to the worker's wage for the full or remaining notice period, even if no damage resulted.", L33, 43,
     "the compensation shall be equal to the worker's wage for the full notice period or the remaining part thereof")])
Q("single_fact", "If my employer terminates me, can I take time off during the notice period to look for a job?", [A(L33, 43)],
  [F("The worker may be absent one working day per week without pay during the notice period to search for another job.", L33, 43,
     "the worker shall have the right to be absent during the notice period for one working day without pay per week, in order to search for another job"),
   F("The worker must notify the employer at least three days before the absence day.", L33, 43,
     "he notifies the employer of the same (3) three days at least before the absence day")])
Q("single_fact", "Can an employment contract set a shorter notice period for the employer than for the worker?", [A(L33, 43)],
  [F("The notice period must be the same for both parties unless a different arrangement serves the worker's interests.", L33, 43,
     "provided that the notice period is the same for both parties unless it serves the interests of the worker")])
Q("scenario", "I resign while I'm on annual leave. When does my notice period start counting?", [A(L33, 35)],
  [F("The notice period starts only from the day after the day scheduled for the worker's return from leave, unless both parties agree otherwise.", L33, 35,
     "the validity of the notice period agreed upon in the employment contract shall not begin, except from the day following the day scheduled for the worker's return from the leave")])
Q("single_fact", "If I leave my job without a legitimate reason before my contract ends, can I get a new work permit?", [A(L33, 50)],
  [F("A foreign worker who leaves work for an illegitimate reason before contract end cannot get another work permit for one year from the date of absence.", L33, 50,
     "he shall not be granted another work permit to join another job in the State in accordance with the provisions hereof, for a period of one year from the date of the absence from work"),
   F("The Ministry may exclude some job categories, skill levels or workers from this ban.", L33, 50,
     "The Ministry may exclude some job categories, skill levels or workers from the provision of Clause (1) of this Article")])

# ---------------- Leave & hours (L33) ----------------
Q("numeric", "How many days of annual leave does a private sector employee get?", [A(L33, 29)],
  [F("At least 30 days with full wage for each year of service.", L33, 29, "Thirty days for each year of extended service"),
   F("Two days per month if service is more than six months and less than a year.", L33, 29,
     "Two days for each month if his service term is more than six months and less than a year")])
Q("numeric", "How much paid sick leave does a private sector worker get, and does it apply during probation?", [A(L33, 31)],
  [F("No paid sick leave during probation (unpaid leave may be granted on a medical report).", L33, 31,
     "The worker shall not be entitled to a paid sick leave during the probationary period"),
   F("After probation, up to 90 days per year: first 15 days full pay, next 30 days half pay, remainder unpaid.", L33, 31,
     "not more than (90) ninety continuous or intermittent days per year"),
   F("First 15 days at full pay.", L33, 31, "The first (15) fifteen days with full pay"),
   F("Following 30 days at half pay.", L33, 31, "The following (30) thirty days with half pay")])
Q("numeric", "What is the maternity leave entitlement in the private sector?", [A(L33, 30)],
  [F("Sixty days of maternity leave.", L33, 30, "maternity leave of (60) sixty days"),
   F("First 45 days at full wage, following 15 days at half wage.", L33, 30, "The first (45) forty-five days with full wage")])
Q("single_fact", "Can my employer fire me because I'm pregnant or on maternity leave?", [A(L33, 30)],
  [F("Terminating or giving notice of termination because of pregnancy, maternity leave or related absence is not permitted.", L33, 30,
     "It is not permissible to terminate the service of the female worker or notify her of the same because of the pregnancy, having a maternity leave or her absence from work")])
Q("numeric", "How many days of leave do I get when a close family member dies?", [A(L33, 32)],
  [F("Five days for death of a spouse; three days for death of mother, father, son, brother, sister, grandson, grandfather or grandmother.", L33, 32,
     "A bereavement leave of (5) five days, in case of death of the husband or wife and (3) three days in case of death of the mother, father, son, brother, sister, grandson, grandfather or grandmother")])
Q("numeric", "Is there paid parental leave for a new father or mother in the private sector?", [A(L33, 32)],
  [F("Five working days, continuous or intermittent, within six months of the child's birth.", L33, 32,
     "A parental leave for a period of ( 5) five working days")])
Q("numeric", "What are the maximum normal working hours in the private sector?", [A(L33, 17)],
  [F("Eight hours per day or 48 hours per week.", L33, 17,
     "The maximum normal working hours for workers shall be (8) eight hours per day or (48) forty-eight hours per week")])
Q("numeric", "How is overtime paid, including at night, and what is the daily limit?", [A(L33, 19)],
  [F("Overtime may not exceed two hours per day, generally.", L33, 19, "provided that they do not exceed two hours per day"),
   F("Overtime is paid at basic wage plus an increase of not less than 25%.", L33, 19, "an increase of not less than ( 25 %) twenty five percent of that wage"),
   F("Overtime between 10 pm and 4 am carries an increase of not less than 50% (shift workers excluded).", L33, 19,
     "an increase of not less than ( %50) fifty percent of that wage")])
Q("numeric", "What do I get if my employer makes me work on a public holiday?", [A(L33, 28)],
  [F("Another day off for each holiday worked, or that day's wage plus an increase of not less than 50% of the basic wage.", L33, 28,
     "plus an increase of not less than (%50) fifty percent of the basic wage for that day")])
Q("single_fact", "Am I entitled to study leave for my university exams?", [A(L33, 32)],
  [F("Up to ten working days per year for exams, if enrolled at an approved institution and with at least two years' service at the employer.", L33, 32,
     "a period of ( 10) ten working days per year"),
   F("Minimum two years of service with the employer.", L33, 32, "provided that the service term at the employer is not less than two years")])

# ---------------- Contract, wages, discipline, termination (L33) ----------------
Q("numeric", "How is end of service gratuity calculated for a full-time foreign worker, and is there a cap?", [A(L33, 51)],
  [F("Requires at least one year of continuous service.", L33, 51, "who completed a year or more in continuous service"),
   F("21 days' basic wage for each year of the first five years.", L33, 51, "A wage of (21) twenty one days for each year of the first five years of service"),
   F("30 days' basic wage for each year beyond five years.", L33, 51, "A wage of (30) thirty days for each year exceeding such period"),
   F("Total may not exceed two years' wage.", L33, 51,
     "the end of service benefits for the foreign worker in its entirety does not exceed two years' wage")])
Q("single_fact", "How long does an employer have to pay my final dues after my contract ends?", [A(L33, 53)],
  [F("Within 14 days from the end date of the contract term.", L33, 53, "within ( 14) fourteen days from the end date of the contract term")],
  not_cite=[A(L9, 19)], note="Domestic workers have a different period (10 days, Decree-Law 9 Art 19(9)).")
Q("numeric", "What is the maximum my employer can deduct from my salary in total?", [A(L33, 25)],
  [F("Total deductions/withholdings may not exceed 50% of the wage in any case.", L33, 25,
     "the percentage of deduction and/or withholding may not exceed (%50) fifty percent of the wage")],
  avoid=["States one quarter as the overall cap for a private sector worker"],
  not_cite=[A(L9, 16)], note="One quarter applies to domestic workers (Decree-Law 9 Art 16).")
Q("single_fact", "Can my employer hold my passport?", [A(L33, 13)],
  [F("The employer must not withhold the worker's official documents.", L33, 13,
     "Not withholding the official documents of the worker or forcing him to leave the State at the end of the employment relationship")],
  not_cite=[A(L9, 11)], note="Private sector worker. Domestic variant is a separate question.")
Q("single_fact", "Can my private sector employer charge me recruitment fees?", [A(L33, 6)],
  [F("The employer may not charge the worker recruitment and employment fees and costs, directly or indirectly.", L33, 6,
     "The employer is prohibited from charging the worker for the fees and costs of recruitment and employment or collecting them from him, whether directly or indirectly")])
Q("single_fact", "Can my employer refuse to give me an experience certificate when I leave?", [A(L33, 13)],
  [F("On request at contract expiry the employer must give an experience certificate without fees.", L33, 13,
     "a certificate of experience, without fees")])
Q("single_fact", "How long do I have to move out of company accommodation after my employment ends?", [A(L33, 16)],
  [F("Within 30 days from the end of service, unless the employer approves a longer stay (at worker's cost or as agreed).", L33, 16,
     "Evacuating the accommodation provided by the employer, within a period not exceeding (30) thirty days from the date of end of his service")])
Q("scenario", "Under what circumstances can my employer dismiss me without notice for being absent?", [A(L33, 44)],
  [F("Absence without legitimate reason for more than 20 intermittent days in a year or more than 7 consecutive days.", L33, 44,
     "for more than ( 20) twenty intermittent days during one year or more than ( 7) seven consecutive days"),
   F("Dismissal requires a prior written investigation and a written, justified decision handed to the worker.", L33, 44,
     "after conducting a written investigation with him and the dismissal decision shall be in writing and justified")],
  not_cite=[A(L9, 19)], note="Domestic workers: 10 consecutive / 15 intermittent days (Decree-Law 9 Art 19(7)).")
Q("scenario", "My employer assaulted me at work. Can I quit without notice and keep my end of service rights?", [A(L33, 45)],
  [F("Worker may quit without notice and retain end-of-service rights if the employer or legal representative assaulted, used violence or harassed the worker at work.", L33, 45,
     "the employer or its legal representative assaulted the worker, committed violence or harassment against him at work"),
   F("The worker must inform the competent authorities and the Ministry within five working days from when he was able to report.", L33, 45,
     "provided that he informs the competent authorities and the Ministry within (5) five working days from the date on which he was able to report")],
  not_cite=[A(C106, 10)], note="Private sector (5 working days). Domestic variant (3 days) is separate.")
Q("numeric", "How much compensation can I get if I am unlawfully terminated for filing a complaint?", [A(L33, 47)],
  [F("Termination because of a proven serious complaint to the Ministry or lawsuit against the employer is unlawful.", L33, 47,
     "due to filing a serious complaint to the Ministry or filing a lawsuit against the employer, whose validity is proven"),
   F("Court-estimated fair compensation, capped at three months' wage based on the last wage.", L33, 47,
     "the amount of compensation does not exceed the worker's wage for a period of (3) three months")])
Q("single_fact", "Can my employer terminate me for health reasons while I still have leave balance?", [A(L33, 46)],
  [F("The employer may not terminate for lack of health fitness before the worker uses legally accrued leaves; contrary agreements are void.", L33, 46,
     "The employer may not terminate the worker's service due to his lack of health fitness before using the legally accrued leaves")])
Q("single_fact", "How long can a non-compete clause last in my contract?", [A(L33, 10)],
  [F("Not more than two years from contract expiry, limited in time, place and type of work to protect legitimate business interests.", L33, 10,
     "The non-competition period shall not be more than two years from the expiry date of the contract"),
   F("The clause is void if the employer terminates the contract in violation of the Decree-Law.", L33, 10,
     "This requirement shall be nullified if the employer terminates the employment contract in violation of the provisions hereof")])
Q("single_fact", "Can an employment contract waive my statutory rights?", [A(L33, 65)],
  [F("Provisions contradicting the Decree-Law are null and void unless more beneficial to the worker; waivers of rights that violate it are void.", L33, 65,
     "Each discharge, reconciliation or waiver of the rights arising for the worker hereunder shall be null and void if it violates its provisions")])
Q("scenario", "Can a 16-year-old work in a private company, and under what conditions?", [A(L33, 5)],
  [F("Juveniles (15 to under 18) may be employed with the guardian's written consent and a medical fitness certificate.", L33, 5,
     "Written consent of the juvenile's guardian or custodian"),
   F("Actual working hours may not exceed six hours per day.", L33, 5, "The actual working hours shall not exceed six hours per day"),
   F("No work between 7 pm and 7 am.", L33, 5, "The juvenile shall not work between 7 pm and 7 am")],
  avoid=["States 18 as the minimum age for private sector employment"], not_cite=[A(L9, 4)],
  note="Domestic workers have a stricter minimum age of 18.")

# ---------------- Disputes and limitation (L33 vs L9) ----------------
Q("numeric", "How long do I have to file a labour claim against my private sector employer?", [A(L33, 54)],
  [F("A lawsuit cannot be heard after one year from the maturity date of the right.", L33, 54,
     "After one (1) year from the maturity date of the right subject to a lawsuit, the lawsuit cannot be heard")],
  avoid=["States three months as the limitation period for a private sector worker"], not_cite=[A(L9, 26)],
  note="Three months from termination is the DOMESTIC worker rule (Decree-Law 9 Art 26(2)). Article 54 was amended by Decree-Law 20 of 2023; the provided PDF text already reflects the amendment.")
Q("numeric", "Up to what claim value can MoHRE decide a labour dispute finally?", [A(L33, 54)],
  [F("The Ministry issues a final decision if the claim is not more than AED 50,000, or if neither party complies with an amicable settlement decision regardless of value.", L33, 54,
     "if the value of the claim is not more than fifty thousand (50,000) UAE dirhams (AED)")])
Q("single_fact", "Do workers pay court fees for labour claims?", [A(L33, 55)],
  [F("Labour claims are exempt from judicial fees; worker/heir requests are exempt up to AED 100,000.", L33, 55,
     "Labour claims shall be exempted from judicial fees at all stages of litigation and execution")])
Q("scenario", "What is the fine for an employer in the private sector who employs a worker with no work permit?", [A(L33, 60)],
  [F("Fine of AED 50,000 to AED 200,000.", L33, 60, "A fine of not less than (AED 50,000) fifty thousand UAE Dirham and not more than (AED 200,000) two hundred thousand UAE Dirham"),
   F("Employing a worker who is not permitted to work for the employer is listed among the violations.", L33, 60,
     "Employing a worker who is not permitted to work for him")])
Q("scope", "Does the main labour law apply to domestic workers?", [A(L33, 3)],
  [F("No. Domestic workers are excluded from the Decree-Law's scope.", L33, 3, "Domestic workers"),
   F("Government employees and armed forces/police/security employees are also excluded.", L33, 3,
     "Employees of the armed forces, police and security")])

# ---------------- Domestic workers (L9 / C106 / C92) ----------------
Q("cross_law", "What is the maximum probation period for a domestic worker?", [A(L9, 8)],
  [F("Not more than six months from the date of employment.", L9, 8, "for a period of not more than (6) six months from the date of employment")],
  not_cite=[A(L33, 9)])
Q("cross_law", "How long can a domestic worker's fixed-term employment contract be?", [A(L9, 7)],
  [F("A limited contract lasts two years and may be renewed for a similar period.", L9, 7,
     "The duration of a limited employment contract is two years and may be renewed for a similar period")])
Q("cross_law", "How many days of paid sick leave does a domestic worker get per year?", [A(L9, 10)],
  [F("30 days per year of service, continuous or intermittent, on a medical report from an approved authority.", L9, 10,
     "Domestic workers are entitled to a sick leave of 30 days for each year of service"),
   F("First 15 days paid in full, next 15 days at half pay.", L9, 10, "The first fifteen days are paid in full"),
   F("No payment if the worker's behaviour contributed to the illness.", L9, 10,
     "If the domestic worker's behavior contributed to the illness, no payment will be made during sick leave")],
  avoid=["States 90 days of sick leave (private sector figure)"], not_cite=[A(L33, 31)])
Q("cross_law", "How much annual leave does a domestic worker get and who pays for the flight home?", [A(L9, 10)],
  [F("Not less than 30 days per year of service, paid in full before departure.", L9, 10,
     "an annual leave of not less than 30 days for each year of service"),
   F("Employer pays the return ticket once every two years if the worker spends leave in the home country.", L9, 10,
     "the employer must incur the cost of the return ticket once every two years")])
Q("cross_law", "How quickly must a domestic worker's salary be paid?", [A(L9, 15)],
  [F("Monthly salaries are paid in UAE dirhams within 10 days from the maturity date.", L9, 15,
     "Monthly salaries are to be paid in UAE dirhams within a period not exceeding 10 days from its maturity date")])
Q("cross_law", "What is the minimum age to hire a domestic worker?", [A(L9, 4)],
  [F("Recruiting or hiring a domestic worker under 18 is prohibited.", L9, 4, "Recruiting or hiring a domestic worker under the age of 18 is prohibited")],
  avoid=["States 15 as the minimum age"], not_cite=[A(L33, 5)])
Q("cross_law", "What is the maximum deduction from a domestic worker's pay for damage to the employer's property?", [A(L9, 16)],
  [F("Deduction cannot exceed one quarter of the domestic worker's salary, with worker's consent or Ministry approval.", L9, 16,
     "the deduction cannot exceed one quarter of the domestic worker's salary")],
  avoid=["States five days' wage per month or 50% (private sector rules)"], not_cite=[A(L33, 25)])
Q("cross_law", "Can an employer keep a domestic worker's passport, and is there a fine?", [A(L9, 11), A(C106, 20)],
  [F("The domestic worker should be allowed to retain all official documents.", L9, 11, "The domestic worker should be allowed to retain all official documents"),
   F("Administrative fine of AED 500 per domestic worker for withholding identification documents.", C106, 20,
     "Withholding the domestic worker's identification documents 500 dirhams for each domestic worker")],
  note="Fine is in Schedule 2, which the current chunker folds into 'Article 20'.")
Q("cross_law", "How long after a domestic worker's contract ends must the employer pay the final compensation?", [A(L9, 19)],
  [F("Within 10 days from the contract expiry date, depending on circumstances and the Implementing Regulation.", L9, 19,
     "the employer shall pay the domestic worker's compensation within (10) ten days from the contract expiry date")],
  not_cite=[A(L33, 53)], note="Private sector is 14 days.")
Q("unanswerable_partial", "How many days of end of service gratuity does a domestic worker get per year of service?", [A(L9, 22)],
  [F("States that the provided text does not give the amount; the UAE Cabinet is to adopt calculation and payment rules.", L9, 22,
     "the UAE Cabinet shall adopt the rules and regulations for calculation and payment of end of service gratuity for domestic workers")],
  avoid=["States 21 days or 30 days per year (private sector figures)"], not_cite=[A(L33, 51)],
  note="Tests whether the system invents a figure instead of saying the documents don't specify one.")
Q("scenario", "A domestic worker's employer assaulted her. Can she leave immediately, and what must she do?", [A(C106, 10)],
  [F("She may leave work without notice.", C106, 10, "he / she has the right to leave work without notice"),
   F("She must immediately report to the competent authorities and notify the Ministry within three days of leaving the workplace.", C106, 10,
     "notify the Ministry within three days of leaving the workplace"),
   F("She must return to the recruitment office for housing and give her contact details.", C106, 10,
     "return to the recruitment office that recruited him/her for housing")],
  not_cite=[A(L33, 45)], note="Private sector rule is 5 working days (Art 45(2)).")
Q("single_fact", "When can a domestic worker leave the job and keep her rights because of employer breach?", [A(C106, 10)],
  [F("If salary is reduced below contract or the employer fails contractual obligations, provided the Ministry is informed within two weeks.", C106, 10,
     "provided that they inform the Ministry within two weeks of the occurrence")])
Q("single_fact", "How soon must an employer report that a domestic worker has abandoned work?", [A(L9, 18)],
  [F("Within five days.", L9, 18, "Employers must notify the Ministry within five days if a domestic worker abandons work"),
   F("A worker leaving without the employer's knowledge must inform the Ministry within two days.", L9, 18,
     "A domestic worker must inform the Ministry within two days of leaving work without the employer's knowledge")])
Q("numeric", "How many hours of rest must a domestic worker get per day?", [A(C106, 7), A(L9, 9)],
  [F("At least 12 hours of rest per day.", C106, 7, "provided that the worker has at least 12 hours of rest per day"),
   F("Time spent eating or resting does not count as actual working hours.", C106, 7,
     "time spent eating or resting by the domestic worker shall not count toward actual working hours")])
Q("single_fact", "What if my domestic worker has to work on her weekly rest day?", [A(C106, 8), A(L9, 9)],
  [F("She must get an alternative day off or be paid cash in lieu.", C106, 8,
     "the employee must be granted an alternative day off for rest or be paid cash in lieu of that day"),
   F("She may not be required to work more than two consecutive rest days in any two weeks unless otherwise agreed.", C106, 8,
     "may not be required to work for more than two consecutive days of rest in any two weeks")])
Q("single_fact", "Can a domestic worker do extra work for my relatives?", [A(C106, 11)],
  [F("Yes, with the worker's consent, for the employer's relatives up to the second degree.", C106, 11,
     "a domestic worker may work for any of the employer's relatives up to the second degree"),
   F("Otherwise no work for parties other than the employer or named beneficiary unless the Ministry specifies.", C106, 11,
     "Domestic workers may not work for any party other than their employers or the beneficiary named in their employment contract")])
Q("scenario", "A domestic worker recruited by name wants to move to a new employer during her first contract. Who pays what?", [A(C106, 6), A(L9, 21)],
  [F("The new employer pays part of the amount the original employer paid the recruitment office, calculated with the Article 6(2) formula.", C106, 6,
     "the new employer is required to pay part of the amount paid by the original employer to the recruitment office"),
   F("The new employer also pays the original employer's government fees, unless otherwise agreed.", C106, 6,
     "the new employer will be responsible for paying the government fees incurred by the original employer for the recruitment and employment of the domestic worker, unless otherwise agreed by both parties"),
   F("Domestic workers may transfer if contractual requirements are met, observing the original employer's rights.", L9, 21,
     "Domestic workers are permitted to transfer to new employers provided that all contractual requirements are met")])
Q("numeric", "How is the recruitment fee refund calculated when a domestic worker leaves early?", [A(C106, 6)],
  [F("Refund = (total recruitment cost / contract duration in months) x remaining months.", C106, 6,
     "( total cost of recruitment ÷ duration of the domestic worker's employment contract in months) x term remaining on the employment contract"),
   F("Full refund if the case occurs in the first month or the worker is medically unfit during probation.", C106, 6,
     "the recruitment office must refund the employer's recruitment fees in full"),
   F("Refund must be paid within two weeks.", C106, 6, "the office is required to refund the amounts listed in this article to the employer within two weeks")])
Q("single_fact", "Does the recruitment office have to refund me if I hired the domestic worker directly by name?", [A(C106, 6)],
  [F("No. If recruited directly, the office is exempt from the refund obligation in all cases in Article 6.", C106, 6,
     "If the domestic worker was recruited directly, the recruitment office is exempt from the obligation to refund the specified amount in all cases outlined in this article")])
Q("scenario", "My domestic worker was incompetent during her probation. Can I get my recruitment fees back?", [A(C106, 6), A(L9, 8)],
  [F("Offices must refund all or part of the fees if the worker shows incompetence and poor conduct during probation.", C106, 6,
     "If the domestic worker demonstrates incompetence and poor conduct during the probationary period"),
   F("Probation can last up to six months.", L9, 8, "for a period of not more than (6) six months from the date of employment")])
Q("numeric", "What bank guarantee does a domestic worker recruitment agency need?", [A(C106, 3), A(C92, 2)],
  [F("A bank guarantee of not less than AED 500,000 during the licence term.", C106, 3,
     "Legal persons and sole proprietorships are required to provide a bank guarantee of not less than AED 500,000"),
   F("A shortfall must be topped up within 30 days.", C106, 3, "complete the guarantee amount within 30 days of the shortage occurring")],
  note="C92 Art 2(1) states the same AED 500,000 requirement; both are accepted as relevant.")
Q("single_fact", "Can a recruitment agency charge the domestic worker a commission for finding the job?", [A(L9, 5), A(C106, 4)],
  [F("No. The agency may not demand or accept any commission or charge expenses, directly or indirectly.", L9, 5,
     "It is prohibited for the Agency to demand or accept, directly or indirectly, any commission for securing the job from any domestic worker or to charge them any expenses")],
  not_cite=[A(L33, 6)])
Q("numeric", "What is the administrative fine if a recruitment office is late refunding fees to the employer?", [A(C106, 20), A(C106, 6)],
  [F("AED 2,000 per case for failure to refund within two weeks of the worker's return or absence report.", C106, 20,
     "Failure to refund all or part of the recruitment fees to the employer within two weeks following the return of the domestic worker to the recruitment office or upon reporting the domestic worker's absence from work. 2,000 dirhams for each case")],
  note="Schedule 2 is folded into 'Article 20' by the chunker.")
Q("numeric", "What is the fine if an employer or family member assaults a domestic worker?", [A(C106, 20), A(C106, 15)],
  [F("AED 20,000 per case.", C106, 20, "assaults or harasses the domestic worker. 20,000 dirhams for each case"),
   F("The Ministry may also suspend the employer's file.", C106, 15,
     "If it is proven that the employer or his representative has assaulted, harassed, or contempt the domestic worker in any way")])
Q("single_fact", "When can the Ministry suspend an employer's file for not paying wages to a domestic worker?", [A(C106, 15)],
  [F("Non-payment of the agreed wage for more than two months.", C106, 15,
     "Non-payment of the agreed wage under the employment contract for a period of more than two months")])
Q("scenario", "What penalties apply to an employer who employs a domestic worker without a work permit?", [A(L9, 27), A(C106, 20)],
  [F("Criminal fine of AED 50,000 to AED 200,000 for providing employment without a work permit.", L9, 27,
     "A fine of at least AED 50,000 (Fifty Thousand Dirhams) and up to AED 200,000 (Two Hundred Thousand Dirhams) shall be imposed on those who commit the following"),
   F("Administrative fine of AED 5,000 per illegal domestic worker.", C106, 20, "5,000 dirhams for each illegal domestic worker")],
  not_cite=[A(L33, 60)], note="Two regimes apply; a full answer mentions both.")
Q("numeric", "How long does a domestic worker have to sue for her entitlements after the job ends?", [A(L9, 26)],
  [F("Not heard after three months from the date the employment relationship ended.", L9, 26,
     "shall not be heard after the lapse of three months from the date of termination of the employment relationship"),
   F("Domestic workers' actions are exempt from judicial fees.", L9, 26, "Actions and applications filed by domestic workers shall be exempted from judicial fees")],
  avoid=["States one year as the limitation period"], not_cite=[A(L33, 54)])
Q("scenario", "A domestic worker and employer cannot settle a dispute. What happens next and how fast?", [A(C106, 13), A(L9, 23)],
  [F("The dispute must be referred to the Ministry; if no amicable settlement within two weeks of the complaint, it goes to the competent court.", L9, 23,
     "In the event that an amicable settlement cannot be reached within two (2) weeks of receiving the complaint, the dispute will be referred to the competent court"),
   F("The Ministry refers the matter to court within two weeks of receiving the complaint, with a legal opinion memorandum.", C106, 13,
     "the Ministry will refer the matter to the appropriate court within two weeks of receiving the complaint")])
Q("scenario", "Who is responsible for a temporary-employment domestic worker if the beneficiary fails their obligations?", [A(C106, 9), A(L9, 14)],
  [F("The recruitment office remains jointly responsible with the beneficiary and cannot evade its employer obligations.", C106, 9,
     "The office shall be jointly responsible for implementing these obligations with the beneficiary"),
   F("The recruitment office functions as employer for temporary employment.", L9, 14,
     "The domestic workers recruitment office functions as the employer for temporary employment")])
Q("single_fact", "If a domestic worker travels abroad with the family, which rules apply?", [A(L9, 3)],
  [F("All parties must abide by the employment contract unless the destination country's laws provide otherwise.", L9, 3,
     "it is mandatory for all parties to the employment contract to abide by the terms of the employment contract unless otherwise provided by the laws of the foreign country of destination")])

# ---------------- Not covered / out of corpus ----------------
Q("unanswerable_partial", "What is the minimum wage for private sector workers in the UAE?", [A(L33, 27)],
  [F("States that the provided text does not set a figure; the Cabinet may issue a resolution to determine the minimum wage.", L33, 27,
     "issue a resolution to determine the minimum wage for workers or any category thereof")],
  avoid=["Gives a specific AED minimum wage figure as if it were in the documents"],
  note="Article 27 only delegates power; a correct answer says no amount is stated.")
Q("unanswerable", "How much does a residence visa for a domestic worker cost?", [],
  [F("States that the provided documents do not contain visa or residence fee amounts.")],
  avoid=["Gives a specific visa fee amount"], answerable=False,
  note="Fees are delegated to the Cabinet/Ministry (L9 Art 29) and not listed in the corpus.")
Q("unanswerable", "What are the VAT or income tax rules for an employee's salary in the UAE?", [],
  [F("States that the provided documents do not cover taxation.")],
  avoid=["Gives specific tax rates or rules"], answerable=False)

meta = {
    "_meta": {
        "purpose": "Ground-truth set for evaluating retrieval, citation and answer correctness of the UAE labour-law RAG.",
        "status": "LLM-DRAFTED, NOT EXPERT-REVIEWED. Each question has reviewed_by=null until a compliance officer or lawyer signs off.",
        "relevance_level": "(source_document, article) pairs, stable across re-chunking. expected_articles = articles that together contain the answer; any one counts for Hit/MRR, all count for Recall.",
        "corpus": [L33, C92, L9, C106],
        "corpus_caveat": "Answers are keyed to the supplied PDF texts only (unofficial translations; some articles are amended by later decrees). The set does not claim to reflect current UAE law.",
        "quote_policy": "Every must_include fact with a quote is verifiable by verbatim match (whitespace/quote-insensitive) against chunk text of the stated article. Run: python eval_answers.py verify-set",
        "must_not_cite": "Articles from the wrong law (e.g. private-sector rule for a domestic worker question). Citing one is a wrong-law flag.",
    },
    "questions": QS,
}
with open("eval_set.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print(len(QS), "questions")
