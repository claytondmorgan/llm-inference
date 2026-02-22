"""
Generate synthetic legal documents CSV for the Legal Document Search Demo.
Run: python generate_legal_data.py
Output: legal-documents.csv
"""

import csv
import os

def generate_legal_data():
    documents = []

    # ============================================================
    # 1. LANDMARK CASES (13 documents)
    # ============================================================

    documents.append({
        "doc_id": "case-001",
        "doc_type": "case_law",
        "title": "Miranda v. Arizona",
        "citation": "384 U.S. 436 (1966)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1966-06-13",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that statements obtained from a defendant during custodial interrogation "
            "are inadmissible unless the prosecution demonstrates that procedural safeguards were employed to "
            "secure the privilege against self-incrimination. The Court established that prior to any questioning, "
            "a person must be warned that they have the right to remain silent, that any statement they make may "
            "be used as evidence against them, and that they have the right to the presence of an attorney, either "
            "retained or appointed. The defendant may waive these rights, provided the waiver is made voluntarily, "
            "knowingly, and intelligently. If at any point during the interrogation the individual indicates a desire "
            "to consult with an attorney or to remain silent, the interrogation must cease. The Court reasoned that "
            "the coercive nature of custodial interrogation undermines the Fifth Amendment privilege, and that "
            "without proper warnings and a clear waiver, no evidence obtained through such interrogation may be "
            "admitted. The decision applied to four consolidated cases involving confessions obtained without "
            "adequate procedural protections."
        ),
        "headnotes": (
            "Fifth Amendment privilege against self-incrimination requires procedural safeguards during custodial "
            "interrogation. Suspects must be informed of right to silence and right to counsel before questioning."
        ),
        "practice_area": "criminal",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-002",
        "doc_type": "case_law",
        "title": "Brown v. Board of Education of Topeka",
        "citation": "347 U.S. 483 (1954)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1954-05-17",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court unanimously held that racial segregation in public schools violates the Equal "
            "Protection Clause of the Fourteenth Amendment. The Court found that separating children in public "
            "schools solely on the basis of race generates a feeling of inferiority among affected children that "
            "may affect their hearts and minds in a way unlikely ever to be undone. The Court rejected the "
            "doctrine established in Plessy v. Ferguson that separate facilities for different races could be "
            "considered equal. Chief Justice Warren wrote that in the field of public education, the doctrine of "
            "separate but equal has no place, as separate educational facilities are inherently unequal. The "
            "decision consolidated cases from Kansas, South Carolina, Virginia, and Delaware. The Court considered "
            "extensive sociological and psychological evidence demonstrating the harmful effects of segregation "
            "on minority children. This landmark ruling effectively overturned decades of legally sanctioned "
            "racial segregation and became a cornerstone of the civil rights movement."
        ),
        "headnotes": (
            "Racial segregation in public schools violates the Equal Protection Clause. Separate educational "
            "facilities are inherently unequal. Overrules Plessy v. Ferguson in the context of public education."
        ),
        "practice_area": "constitutional_law",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-003",
        "doc_type": "case_law",
        "title": "Marbury v. Madison",
        "citation": "5 U.S. (1 Cranch) 137 (1803)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1803-02-24",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court established the principle of judicial review, holding that the federal judiciary "
            "has the authority to review acts of Congress and declare them void if they are found to be in conflict "
            "with the Constitution. Chief Justice Marshall wrote that it is emphatically the province and duty of "
            "the judicial department to say what the law is. The Court held that William Marbury was entitled to "
            "his commission as justice of the peace, but that the provision of the Judiciary Act of 1789 that "
            "purported to grant the Supreme Court original jurisdiction to issue writs of mandamus was "
            "unconstitutional because it expanded the Court's original jurisdiction beyond what Article III "
            "permits. The decision established that the Constitution is the supreme law of the land and that "
            "any legislative act repugnant to the Constitution is void. This foundational case established the "
            "framework for constitutional governance and the role of the judiciary as the ultimate interpreter "
            "of constitutional meaning."
        ),
        "headnotes": (
            "Establishes judicial review: federal courts may declare acts of Congress unconstitutional. "
            "The Constitution is the supreme law and any conflicting legislation is void."
        ),
        "practice_area": "constitutional_law",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-004",
        "doc_type": "case_law",
        "title": "Mapp v. Ohio",
        "citation": "367 U.S. 643 (1961)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1961-06-19",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that the exclusionary rule, which prohibits the use of evidence obtained "
            "in violation of the Fourth Amendment, applies to state criminal proceedings through the Fourteenth "
            "Amendment's Due Process Clause. The Court overruled Wolf v. Colorado, which had held that the "
            "exclusionary rule was not binding on the states. The majority reasoned that the right to privacy "
            "embodied in the Fourth Amendment is enforceable against the states and that without the exclusionary "
            "rule, the Fourth Amendment's protections would be reduced to a form of words. The Court emphasized "
            "that the exclusionary rule is an essential part of the Fourth Amendment, not merely a judicially "
            "created remedy. The decision established that all evidence obtained by searches and seizures in "
            "violation of the Constitution is inadmissible in state courts, creating a uniform federal standard "
            "for the admissibility of evidence."
        ),
        "headnotes": (
            "The exclusionary rule applies to state proceedings through the Fourteenth Amendment. Evidence "
            "obtained through unconstitutional searches is inadmissible in state courts."
        ),
        "practice_area": "criminal",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-005",
        "doc_type": "case_law",
        "title": "Gideon v. Wainwright",
        "citation": "372 U.S. 335 (1963)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1963-03-18",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court unanimously held that the Sixth Amendment's guarantee of counsel is a fundamental "
            "right essential to a fair trial and is made obligatory upon the states through the Fourteenth "
            "Amendment. The Court overruled Betts v. Brady, which had limited the right to appointed counsel "
            "in state courts to capital cases or cases involving special circumstances. Justice Black wrote that "
            "any person hauled into court who is too poor to hire a lawyer cannot be assured a fair trial unless "
            "counsel is provided. The Court reasoned that lawyers in criminal courts are necessities, not luxuries, "
            "and that the government hires lawyers to prosecute and defendants who have money hire lawyers to "
            "defend, indicating that the right to counsel is fundamental. The decision required states to provide "
            "an attorney to defendants in criminal cases who cannot afford one."
        ),
        "headnotes": (
            "Sixth Amendment right to counsel is a fundamental right applicable to state proceedings. "
            "States must provide counsel to indigent defendants in criminal cases."
        ),
        "practice_area": "criminal",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-006",
        "doc_type": "case_law",
        "title": "Terry v. Ohio",
        "citation": "392 U.S. 1 (1968)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1968-06-10",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that a police officer may stop and briefly detain a person for investigative "
            "purposes if the officer has a reasonable suspicion supported by articulable facts that criminal "
            "activity may be afoot, even if the officer lacks probable cause for an arrest. The Court further "
            "held that the officer may conduct a carefully limited search of the outer clothing of such persons "
            "if the officer has reason to believe they may be armed and dangerous. The Court balanced the "
            "government's interest in effective law enforcement against the individual's Fourth Amendment right "
            "to personal security, concluding that the limited intrusion of a stop and frisk is justified when "
            "the officer can point to specific and articulable facts warranting the intrusion. The decision "
            "established the reasonable suspicion standard as distinct from and lower than the probable cause "
            "standard for arrests and full searches."
        ),
        "headnotes": (
            "Officers may conduct brief investigatory stops based on reasonable suspicion. A limited pat-down "
            "frisk is permissible when the officer reasonably believes the person may be armed."
        ),
        "practice_area": "criminal",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-007",
        "doc_type": "case_law",
        "title": "Griswold v. Connecticut",
        "citation": "381 U.S. 479 (1965)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1965-06-07",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that a Connecticut law prohibiting the use of contraceptives violated the "
            "constitutional right to marital privacy. Justice Douglas wrote for the majority that specific "
            "guarantees in the Bill of Rights have penumbras formed by emanations from those guarantees that "
            "give them life and substance, and that the right to privacy exists within these penumbras. The Court "
            "found that the First, Third, Fourth, Fifth, and Ninth Amendments create zones of privacy that "
            "protect the marital relationship. The Connecticut statute operated directly on the intimate relation "
            "of husband and wife, and the Court held that the state had no legitimate interest in regulating "
            "the use of contraceptives by married couples. The decision established the constitutional right "
            "to privacy as a fundamental right worthy of protection, even though the word privacy does not "
            "appear in the Constitution."
        ),
        "headnotes": (
            "The Bill of Rights contains penumbral rights including a right to privacy. State laws prohibiting "
            "contraceptive use by married couples violate the constitutional right to marital privacy."
        ),
        "practice_area": "constitutional_law",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-008",
        "doc_type": "case_law",
        "title": "New York Times Co. v. Sullivan",
        "citation": "376 U.S. 254 (1964)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1964-03-09",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that the First Amendment protects the publication of statements about the "
            "conduct of public officials, even when the statements are false, unless they are made with actual "
            "malice, defined as knowledge that the statements were false or with reckless disregard of whether "
            "they were false or not. The Court reversed a defamation judgment against the New York Times, holding "
            "that a public official may not recover damages for a defamatory falsehood relating to official "
            "conduct unless the official proves actual malice with convincing clarity. The Court reasoned that "
            "debate on public issues should be uninhibited, robust, and wide-open, and that erroneous statements "
            "are inevitable in free debate and must be protected to give free expression the breathing space it "
            "needs to survive. The decision fundamentally reshaped defamation law and strengthened First "
            "Amendment protections for criticism of government officials."
        ),
        "headnotes": (
            "Public officials must prove actual malice to recover in defamation actions. Actual malice means "
            "knowledge of falsity or reckless disregard for truth."
        ),
        "practice_area": "constitutional_law",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-009",
        "doc_type": "case_law",
        "title": "Tinker v. Des Moines Independent Community School District",
        "citation": "393 U.S. 503 (1969)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1969-02-24",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that students do not shed their constitutional rights to freedom of speech "
            "or expression at the schoolhouse gate. The Court found that the wearing of black armbands to "
            "protest the Vietnam War was protected symbolic speech under the First Amendment. The majority "
            "held that school officials could not prohibit student expression unless they could demonstrate "
            "that the expression would substantially and materially interfere with the operation of the school "
            "or impinge upon the rights of other students. The Court rejected the school district's argument "
            "that the armbands could lead to disruption, finding no evidence that the armbands caused any "
            "disruption or disorder. The decision established the substantial disruption test for student "
            "speech, requiring schools to show more than a mere desire to avoid the discomfort and "
            "unpleasantness of an unpopular viewpoint."
        ),
        "headnotes": (
            "Students retain First Amendment rights in school. Schools may restrict student speech only if it "
            "would cause substantial and material disruption to school operations."
        ),
        "practice_area": "constitutional_law",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-010",
        "doc_type": "case_law",
        "title": "Katz v. United States",
        "citation": "389 U.S. 347 (1967)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1967-12-18",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that the Fourth Amendment protects people, not places, and that a person "
            "has a constitutionally protected reasonable expectation of privacy. The Court found that the FBI's "
            "warrantless electronic surveillance of a public telephone booth constituted a search within the "
            "meaning of the Fourth Amendment. Justice Harlan's concurrence established the two-part test that "
            "has become the framework for Fourth Amendment analysis: first, the individual must have exhibited "
            "an actual subjective expectation of privacy, and second, that expectation must be one that society "
            "is prepared to recognize as reasonable. The Court rejected the prior trespass doctrine from Olmstead "
            "v. United States, holding that the reach of the Fourth Amendment cannot turn upon the presence or "
            "absence of a physical intrusion into any given enclosure. The decision modernized Fourth Amendment "
            "analysis to address electronic surveillance technologies."
        ),
        "headnotes": (
            "Fourth Amendment protects reasonable expectations of privacy, not just physical spaces. Warrantless "
            "electronic surveillance requires a warrant when a reasonable expectation of privacy exists."
        ),
        "practice_area": "criminal",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-011",
        "doc_type": "case_law",
        "title": "Plessy v. Ferguson",
        "citation": "163 U.S. 537 (1896)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1896-05-18",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court upheld the constitutionality of racial segregation under the separate but equal "
            "doctrine. The majority held that a Louisiana law requiring separate railway carriages for white "
            "and non-white passengers did not violate the Thirteenth or Fourteenth Amendments. The Court "
            "reasoned that the Fourteenth Amendment was not intended to abolish distinctions based upon color "
            "or to enforce social equality. The majority found that legislation permitting separation of the "
            "two races did not necessarily imply the inferiority of either race and that such separation was "
            "a reasonable exercise of state police power. Justice Harlan dissented, arguing that the Constitution "
            "is color-blind and neither knows nor tolerates classes among citizens. This decision was later "
            "overruled by Brown v. Board of Education, which held that separate educational facilities are "
            "inherently unequal."
        ),
        "headnotes": (
            "OVERRULED: Upheld separate but equal doctrine for racial segregation. Overruled by Brown v. Board "
            "of Education, 347 U.S. 483 (1954)."
        ),
        "practice_area": "constitutional_law",
        "status": "overruled"
    })

    documents.append({
        "doc_id": "case-012",
        "doc_type": "case_law",
        "title": "Korematsu v. United States",
        "citation": "323 U.S. 214 (1944)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1944-12-18",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court upheld Executive Order 9066, which authorized the forced relocation and "
            "internment of Japanese Americans during World War II. The majority applied strict scrutiny but "
            "found that the order was justified by military necessity during wartime. The Court held that "
            "pressing public necessity may sometimes justify restrictions that curtail the civil rights of "
            "a single racial group. Justice Murphy dissented, arguing the order constituted the legalization "
            "of racism and fell into the ugly abyss of racism. Justice Jackson also dissented, warning that "
            "the principle of racial discrimination lies about like a loaded weapon ready for use by any "
            "authority that can bring forward a plausible claim of an urgent need. The decision was formally "
            "repudiated by the Supreme Court in Trump v. Hawaii (2018), where Chief Justice Roberts stated "
            "that Korematsu was gravely wrong the day it was decided."
        ),
        "headnotes": (
            "OVERRULED: Upheld wartime internment of Japanese Americans. Formally repudiated by Trump v. Hawaii, "
            "585 U.S. ___ (2018). Recognized as a grave constitutional error."
        ),
        "practice_area": "constitutional_law",
        "status": "overruled"
    })

    documents.append({
        "doc_id": "case-013",
        "doc_type": "case_law",
        "title": "Obergefell v. Hodges",
        "citation": "576 U.S. 644 (2015)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "2015-06-26",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that the fundamental right to marry is guaranteed to same-sex couples by "
            "both the Due Process Clause and the Equal Protection Clause of the Fourteenth Amendment. Justice "
            "Kennedy wrote for the majority that the right to marry is a fundamental liberty because it is "
            "inherent in the concept of individual autonomy, it supports a two-person union unlike any other, "
            "it safeguards children and families, and marriage is a keystone of the nation's social order. The "
            "Court found that there is no difference between same-sex and opposite-sex couples with respect "
            "to these principles, and that laws excluding same-sex couples from marriage impose stigma and "
            "injury on them. The decision required all states to issue marriage licenses to same-sex couples "
            "and to recognize same-sex marriages lawfully performed in other states."
        ),
        "headnotes": (
            "The fundamental right to marry extends to same-sex couples under the Due Process and Equal "
            "Protection Clauses of the Fourteenth Amendment. States must license and recognize same-sex marriages."
        ),
        "practice_area": "constitutional_law",
        "status": "good_law"
    })

    # ============================================================
    # 2. EMPLOYMENT DISCRIMINATION CASES (12 documents)
    # ============================================================

    documents.append({
        "doc_id": "case-020",
        "doc_type": "case_law",
        "title": "McDonnell Douglas Corp. v. Green",
        "citation": "411 U.S. 792 (1973)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1973-05-14",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court established the burden-shifting framework for employment discrimination cases "
            "brought under Title VII of the Civil Rights Act. The Court held that the plaintiff must first "
            "establish a prima facie case of discrimination by showing membership in a protected class, "
            "qualification for the position, an adverse employment action, and circumstances giving rise to an "
            "inference of discrimination. Once the plaintiff establishes a prima facie case, the burden shifts "
            "to the employer to articulate a legitimate, nondiscriminatory reason for the adverse action. If "
            "the employer meets this burden, the plaintiff must then demonstrate that the stated reason is "
            "pretextual. The Court emphasized that the ultimate burden of persuasion remains with the plaintiff "
            "throughout the proceeding. This framework has become the standard analytical tool in disparate "
            "treatment cases and has been widely adopted across federal circuits."
        ),
        "headnotes": (
            "Establishes burden-shifting framework for Title VII disparate treatment cases. Plaintiff must show "
            "prima facie case; employer must articulate legitimate reason; plaintiff must prove pretext."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-021",
        "doc_type": "case_law",
        "title": "Griggs v. Duke Power Co.",
        "citation": "401 U.S. 424 (1971)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1971-03-08",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court unanimously held that Title VII prohibits employment practices that are facially "
            "neutral but discriminatory in operation, establishing the disparate impact theory of discrimination. "
            "The Court found that Duke Power's requirement of a high school diploma and passage of intelligence "
            "tests as conditions of employment or transfer disqualified Black applicants at a substantially "
            "higher rate than white applicants, and neither requirement was shown to be related to job "
            "performance. Chief Justice Burger wrote that Title VII proscribes not only overt discrimination "
            "but also practices that are fair in form but discriminatory in operation, and that the touchstone "
            "is business necessity. The decision established that if an employment practice that operates to "
            "exclude a protected group cannot be shown to be related to job performance, it is prohibited."
        ),
        "headnotes": (
            "Title VII prohibits facially neutral employment practices with disparate impact on protected groups "
            "unless justified by business necessity. Establishes disparate impact theory."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-022",
        "doc_type": "case_law",
        "title": "Harris v. Forklift Systems, Inc.",
        "citation": "510 U.S. 17 (1993)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1993-11-09",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that a plaintiff alleging a hostile work environment under Title VII need "
            "not prove that the conduct seriously affected their psychological well-being or caused them to "
            "suffer injury. The Court established a middle path between making actionable any conduct that is "
            "merely offensive and requiring the conduct to cause a tangible psychological injury. The standard "
            "considers both an objective component (whether a reasonable person would find the environment "
            "hostile or abusive) and a subjective component (whether the victim perceived it as such). The "
            "Court identified several factors relevant to this determination, including the frequency and "
            "severity of the conduct, whether it is physically threatening or humiliating, and whether it "
            "unreasonably interferes with the employee's work performance."
        ),
        "headnotes": (
            "Hostile work environment claims under Title VII do not require proof of psychological injury. "
            "Standard is whether conduct is severe or pervasive enough to alter conditions of employment."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-023",
        "doc_type": "case_law",
        "title": "Ramirez v. TechCorp Industries",
        "citation": "45 Cal. App. 5th 892 (2020)",
        "jurisdiction": "CA",
        "date_decided": "2020-03-15",
        "court": "California Court of Appeal, Second District",
        "content": (
            "The court held that an employer's failure to engage in the interactive process required by the "
            "California Fair Employment and Housing Act constitutes an independent basis for liability in a "
            "disability discrimination claim. The plaintiff, a software engineer diagnosed with a repetitive "
            "strain condition, requested ergonomic equipment and modified work schedules. The employer did not "
            "respond to these requests for several months, during which the plaintiff's condition worsened. "
            "The court found that FEHA requires employers to engage in a timely, good-faith interactive process "
            "to determine effective reasonable accommodations. The failure to do so, combined with the "
            "subsequent termination of the employee, supported both the discrimination and retaliation claims. "
            "The court awarded damages including back pay, front pay, and emotional distress damages, finding "
            "the employer's conduct demonstrated a willful disregard of its statutory obligations."
        ),
        "headnotes": (
            "Failure to engage in FEHA interactive process is an independent basis for liability. Employers "
            "must timely respond to accommodation requests in good faith."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-024",
        "doc_type": "case_law",
        "title": "Johnson v. Pacific Logistics Group",
        "citation": "312 F.3d 1045 (9th Cir. 2019)",
        "jurisdiction": "Federal_9th_Circuit",
        "date_decided": "2019-07-22",
        "court": "United States Court of Appeals for the Ninth Circuit",
        "content": (
            "The Ninth Circuit held that an employer's pattern of transferring employees who filed internal "
            "complaints of racial harassment constituted retaliation in violation of Title VII. The court found "
            "that while lateral transfers are not per se adverse employment actions, a transfer made in response "
            "to protected activity that results in materially adverse consequences to the employee satisfies the "
            "retaliation standard under Burlington Northern. The plaintiff demonstrated that within two weeks "
            "of filing a formal complaint about racially offensive comments by a supervisor, she was transferred "
            "to a position with less desirable hours, a longer commute, and reduced opportunities for overtime "
            "pay. The court emphasized that the temporal proximity between the complaint and the transfer, "
            "combined with the employer's failure to articulate a legitimate business reason, supported an "
            "inference of retaliatory motive."
        ),
        "headnotes": (
            "Lateral transfers in response to protected complaints may constitute retaliation under Title VII. "
            "Temporal proximity between complaint and adverse action supports inference of retaliation."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-025",
        "doc_type": "case_law",
        "title": "Martinez v. Southwest Healthcare Corp.",
        "citation": "52 Cal. App. 5th 234 (2021)",
        "jurisdiction": "CA",
        "date_decided": "2021-01-12",
        "court": "California Court of Appeal, Fourth District",
        "content": (
            "The court addressed the standard for proving FMLA interference and retaliation claims when an "
            "employee is terminated shortly after returning from medical leave. The plaintiff, a registered "
            "nurse, took twelve weeks of FMLA leave for treatment of a serious health condition. Upon return, "
            "the employer placed her on a performance improvement plan and terminated her employment within "
            "thirty days, citing performance deficiencies that allegedly predated her leave. The court held "
            "that an employer's articulated reason for termination may be found pretextual when the employer "
            "fails to document performance concerns before the leave, initiates corrective action only after "
            "the employee exercises FMLA rights, and applies different standards to similarly situated employees "
            "who did not take leave. The court also clarified that FMLA interference does not require proof "
            "of discriminatory intent; the employee need only show that the employer denied a benefit to which "
            "the employee was entitled under the statute."
        ),
        "headnotes": (
            "FMLA interference does not require proof of discriminatory intent. Termination shortly after FMLA "
            "leave with undocumented pre-leave performance concerns suggests pretext."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-026",
        "doc_type": "case_law",
        "title": "Chen v. DataSoft Solutions Inc.",
        "citation": "287 F. Supp. 3d 456 (S.D.N.Y. 2018)",
        "jurisdiction": "NY",
        "date_decided": "2018-09-05",
        "court": "United States District Court for the Southern District of New York",
        "content": (
            "The court denied the employer's motion for summary judgment on claims of national origin "
            "discrimination and hostile work environment under Title VII and the New York State Human Rights "
            "Law. The plaintiff, a Chinese-American data analyst, presented evidence that his supervisor "
            "made repeated comments questioning his English proficiency despite his native fluency, excluded "
            "him from team meetings, and assigned him less visible projects compared to similarly qualified "
            "non-Asian colleagues. The court found that while individual comments might not rise to the level "
            "of actionable harassment, the cumulative effect of the supervisor's conduct over an eighteen-month "
            "period, including both verbal comments and differential treatment, could lead a reasonable jury to "
            "find that the workplace was permeated with discriminatory intimidation. The court noted that the "
            "New York Human Rights Law provides broader protections than federal law and requires only that the "
            "conduct constitute unequal treatment based on a protected characteristic."
        ),
        "headnotes": (
            "Cumulative discriminatory conduct over time can support hostile work environment claim. NY Human "
            "Rights Law provides broader protections than Title VII for workplace discrimination."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-027",
        "doc_type": "case_law",
        "title": "Williams v. Lone Star Energy Partners",
        "citation": "678 F.3d 412 (5th Cir. 2017)",
        "jurisdiction": "Federal_5th_Circuit",
        "date_decided": "2017-11-30",
        "court": "United States Court of Appeals for the Fifth Circuit",
        "content": (
            "The Fifth Circuit held that an employer's honest belief in the stated reason for termination "
            "defeats an inference of pretext, even if the employer's belief was mistaken. The plaintiff, an "
            "African-American operations manager, claimed he was terminated because of his race after he "
            "was accused of falsifying safety inspection reports. The court found that the employer conducted "
            "an investigation, concluded that the plaintiff had submitted inaccurate reports, and terminated "
            "his employment based on that conclusion. Although the plaintiff presented evidence suggesting that "
            "the reports may have been accurate, the court held that the question is not whether the employer "
            "made the correct decision, but whether the employer genuinely believed the stated reason. The "
            "dissent argued that the majority's application of the honest belief doctrine effectively immunized "
            "employers from claims of discrimination by allowing them to rely on flawed investigations."
        ),
        "headnotes": (
            "Employer's honest belief in stated reason for termination defeats pretext, even if mistaken. "
            "Dissent questions whether doctrine immunizes employers from scrutiny of flawed investigations."
        ),
        "practice_area": "employment",
        "status": "distinguished"
    })

    documents.append({
        "doc_id": "case-028",
        "doc_type": "case_law",
        "title": "Davis v. Metro Transit Authority",
        "citation": "89 Cal. App. 5th 1120 (2022)",
        "jurisdiction": "CA",
        "date_decided": "2022-06-14",
        "court": "California Court of Appeal, First District",
        "content": (
            "The court held that an employer's facially neutral attendance policy had a disparate impact on "
            "employees with disabilities in violation of the ADA and California FEHA. The transit authority "
            "implemented an automated point system that assessed points for each absence regardless of the "
            "reason, including absences related to medical conditions covered by reasonable accommodation "
            "obligations. Employees who accumulated a specified number of points within a rolling twelve-month "
            "period were subject to progressive discipline and eventual termination. The court found that the "
            "policy disproportionately affected employees with chronic health conditions who required periodic "
            "absences for medical treatment, and that the employer failed to demonstrate that the rigid "
            "application of the policy without exemptions for disability-related absences was consistent with "
            "business necessity. The court ordered reinstatement and back pay for the terminated employees."
        ),
        "headnotes": (
            "Facially neutral attendance policies that disproportionately affect disabled employees may violate "
            "ADA and FEHA. Employers must consider disability-related absences in accommodation analysis."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-029",
        "doc_type": "case_law",
        "title": "Thompson v. Global Financial Services",
        "citation": "415 F. Supp. 3d 789 (N.D. Tex. 2019)",
        "jurisdiction": "TX",
        "date_decided": "2019-04-08",
        "court": "United States District Court for the Northern District of Texas",
        "content": (
            "The court granted partial summary judgment for the plaintiff on her pregnancy discrimination claim "
            "under Title VII and the Pregnancy Discrimination Act. The plaintiff, a senior financial analyst, "
            "was denied promotion to vice president after informing her supervisor of her pregnancy. The "
            "employer promoted a less experienced male colleague instead, stating that the position required "
            "extensive travel that the plaintiff would be unable to perform. The court found that the "
            "employer's assumption about the plaintiff's ability to travel based on her pregnancy constituted "
            "direct evidence of discrimination. The court held that an employer may not make employment "
            "decisions based on assumptions about the capabilities of pregnant employees, and that the "
            "Pregnancy Discrimination Act requires that pregnant workers be treated the same as other employees "
            "who are similar in their ability or inability to work."
        ),
        "headnotes": (
            "Employer assumptions about pregnant employees' capabilities constitute direct evidence of "
            "discrimination. PDA requires pregnant workers be treated same as similarly able employees."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-030",
        "doc_type": "case_law",
        "title": "Rivera v. Coastal Manufacturing Inc.",
        "citation": "198 F.3d 567 (2nd Cir. 2016)",
        "jurisdiction": "Federal_2nd_Circuit",
        "date_decided": "2016-08-19",
        "court": "United States Court of Appeals for the Second Circuit",
        "content": (
            "The Second Circuit reversed the district court's grant of summary judgment for the employer on "
            "age discrimination claims under the ADEA. The plaintiff, a 58-year-old production supervisor with "
            "twenty-five years of experience, was terminated as part of a reduction in force that "
            "disproportionately affected employees over fifty. The employer claimed the selection criteria were "
            "based on objective performance metrics, but the court found genuine disputes of material fact "
            "regarding whether the metrics were applied consistently. Evidence showed that several younger "
            "employees with lower performance scores were retained, and that the decision-makers had made "
            "age-related remarks in meetings, including references to the need for fresh perspectives and "
            "new energy. The court held that while individual remarks may not constitute direct evidence, "
            "stray remarks by decision-makers combined with statistical disparities in the RIF create a triable "
            "issue of discriminatory intent."
        ),
        "headnotes": (
            "Age-related remarks by decision-makers combined with statistical disparities in RIF create triable "
            "issue of discriminatory intent under ADEA. Inconsistent application of selection criteria is evidence of pretext."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-031",
        "doc_type": "case_law",
        "title": "Patterson v. Apex Hospitality Group",
        "citation": "34 Cal. App. 5th 567 (2018)",
        "jurisdiction": "CA",
        "date_decided": "2018-12-03",
        "court": "California Court of Appeal, Third District",
        "content": (
            "The court addressed whether an employer's written anti-harassment policy insulates it from "
            "liability under FEHA when the policy is not effectively enforced. The plaintiff, a hotel front "
            "desk supervisor, reported ongoing sexual harassment by a general manager through the company's "
            "designated reporting channel. Although the employer had a facially adequate anti-harassment policy, "
            "the investigation was conducted by a personal friend of the accused and concluded within three days "
            "without interviewing several identified witnesses. The court held that the existence of an "
            "anti-harassment policy does not automatically shield an employer from liability and that the "
            "adequacy of the employer's response must be evaluated based on the thoroughness and impartiality "
            "of the investigation, the promptness of corrective action, and whether the response was reasonably "
            "calculated to end the harassment. The court found the employer's investigation was inadequate as "
            "a matter of law."
        ),
        "headnotes": (
            "Anti-harassment policy alone does not insulate employer from FEHA liability. Adequacy of response "
            "measured by thoroughness, impartiality of investigation, and effectiveness of corrective action."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    # ============================================================
    # 3. STATUTES (12 documents)
    # ============================================================

    documents.append({
        "doc_id": "statute-001",
        "doc_type": "statute",
        "title": "Title VII of the Civil Rights Act of 1964 - Unlawful Employment Practices",
        "citation": "42 U.S.C. \u00a7 2000e-2",
        "jurisdiction": "US_Federal",
        "date_decided": "1964-07-02",
        "court": "United States Congress",
        "content": (
            "It shall be an unlawful employment practice for an employer to fail or refuse to hire or to "
            "discharge any individual, or otherwise to discriminate against any individual with respect to "
            "compensation, terms, conditions, or privileges of employment, because of such individual's race, "
            "color, religion, sex, or national origin. It shall also be an unlawful employment practice for "
            "an employer to limit, segregate, or classify employees or applicants for employment in any way "
            "which would deprive or tend to deprive any individual of employment opportunities or otherwise "
            "adversely affect status as an employee, because of such individual's race, color, religion, sex, "
            "or national origin. It shall be an unlawful employment practice for an employment agency to fail "
            "or refuse to refer for employment, or otherwise to discriminate against, any individual because "
            "of race, color, religion, sex, or national origin. This section shall not apply to employment of "
            "aliens outside any State or to membership of combatant combatant forces."
        ),
        "headnotes": (
            "Prohibits employment discrimination based on race, color, religion, sex, or national origin. "
            "Covers hiring, firing, compensation, and terms of employment."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-002",
        "doc_type": "statute",
        "title": "Americans with Disabilities Act - Discrimination Prohibition",
        "citation": "42 U.S.C. \u00a7 12112",
        "jurisdiction": "US_Federal",
        "date_decided": "1990-07-26",
        "court": "United States Congress",
        "content": (
            "No covered entity shall discriminate against a qualified individual on the basis of disability "
            "in regard to job application procedures, the hiring, advancement, or discharge of employees, "
            "employee compensation, job training, and other terms, conditions, and privileges of employment. "
            "The term discriminate against a qualified individual on the basis of disability includes not "
            "making reasonable accommodations to the known physical or mental limitations of an otherwise "
            "qualified individual with a disability who is an applicant or employee, unless such covered entity "
            "can demonstrate that the accommodation would impose an undue hardship on the operation of the "
            "business. Reasonable accommodation may include making existing facilities used by employees "
            "readily accessible to and usable by individuals with disabilities, job restructuring, part-time "
            "or modified work schedules, reassignment to a vacant position, acquisition or modification of "
            "equipment or devices, appropriate adjustment or modifications of examinations, training materials "
            "or policies, the provision of qualified readers or interpreters, and other similar accommodations."
        ),
        "headnotes": (
            "Prohibits disability discrimination in employment. Requires reasonable accommodations unless "
            "undue hardship. Defines reasonable accommodation broadly."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-003",
        "doc_type": "statute",
        "title": "Americans with Disabilities Act - Definition of Disability",
        "citation": "42 U.S.C. \u00a7 12102",
        "jurisdiction": "US_Federal",
        "date_decided": "1990-07-26",
        "court": "United States Congress",
        "content": (
            "The term disability means, with respect to an individual, a physical or mental impairment that "
            "substantially limits one or more major life activities of such individual, a record of such an "
            "impairment, or being regarded as having such an impairment. Major life activities include, but "
            "are not limited to, caring for oneself, performing manual tasks, seeing, hearing, eating, sleeping, "
            "walking, standing, lifting, bending, speaking, breathing, learning, reading, concentrating, "
            "thinking, communicating, and working. A major life activity also includes the operation of a major "
            "bodily function, including but not limited to, functions of the immune system, normal cell growth, "
            "digestive, bowel, bladder, neurological, brain, respiratory, circulatory, endocrine, and "
            "reproductive functions. The definition of disability shall be construed in favor of broad coverage "
            "of individuals to the maximum extent permitted by the terms of this chapter."
        ),
        "headnotes": (
            "Defines disability as impairment substantially limiting major life activities. Includes record "
            "of impairment and regarded as having impairment. Construed broadly."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-004",
        "doc_type": "statute",
        "title": "California Fair Employment and Housing Act - Unlawful Practices",
        "citation": "Cal. Gov. Code \u00a7 12940",
        "jurisdiction": "CA",
        "date_decided": "1980-09-01",
        "court": "California State Legislature",
        "content": (
            "It is an unlawful employment practice for an employer, because of the race, religious creed, "
            "color, national origin, ancestry, physical disability, mental disability, medical condition, "
            "genetic information, marital status, sex, gender, gender identity, gender expression, age, "
            "sexual orientation, or veteran or military status of any person, to refuse to hire or employ the "
            "person or to bar or to discharge the person from employment or to discriminate against the person "
            "in compensation or in terms, conditions, or privileges of employment. For an employer or other "
            "entity covered by this part to fail to engage in a timely, good faith, interactive process with "
            "the employee or applicant to determine effective reasonable accommodations, if any, in response "
            "to a request for reasonable accommodation by an employee or applicant with a known physical or "
            "mental disability or known medical condition. For an employer or other entity to fail to make "
            "reasonable accommodation for the known physical or mental disability of an applicant or employee."
        ),
        "headnotes": (
            "FEHA prohibits employment discrimination on broad grounds including disability, gender identity, "
            "and genetic information. Requires interactive process and reasonable accommodation."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-005",
        "doc_type": "statute",
        "title": "Family and Medical Leave Act - Entitlement to Leave",
        "citation": "29 U.S.C. \u00a7 2612",
        "jurisdiction": "US_Federal",
        "date_decided": "1993-02-05",
        "court": "United States Congress",
        "content": (
            "An eligible employee shall be entitled to a total of 12 workweeks of leave during any 12-month "
            "period for one or more of the following: because of the birth of a son or daughter of the employee "
            "and in order to care for such son or daughter; because of the placement of a son or daughter with "
            "the employee for adoption or foster care; in order to care for the spouse, or a son, daughter, or "
            "parent, of the employee, if such spouse, son, daughter, or parent has a serious health condition; "
            "because of a serious health condition that makes the employee unable to perform the functions of "
            "the position of such employee; because of any qualifying exigency arising out of the fact that the "
            "spouse, or a son, daughter, or parent of the employee is on covered active duty in the Armed Forces. "
            "An eligible employee who is the spouse, son, daughter, parent, or next of kin of a covered "
            "servicemember shall be entitled to a total of 26 workweeks of leave during a 12-month period to "
            "care for the servicemember."
        ),
        "headnotes": (
            "Eligible employees entitled to 12 weeks unpaid leave for birth, adoption, family care, or "
            "serious health condition. 26 weeks for military caregiver leave."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-006",
        "doc_type": "statute",
        "title": "Civil Rights Act - Section 1983",
        "citation": "42 U.S.C. \u00a7 1983",
        "jurisdiction": "US_Federal",
        "date_decided": "1871-04-20",
        "court": "United States Congress",
        "content": (
            "Every person who, under color of any statute, ordinance, regulation, custom, or usage, of any "
            "State or Territory or the District of Columbia, subjects, or causes to be subjected, any citizen "
            "of the United States or other person within the jurisdiction thereof to the deprivation of any "
            "rights, privileges, or immunities secured by the Constitution and laws, shall be liable to the "
            "party injured in an action at law, suit in equity, or other proper proceeding for redress, except "
            "that in any action brought against a judicial officer for an act or omission taken in such "
            "officer's judicial capacity, injunctive relief shall not be granted unless a declaratory decree "
            "was violated or declaratory relief was unavailable. For the purposes of this section, any Act of "
            "Congress applicable exclusively to the District of Columbia shall be considered to be a statute "
            "of the District of Columbia."
        ),
        "headnotes": (
            "Provides civil remedy for deprivation of constitutional rights under color of state law. "
            "Applies to state and local government actors. Judicial officers have limited immunity."
        ),
        "practice_area": "civil_rights",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-007",
        "doc_type": "statute",
        "title": "Age Discrimination in Employment Act - Prohibition",
        "citation": "29 U.S.C. \u00a7 623",
        "jurisdiction": "US_Federal",
        "date_decided": "1967-12-15",
        "court": "United States Congress",
        "content": (
            "It shall be unlawful for an employer to fail or refuse to hire or to discharge any individual "
            "or otherwise discriminate against any individual with respect to his compensation, terms, "
            "conditions, or privileges of employment, because of such individual's age. It shall be unlawful "
            "for an employer to limit, segregate, or classify his employees in any way which would deprive or "
            "tend to deprive any individual of employment opportunities or otherwise adversely affect his "
            "status as an employee, because of such individual's age. It shall be unlawful for an employer to "
            "reduce the wage rate of any employee in order to comply with this chapter. The prohibitions in "
            "this section shall be limited to individuals who are at least 40 years of age. It shall not be "
            "unlawful for an employer to take any action otherwise prohibited under this section where age is "
            "a bona fide occupational qualification reasonably necessary to the normal operation of the "
            "particular business."
        ),
        "headnotes": (
            "Prohibits age discrimination in employment for individuals 40 and older. Covers hiring, firing, "
            "compensation, and classification. BFOQ defense available."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-008",
        "doc_type": "statute",
        "title": "Title VII - Definition of Employer",
        "citation": "42 U.S.C. \u00a7 2000e(b)",
        "jurisdiction": "US_Federal",
        "date_decided": "1964-07-02",
        "court": "United States Congress",
        "content": (
            "The term employer means a person engaged in an industry affecting commerce who has fifteen or more "
            "employees for each working day in each of twenty or more calendar weeks in the current or preceding "
            "calendar year, and any agent of such a person, but such term does not include the United States, "
            "a corporation wholly owned by the Government of the United States, an Indian tribe, or any "
            "department or agency of the District of Columbia subject by statute to procedures of the "
            "competitive service. The term employee means an individual employed by an employer, except that "
            "the term employee shall not include any person elected to public office in any State or political "
            "subdivision of any State by the qualified voters thereof, or any person chosen by such officer to "
            "be on such officer's personal staff."
        ),
        "headnotes": (
            "Title VII applies to employers with 15 or more employees. Federal government, Indian tribes, "
            "and DC agencies subject to competitive service are excluded."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-009",
        "doc_type": "statute",
        "title": "California FEHA - Reasonable Accommodation",
        "citation": "Cal. Gov. Code \u00a7 12940(m)",
        "jurisdiction": "CA",
        "date_decided": "1980-09-01",
        "court": "California State Legislature",
        "content": (
            "It is an unlawful employment practice for an employer or other entity covered by this part to "
            "fail to make reasonable accommodation for the known physical or mental disability of an applicant "
            "or employee. Nothing in this subdivision shall be construed to require an accommodation that is "
            "demonstrated by the employer or other covered entity to produce undue hardship to its operation. "
            "Reasonable accommodation includes making existing facilities used by employees readily accessible "
            "to and usable by individuals with disabilities, job restructuring, part-time or modified work "
            "schedules, reassignment to a vacant position, acquisition or modification of equipment or devices, "
            "adjustment or modifications of examinations, training materials or policies, the provision of "
            "qualified readers or interpreters, and other similar accommodations for individuals with "
            "disabilities. In determining whether an accommodation would impose an undue hardship on the "
            "operation of the employer, factors to be considered include the nature and cost of the accommodation "
            "needed, the overall financial resources of the facilities involved, and the impact of the "
            "accommodation on the operation of the facility."
        ),
        "headnotes": (
            "FEHA requires reasonable accommodation for known disabilities. Undue hardship defense available. "
            "Factors include cost, employer resources, and operational impact."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-010",
        "doc_type": "statute",
        "title": "Pregnancy Discrimination Act",
        "citation": "42 U.S.C. \u00a7 2000e(k)",
        "jurisdiction": "US_Federal",
        "date_decided": "1978-10-31",
        "court": "United States Congress",
        "content": (
            "The terms because of sex or on the basis of sex include, but are not limited to, because of or "
            "on the basis of pregnancy, childbirth, or related medical conditions; and women affected by "
            "pregnancy, childbirth, or related medical conditions shall be treated the same for all "
            "employment-related purposes, including receipt of benefits under fringe benefit programs, as "
            "other persons not so affected but similar in their ability or inability to work, and nothing in "
            "section 2000e-2(h) of this title shall be interpreted to permit otherwise. This subsection shall "
            "not require an employer to pay for health insurance benefits for abortion, except where the life "
            "of the mother would be endangered if the fetus were carried to term, or except where medical "
            "complications have arisen from an abortion."
        ),
        "headnotes": (
            "Pregnancy discrimination is sex discrimination under Title VII. Pregnant workers must be treated "
            "same as similarly situated non-pregnant workers."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-011",
        "doc_type": "statute",
        "title": "Title VII - Retaliation Prohibition",
        "citation": "42 U.S.C. \u00a7 2000e-3(a)",
        "jurisdiction": "US_Federal",
        "date_decided": "1964-07-02",
        "court": "United States Congress",
        "content": (
            "It shall be an unlawful employment practice for an employer to discriminate against any of his "
            "employees or applicants for employment, for an employment agency, or joint labor-management "
            "committee controlling apprenticeship or other training or retraining, including on-the-job "
            "training programs, to discriminate against any individual, or for a labor organization to "
            "discriminate against any member thereof or applicant for membership, because he has opposed any "
            "practice made an unlawful employment practice by this subchapter, or because he has made a charge, "
            "testified, assisted, or participated in any manner in an investigation, proceeding, or hearing "
            "under this subchapter. It shall be an unlawful employment practice for an employer, labor "
            "organization, employment agency, or joint labor-management committee controlling apprenticeship "
            "or other training or retraining to print or publish or cause to be printed or published any notice "
            "or advertisement relating to employment indicating any preference, limitation, specification, "
            "or discrimination based on protected characteristics."
        ),
        "headnotes": (
            "Prohibits retaliation against employees who oppose unlawful practices or participate in Title VII "
            "proceedings. Covers opposition and participation clause protections."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "statute-012",
        "doc_type": "statute",
        "title": "ADA Amendments Act - Rules of Construction",
        "citation": "42 U.S.C. \u00a7 12101 note",
        "jurisdiction": "US_Federal",
        "date_decided": "2008-09-25",
        "court": "United States Congress",
        "content": (
            "The definition of disability in this chapter shall be construed in favor of broad coverage of "
            "individuals under this chapter, to the maximum extent permitted by the terms of this chapter. "
            "An impairment that substantially limits one major life activity need not limit other major life "
            "activities in order to be considered a disability. An impairment that is episodic or in remission "
            "is a disability if it would substantially limit a major life activity when active. The "
            "determination of whether an impairment substantially limits a major life activity shall be made "
            "without regard to the ameliorative effects of mitigating measures such as medication, medical "
            "supplies, prosthetics, hearing aids, mobility devices, oxygen therapy, assistive technology, "
            "reasonable accommodations, or learned behavioral or adaptive neurological modifications. The use "
            "of ordinary eyeglasses or contact lenses shall be considered in determining whether an impairment "
            "substantially limits a major life activity."
        ),
        "headnotes": (
            "ADA Amendments Act broadens disability definition. Episodic conditions qualify. Mitigating measures "
            "generally not considered in disability determination."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    # ============================================================
    # 4. PRACTICE GUIDES (8 documents)
    # ============================================================

    documents.append({
        "doc_id": "guide-001",
        "doc_type": "practice_guide",
        "title": "Filing an Employment Discrimination Claim in California",
        "citation": "",
        "jurisdiction": "CA",
        "date_decided": "",
        "court": "",
        "content": (
            "Step 1: Document the discriminatory conduct. Maintain a contemporaneous log of incidents including "
            "dates, times, witnesses, and the specific conduct. Preserve all relevant communications including "
            "emails, text messages, and written correspondence. Step 2: Report through internal channels. File "
            "a formal written complaint with human resources or management following the employer's complaint "
            "procedure. Retain a copy of all written complaints and note the date of submission. Step 3: File "
            "a complaint with the California Civil Rights Department (formerly DFEH). A complaint must be filed "
            "within three years of the most recent discriminatory act. The CRD will investigate and attempt "
            "mediation. Step 4: Obtain a right-to-sue notice. If the CRD does not resolve the complaint, "
            "request an immediate right-to-sue notice to pursue the claim in court. Step 5: File a civil "
            "lawsuit. A lawsuit must be filed within one year of receiving the right-to-sue notice. Consider "
            "both state FEHA claims and federal Title VII claims if applicable. Remedies may include back pay, "
            "front pay, compensatory damages, punitive damages, attorney fees, and injunctive relief."
        ),
        "headnotes": (
            "Step-by-step guide for California employment discrimination claims. Covers documentation, internal "
            "reporting, CRD complaint filing, right-to-sue notice, and civil lawsuit procedures."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-002",
        "doc_type": "practice_guide",
        "title": "ADA Reasonable Accommodation Request Checklist",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Checklist for employees requesting reasonable accommodation under the ADA: 1. Identify the "
            "essential functions of the position that are affected by the disability. 2. Obtain medical "
            "documentation from a healthcare provider describing the functional limitations and suggested "
            "accommodations. 3. Submit a written accommodation request to the employer identifying the "
            "disability-related limitation and the specific accommodation requested. The request need not use "
            "the words reasonable accommodation or reference the ADA. 4. Participate in the interactive "
            "process in good faith. The interactive process is a mandatory dialogue between the employee and "
            "employer to identify effective accommodations. 5. Consider alternative accommodations if the "
            "requested accommodation would impose an undue hardship. Potential accommodations include modified "
            "work schedules, telework arrangements, ergonomic equipment, job restructuring, reassignment to "
            "vacant positions, and modified policies. 6. Document all communications related to the "
            "accommodation request. 7. If the employer denies the request, ask for a written explanation of "
            "the reasons for denial and the interactive process steps taken."
        ),
        "headnotes": (
            "Practical checklist for ADA accommodation requests. Covers documentation, interactive process "
            "participation, alternative accommodations, and denial response procedures."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-003",
        "doc_type": "practice_guide",
        "title": "Conducting Workplace Harassment Investigations",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Best practices for conducting workplace harassment investigations: 1. Promptness: Begin the "
            "investigation within 24-48 hours of receiving a complaint. Delays can expose the employer to "
            "liability. 2. Investigator selection: Choose an impartial investigator with no personal or "
            "professional relationship with the parties. Consider using an external investigator for complaints "
            "involving senior management. 3. Interim measures: Assess whether interim protective measures are "
            "needed, such as temporary reassignment, schedule changes, or no-contact directives. 4. Witness "
            "interviews: Interview the complainant, the accused, and all identified witnesses separately. "
            "Use open-ended questions and document responses verbatim where possible. 5. Document review: "
            "Collect and review all relevant documents, emails, text messages, and surveillance footage. "
            "6. Credibility assessment: Evaluate witness credibility based on consistency, corroboration, "
            "demeanor, motive, and plausibility. 7. Findings and recommendations: Prepare a written report "
            "documenting the investigation, findings of fact, credibility assessments, and recommended "
            "corrective action. 8. Follow-up: Monitor the workplace after the investigation to ensure the "
            "harassment has stopped and no retaliation occurs."
        ),
        "headnotes": (
            "Comprehensive guide to workplace harassment investigations. Covers investigator selection, "
            "interim measures, witness interviews, credibility assessment, and follow-up procedures."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-004",
        "doc_type": "practice_guide",
        "title": "FMLA Leave Administration Guide for Employers",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Key requirements for employers administering FMLA leave: 1. Eligibility: Employees are eligible "
            "if they have worked for the employer for at least 12 months, have worked at least 1,250 hours in "
            "the preceding 12 months, and work at a location with 50 or more employees within 75 miles. "
            "2. Notice requirements: When an employee requests FMLA leave, the employer must provide the "
            "employee with a notice of eligibility within five business days, along with a notice of rights "
            "and responsibilities. 3. Medical certification: Employers may require medical certification from "
            "the employee's healthcare provider to support the need for leave. The certification must be "
            "returned within 15 calendar days. 4. Designation: The employer must designate leave as FMLA-"
            "qualifying within five business days of having sufficient information. 5. Benefits continuation: "
            "Employers must maintain group health insurance coverage during FMLA leave on the same terms as if "
            "the employee continued to work. 6. Reinstatement: Upon return, employees must be restored to the "
            "same or an equivalent position with equivalent pay, benefits, and working conditions."
        ),
        "headnotes": (
            "Employer guide for FMLA administration. Covers eligibility requirements, notice obligations, "
            "medical certification, designation, benefits continuation, and reinstatement rights."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-005",
        "doc_type": "practice_guide",
        "title": "Drafting Employment Arbitration Agreements",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Key considerations for drafting enforceable employment arbitration agreements: 1. Mutual "
            "obligation: The agreement should require both the employer and employee to arbitrate covered "
            "claims. Courts are more likely to enforce mutual agreements. 2. Scope of covered claims: Clearly "
            "define which claims are subject to arbitration. Common carve-outs include workers compensation "
            "claims, unemployment insurance, and claims before administrative agencies. 3. Arbitrator selection: "
            "Provide for a neutral arbitrator selection process, such as selection from a panel provided by "
            "AAA or JAMS. 4. Discovery: Allow adequate discovery procedures, including document requests and "
            "at least one deposition per side. 5. Remedies: Ensure the arbitrator has authority to award all "
            "remedies available under applicable law, including compensatory damages, punitive damages, and "
            "attorney fees. 6. Cost allocation: The employer should bear the arbitration costs beyond what the "
            "employee would have paid in court filing fees. 7. Written decision: Require the arbitrator to "
            "issue a reasoned written award. 8. Consideration: Ensure adequate consideration, particularly "
            "for existing employees. Continued employment alone may not constitute sufficient consideration "
            "in all jurisdictions."
        ),
        "headnotes": (
            "Guide to drafting enforceable employment arbitration agreements. Covers mutuality, scope, "
            "arbitrator selection, discovery, remedies, cost allocation, and consideration requirements."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-006",
        "doc_type": "practice_guide",
        "title": "Section 1983 Civil Rights Litigation Primer",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Section 1983 provides a civil remedy against persons who, acting under color of state law, "
            "deprive others of federal constitutional or statutory rights. Key elements of a Section 1983 "
            "claim: 1. State action: The defendant must have acted under color of state law. Private actors "
            "are generally not liable unless they conspired with state actors or performed a traditional "
            "government function. 2. Constitutional violation: The plaintiff must identify a specific "
            "constitutional right that was violated. Common bases include Fourth Amendment (excessive force, "
            "unreasonable search), First Amendment (retaliation for speech), and Fourteenth Amendment (due "
            "process, equal protection). 3. Causation: The defendant's conduct must have been the proximate "
            "cause of the constitutional injury. 4. Qualified immunity: Individual government defendants may "
            "assert qualified immunity, which protects officials from liability unless the right was clearly "
            "established at the time of the conduct. 5. Municipal liability: Under Monell v. Department of "
            "Social Services, municipalities may be liable under Section 1983 only when the constitutional "
            "violation results from an official policy, custom, or practice."
        ),
        "headnotes": (
            "Primer on Section 1983 civil rights litigation. Covers state action, constitutional violation, "
            "causation, qualified immunity, and municipal liability under Monell."
        ),
        "practice_area": "civil_rights",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-007",
        "doc_type": "practice_guide",
        "title": "Responding to EEOC Charges of Discrimination",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Guide for employers responding to EEOC charges: 1. Preserve evidence: Upon receipt of a charge, "
            "immediately implement a litigation hold to preserve all relevant documents, emails, and electronic "
            "data. 2. Investigate internally: Conduct a thorough internal investigation before preparing the "
            "position statement. Interview relevant witnesses and review personnel files, performance records, "
            "and communications. 3. Draft position statement: The position statement should respond to each "
            "allegation in the charge, present the employer's legitimate, nondiscriminatory reasons for the "
            "challenged action, and provide supporting documentation. 4. Comparator analysis: Identify and "
            "document the treatment of similarly situated employees to demonstrate consistent application of "
            "policies. 5. Mediation: Consider participating in EEOC mediation, which may provide a faster and "
            "less expensive resolution. 6. Cooperation: Respond to EEOC requests for information promptly "
            "and completely. Failure to cooperate can result in adverse inferences. 7. Timeline: Position "
            "statements are typically due within 30 days of receiving the charge, though extensions may be "
            "requested."
        ),
        "headnotes": (
            "Employer guide for responding to EEOC charges. Covers evidence preservation, internal investigation, "
            "position statement preparation, comparator analysis, and mediation considerations."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "guide-008",
        "doc_type": "practice_guide",
        "title": "Workplace Retaliation Prevention Strategies",
        "citation": "",
        "jurisdiction": "US_Federal",
        "date_decided": "",
        "court": "",
        "content": (
            "Strategies for preventing workplace retaliation claims: 1. Training: Train all managers and "
            "supervisors to recognize and avoid retaliatory conduct. Emphasize that retaliation includes any "
            "materially adverse action that would dissuade a reasonable worker from making a complaint. "
            "2. Separation: When possible, separate the decision-making process for employment actions "
            "affecting a complainant from the individual accused of the underlying misconduct. 3. Documentation: "
            "Maintain thorough documentation of all employment decisions, including the business rationale for "
            "each decision. Contemporaneous documentation is more credible than after-the-fact justifications. "
            "4. Timing awareness: Be aware that close temporal proximity between a protected activity and an "
            "adverse action creates a strong inference of retaliation. If adverse action is warranted, document "
            "that the decision was made before the protected activity occurred or is based on independent "
            "factors. 5. Consistent treatment: Apply policies and performance standards consistently across "
            "all employees, regardless of whether they have engaged in protected activity. 6. No-retaliation "
            "reminders: After receiving a complaint, remind all involved parties of the anti-retaliation "
            "policy and document the reminder."
        ),
        "headnotes": (
            "Preventive strategies against retaliation claims. Covers training, decision-maker separation, "
            "documentation, timing awareness, consistent treatment, and anti-retaliation reminders."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    # ============================================================
    # 5. REGULATIONS (8 documents)
    # ============================================================

    documents.append({
        "doc_id": "reg-001",
        "doc_type": "regulation",
        "title": "EEOC Guidelines on Harassment",
        "citation": "29 C.F.R. \u00a7 1604.11",
        "jurisdiction": "US_Federal",
        "date_decided": "1980-11-10",
        "court": "Equal Employment Opportunity Commission",
        "content": (
            "Harassment on the basis of sex is a violation of section 703 of Title VII. Unwelcome sexual "
            "advances, requests for sexual favors, and other verbal or physical conduct of a sexual nature "
            "constitute sexual harassment when submission to such conduct is made either explicitly or "
            "implicitly a term or condition of an individual's employment, submission to or rejection of such "
            "conduct by an individual is used as the basis for employment decisions affecting such individual, "
            "or such conduct has the purpose or effect of unreasonably interfering with an individual's work "
            "performance or creating an intimidating, hostile, or offensive working environment. An employer "
            "is responsible for its acts and those of its agents and supervisory employees with respect to "
            "sexual harassment regardless of whether the specific acts complained of were authorized or even "
            "forbidden by the employer and regardless of whether the employer knew or should have known of "
            "their occurrence."
        ),
        "headnotes": (
            "EEOC defines sexual harassment as unwelcome sexual conduct that affects employment or creates "
            "hostile environment. Employers liable for supervisor harassment regardless of knowledge."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-002",
        "doc_type": "regulation",
        "title": "EEOC Enforcement Guidance on Reasonable Accommodation",
        "citation": "EEOC No. 915.002",
        "jurisdiction": "US_Federal",
        "date_decided": "2002-10-17",
        "court": "Equal Employment Opportunity Commission",
        "content": (
            "This enforcement guidance addresses the rights and responsibilities of employers and individuals "
            "with disabilities regarding reasonable accommodation under the ADA. An individual with a disability "
            "may request a reasonable accommodation at any time during the application process or during "
            "employment. The request does not need to be in writing, does not need to mention the ADA or use "
            "the phrase reasonable accommodation. The employer should respond expeditiously to a request for "
            "reasonable accommodation. Unnecessary delays in responding may result in a violation of the ADA. "
            "The interactive process requires both the employer and the employee to communicate in good faith "
            "to identify and implement an effective accommodation. Employers should consider the individual's "
            "preferred accommodation, but may offer an alternative accommodation that is equally effective. "
            "The employer is not required to provide the best accommodation or the accommodation preferred by "
            "the individual, as long as the accommodation provided is effective in meeting the needs of the "
            "individual."
        ),
        "headnotes": (
            "EEOC guidance on ADA reasonable accommodation. No formal request needed. Employer must respond "
            "promptly and engage in interactive process. Need not provide preferred accommodation if alternative is effective."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-003",
        "doc_type": "regulation",
        "title": "EEOC Guidance on National Origin Discrimination",
        "citation": "29 C.F.R. \u00a7 1606",
        "jurisdiction": "US_Federal",
        "date_decided": "1980-12-01",
        "court": "Equal Employment Opportunity Commission",
        "content": (
            "The EEOC guidelines define national origin discrimination broadly to include discrimination "
            "because of an individual's, or their ancestor's, place of origin, or because an individual has "
            "the physical, cultural, or linguistic characteristics of a national origin group. National origin "
            "discrimination also includes discrimination against a person who is associated with someone of a "
            "particular national origin, or who is a member of an organization identified with a particular "
            "national origin group. English-only rules are presumptively discriminatory unless the employer can "
            "show business necessity. When an employer has a legitimate business need for an English-only rule "
            "at certain times, it should inform employees of the general circumstances when speaking only in "
            "English is required and the consequences of violating the rule. Accent discrimination may "
            "constitute national origin discrimination if the individual's accent does not materially interfere "
            "with the ability to perform job duties."
        ),
        "headnotes": (
            "National origin discrimination includes ancestry, physical/cultural/linguistic characteristics, "
            "and association. English-only rules presumptively discriminatory. Accent discrimination may violate Title VII."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-004",
        "doc_type": "regulation",
        "title": "DOL FMLA Regulations - Serious Health Condition",
        "citation": "29 C.F.R. \u00a7 825.113",
        "jurisdiction": "US_Federal",
        "date_decided": "2009-01-16",
        "court": "Department of Labor",
        "content": (
            "A serious health condition entitling an employee to FMLA leave means an illness, injury, "
            "impairment, or physical or mental condition that involves inpatient care in a hospital, hospice, "
            "or residential medical care facility, or continuing treatment by a health care provider. "
            "Continuing treatment includes a period of incapacity of more than three consecutive full calendar "
            "days and subsequent treatment or period of incapacity relating to the same condition that also "
            "involves treatment two or more times by a health care provider within 30 days of the first day of "
            "incapacity, or treatment by a health care provider on at least one occasion which results in a "
            "regimen of continuing treatment. Chronic conditions requiring periodic treatment are also covered "
            "even when each episode of incapacity lasts fewer than three days. Pregnancy and prenatal care "
            "qualify as serious health conditions without meeting the three-day incapacity requirement."
        ),
        "headnotes": (
            "Defines serious health condition for FMLA. Includes inpatient care and continuing treatment. "
            "Chronic conditions and pregnancy covered. Three-day incapacity threshold for most conditions."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-005",
        "doc_type": "regulation",
        "title": "California CRD Complaint Investigation Procedures",
        "citation": "Cal. Code Regs. tit. 2, \u00a7 10005",
        "jurisdiction": "CA",
        "date_decided": "2020-01-01",
        "court": "California Civil Rights Department",
        "content": (
            "Upon receipt of a verified complaint alleging violations of the Fair Employment and Housing Act, "
            "the Department shall conduct an investigation. The investigation may include requests for "
            "information from the respondent, witness interviews, and review of relevant documents. The "
            "respondent shall provide a verified answer to the complaint within 30 days of service. The "
            "Department may attempt to resolve the complaint through conciliation, mediation, or persuasion. "
            "If the Department determines that sufficient evidence exists to establish a violation, it may "
            "file an accusation on behalf of the complainant before the Fair Employment and Housing Council "
            "or may issue a right-to-sue notice at the complainant's request. The complainant may request an "
            "immediate right-to-sue notice at any time after filing the complaint. The statute of limitations "
            "for filing a complaint with the Department is three years from the date of the alleged unlawful "
            "practice. This extended limitations period took effect on January 1, 2020."
        ),
        "headnotes": (
            "CRD investigation procedures for FEHA complaints. 30-day response period. Three-year statute "
            "of limitations. Complainant may request immediate right-to-sue notice."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-006",
        "doc_type": "regulation",
        "title": "EEOC Guidelines on Employee Selection Procedures",
        "citation": "29 C.F.R. \u00a7 1607",
        "jurisdiction": "US_Federal",
        "date_decided": "1978-08-25",
        "court": "Equal Employment Opportunity Commission",
        "content": (
            "These guidelines apply to tests and other selection procedures which are used as a basis for any "
            "employment decision. A selection rate for any group which is less than four-fifths (or eighty "
            "percent) of the rate for the group with the highest rate will generally be regarded by the Federal "
            "enforcement agencies as evidence of adverse impact. Where the user's evidence concerning the "
            "impact of a selection procedure indicates adverse impact, the enforcement agencies will look to "
            "whether the user has validated the selection procedure in accord with these guidelines. To "
            "establish the content validity of a selection procedure, a user should show that the behavior "
            "measured by the procedure is a representative sample of the behavior of the job in question. "
            "Criterion-related validity involves establishing a statistical relationship between scores on "
            "the selection procedure and job performance measures. Construct validity involves identifying "
            "the psychological trait measured by the procedure and demonstrating that the trait is important "
            "for job performance."
        ),
        "headnotes": (
            "Uniform Guidelines on Employee Selection. Four-fifths rule for adverse impact. Requires validation "
            "of selection procedures showing adverse impact. Three types: content, criterion, construct validity."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-007",
        "doc_type": "regulation",
        "title": "DOL Regulations on FMLA Employer Notice Requirements",
        "citation": "29 C.F.R. \u00a7 825.300",
        "jurisdiction": "US_Federal",
        "date_decided": "2009-01-16",
        "court": "Department of Labor",
        "content": (
            "Employers covered by the FMLA are required to post and keep posted on their premises, in "
            "conspicuous places where employees and applicants for employment are employed, a notice explaining "
            "the Act's provisions and providing information concerning the procedures for filing complaints of "
            "violations of the Act with the Wage and Hour Division. When an employee requests FMLA leave or "
            "the employer acquires knowledge that an employee's leave may be for an FMLA-qualifying reason, "
            "the employer must notify the employee of the employee's eligibility to take FMLA leave within "
            "five business days, absent extenuating circumstances. The eligibility notice must state whether "
            "the employee is eligible for FMLA leave and if the employee is not eligible, at least one reason "
            "why the employee is not eligible. Within five business days after the employee has submitted the "
            "required certification or the employer has sufficient information to determine whether the leave "
            "qualifies as FMLA leave, the employer must notify the employee whether the leave will be "
            "designated as FMLA leave."
        ),
        "headnotes": (
            "FMLA employer notice requirements. Must post FMLA notice. Five business days to notify employee "
            "of eligibility. Five business days to designate leave as FMLA-qualifying."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "reg-008",
        "doc_type": "regulation",
        "title": "EEOC Guidance on Disability-Related Inquiries and Medical Examinations",
        "citation": "EEOC No. 915.002",
        "jurisdiction": "US_Federal",
        "date_decided": "2000-07-27",
        "court": "Equal Employment Opportunity Commission",
        "content": (
            "The ADA places strict limits on when employers may make disability-related inquiries or require "
            "medical examinations. Before a conditional offer of employment, employers may not ask questions "
            "likely to elicit information about a disability or require medical examinations. After making a "
            "conditional offer but before employment begins, employers may make disability-related inquiries "
            "and conduct medical examinations as long as all entering employees in the same job category are "
            "subjected to the same inquiries and examinations. During employment, disability-related inquiries "
            "and medical examinations must be job-related and consistent with business necessity. This standard "
            "is met when the employer has a reasonable belief, based on objective evidence, that an employee's "
            "ability to perform essential job functions will be impaired by a medical condition, or that an "
            "employee will pose a direct threat due to a medical condition. Employers should not ask broad "
            "questions about medical conditions, medications, or prior workers compensation claims."
        ),
        "headnotes": (
            "ADA limits disability inquiries at three stages: pre-offer (prohibited), post-offer/pre-employment "
            "(permitted if uniform), during employment (job-related and consistent with business necessity)."
        ),
        "practice_area": "employment",
        "status": "good_law"
    })

    # ============================================================
    # 6. ADDITIONAL TORT/CONTRACT CASES (5 documents)
    # ============================================================

    documents.append({
        "doc_id": "case-040",
        "doc_type": "case_law",
        "title": "Palsgraf v. Long Island Railroad Co.",
        "citation": "248 N.Y. 339 (1928)",
        "jurisdiction": "NY",
        "date_decided": "1928-05-29",
        "court": "New York Court of Appeals",
        "content": (
            "The New York Court of Appeals, in an opinion by Chief Judge Cardozo, held that a defendant owes "
            "a duty of care only to those plaintiffs who are within the reasonably foreseeable zone of danger. "
            "The plaintiff was standing on a train platform when railroad employees helped a passenger board a "
            "moving train. The passenger dropped a package, which contained fireworks that exploded, causing "
            "scales at the other end of the platform to fall and injure the plaintiff. The court held that "
            "the railroad's negligence in assisting the passenger was not actionable by the plaintiff because "
            "the harm to her was not a foreseeable consequence of the railroad's conduct. Cardozo wrote that "
            "the risk reasonably to be perceived defines the duty to be obeyed, and risk imports relation. "
            "Judge Andrews dissented, arguing that every person owes a duty to the world at large not to "
            "engage in negligent conduct, and that proximate cause should be the limiting factor rather than "
            "duty. This case remains foundational in tort law for establishing the foreseeability requirement "
            "in duty analysis."
        ),
        "headnotes": (
            "Duty of care extends only to foreseeable plaintiffs within the zone of danger. Risk reasonably "
            "perceived defines the duty owed. Foundational case for foreseeability in negligence."
        ),
        "practice_area": "tort",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-041",
        "doc_type": "case_law",
        "title": "Hadley v. Baxendale",
        "citation": "9 Exch. 341, 156 Eng. Rep. 145 (1854)",
        "jurisdiction": "US_Federal",
        "date_decided": "1854-02-23",
        "court": "Court of Exchequer",
        "content": (
            "The Court of Exchequer established the foundational rule for consequential damages in breach of "
            "contract cases. The plaintiffs operated a mill that was shut down because of a broken crankshaft. "
            "They hired the defendants to deliver the broken shaft to the manufacturer for use as a pattern "
            "for a new one. The defendants delayed delivery, resulting in extended downtime and lost profits "
            "for the plaintiffs. The court held that damages for breach of contract should be limited to those "
            "that arise naturally from the breach itself, according to the usual course of things, or those "
            "that may reasonably be supposed to have been in the contemplation of both parties at the time of "
            "contracting as the probable result of the breach. Because the defendants did not know that the "
            "mill was idle pending the delivery, the lost profits were not recoverable. This decision "
            "established the foreseeability limitation on consequential damages that remains a cornerstone "
            "of contract law."
        ),
        "headnotes": (
            "Contract damages limited to those naturally arising from breach or reasonably contemplated at "
            "time of contracting. Lost profits not recoverable if not foreseeable by breaching party."
        ),
        "practice_area": "contract",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-042",
        "doc_type": "case_law",
        "title": "Alice Corp. v. CLS Bank International",
        "citation": "573 U.S. 208 (2014)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "2014-06-19",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that claims directed to the abstract idea of intermediated settlement "
            "are not patentable under 35 U.S.C. section 101, even when implemented on a computer. The Court "
            "applied a two-step framework: first, determine whether the claims are directed to a patent-"
            "ineligible concept such as an abstract idea; second, if so, examine the claim elements "
            "individually and as an ordered combination to determine whether they contain an inventive concept "
            "sufficient to transform the abstract idea into a patent-eligible application. The Court found "
            "that using a generic computer to perform the abstract idea of intermediated settlement did not "
            "add significantly more than the abstract idea itself. The decision significantly impacted software "
            "patent eligibility and led to the invalidation of numerous software-related patents under what "
            "became known as the Alice framework."
        ),
        "headnotes": (
            "Abstract ideas implemented on generic computers are not patent-eligible. Two-step Alice framework: "
            "identify abstract idea, then determine if claims add inventive concept."
        ),
        "practice_area": "ip",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-043",
        "doc_type": "case_law",
        "title": "BMW of North America v. Gore",
        "citation": "517 U.S. 559 (1996)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "1996-05-20",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court established constitutional guideposts for evaluating the reasonableness of "
            "punitive damages awards under the Due Process Clause of the Fourteenth Amendment. The Court "
            "identified three guideposts: first, the degree of reprehensibility of the defendant's conduct, "
            "which is the most important indicator; second, the ratio between the punitive damages award and "
            "the actual or potential harm suffered by the plaintiff; and third, the difference between the "
            "punitive damages awarded and the civil or criminal sanctions that could be imposed for comparable "
            "misconduct. The Court reversed a two-million-dollar punitive damages award against BMW for "
            "failing to disclose that a new car had been repainted, finding that the ratio between the "
            "punitive award and the compensatory damages of four thousand dollars was grossly excessive. While "
            "the Court declined to draw a bright line ratio, it suggested that few awards exceeding a "
            "single-digit ratio would satisfy due process."
        ),
        "headnotes": (
            "Due Process limits punitive damages. Three guideposts: reprehensibility, ratio to compensatory "
            "damages, comparison to civil/criminal penalties. Single-digit ratio generally expected."
        ),
        "practice_area": "tort",
        "status": "good_law"
    })

    documents.append({
        "doc_id": "case-044",
        "doc_type": "case_law",
        "title": "Carpenter v. United States",
        "citation": "585 U.S. 296 (2018)",
        "jurisdiction": "US_Supreme_Court",
        "date_decided": "2018-06-22",
        "court": "Supreme Court of the United States",
        "content": (
            "The Supreme Court held that the government's acquisition of historical cell-site location "
            "information from a wireless carrier constitutes a search under the Fourth Amendment, requiring "
            "a warrant supported by probable cause. The Court found that cell phone location data provides an "
            "intimate window into a person's life, revealing not only movements but also familial, political, "
            "professional, religious, and intimate associations. Chief Justice Roberts wrote that individuals "
            "maintain a legitimate expectation of privacy in the record of their physical movements as captured "
            "through cell-site location information. The Court rejected the government's argument that the "
            "third-party doctrine applied because subscribers voluntarily convey location data to their "
            "carriers, holding that cell phone location data is qualitatively different from telephone numbers "
            "or bank records because it provides a comprehensive chronicle of the user's past movements."
        ),
        "headnotes": (
            "Government acquisition of historical cell-site location information is a Fourth Amendment search "
            "requiring a warrant. Third-party doctrine does not apply to cell location data."
        ),
        "practice_area": "criminal",
        "status": "good_law"
    })

    # Write to CSV
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legal-documents.csv")

    fieldnames = [
        "doc_id", "doc_type", "title", "citation", "jurisdiction",
        "date_decided", "court", "content", "headnotes", "practice_area", "status"
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(documents)

    print(f"Generated {len(documents)} legal documents -> {output_file}")

    # Print summary
    from collections import Counter
    type_counts = Counter(d["doc_type"] for d in documents)
    status_counts = Counter(d["status"] for d in documents)
    area_counts = Counter(d["practice_area"] for d in documents)

    print(f"\nBy document type:")
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    print(f"\nBy status:")
    for s, c in status_counts.most_common():
        print(f"  {s}: {c}")

    print(f"\nBy practice area:")
    for a, c in area_counts.most_common():
        print(f"  {a}: {c}")


if __name__ == "__main__":
    generate_legal_data()