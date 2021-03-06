
import pandas as pd
import plgspl.questions as qs
from plgspl.types import PDF
import os
import json
from plgspl.cfg import get_cfg


def to_pdf(info_json, manual_csv, file_dir=None):
    submissions = dict()
    config = qs.AssignmentConfig()

    # load the raw assignment config file
    cfg = json.load(open(info_json))
    out_file = cfg.get("title", "assignment").replace(" ", "_")
    zones = cfg['zones']
    print(f'Parsing config for {out_file}...')
    for z in zones:
        for i, raw_q in enumerate(z['questions']):
            parts = raw_q['parts'] if 'parts' in raw_q else []
            files = set(raw_q['files']) if 'files' in raw_q else set()
            if 'id' not in raw_q:
                vs = list(map(lambda q: q['id'], raw_q['alternatives']))
                q = qs.QuestionInfo(vs[0], i + 1,
                                    variants=vs, number_choose=raw_q['numberChoose'],
                                    parts=parts, expected_files=files)
            else:
                q = qs.QuestionInfo(
                    raw_q['id'], i + 1, parts=parts, expected_files=files)
            config.add_question(q)
    print(
        f'Parsed config. Created {config.get_question_count()} questions and {config.get_variant_count()} variants.', end='\n\n')

    # iterate over the rows of the csv and parse the data
    print(
        f'Parsing submissions from {manual_csv} and provided file directory (if any)')
    manual = pd.read_csv(manual_csv)
    for i, m in manual.iterrows():
        uid_full = m.get('uid', m.get('UID'))
        uid = str(uid_full).split("@", 1)[0]

        qid = m['qid']
        sid = m['submission_id']

        submission = submissions.get(uid)
        if not submission:
            submission = qs.Submission(uid)
            submissions[uid] = submission
        q = config.get_question(qid)
        if not q:
            continue

        # look for any files related to this question submission
        fns = []
        if file_dir:
            for fn in os.listdir(file_dir):
                # if it has the student id, and the qid_sid pair, count it as acceptable
                if fn.find(uid_full) > -1 and fn.find(f'{qs.escape_qid(qid)}_{sid}') > -1 and qs.parse_filename(fn, qid) in q.expected_files:
                    fns.append(os.path.join(file_dir, fn))
                    q.add_file(os.path.join(file_dir, fn))

        submission.add_student_question(
            qs.StudentQuestion(q, m['params'], m['true_answer'],
                               m['submitted_answer'], m['partial_scores'],
                               qs.StudentFileBundle(fns, qid), qid))
    print(f'Created {len(submissions)} submission(s)..')

    pdf = PDF()

    def pdf_output(pdf, name):
        pdf.output(os.path.join(os.getcwd(), f'{out_file}_{name}.pdf'))

    prev = 1
    expected_pages = 0
    template_submission = None
    missing_questions = []
    for i, (_, v) in enumerate(submissions.items()):
        v: qs.Submission
        # print(f'Printing out {v.uid}\'s submission to a pdf')
        start_page = pdf.page_no()
        v.render_submission(
            pdf, config, template_submission=template_submission)
        if i == 0:
            sample_pdf = PDF()
            v.render_submission(sample_pdf, config, True)
            template_submission = v
            pdf_output(sample_pdf, "sample")
            expected_pages = sample_pdf.page_no()
            max_submissions = get_cfg('gs', 'pagesPerPDF') / expected_pages
            if max_submissions < 1:
                print('Cannot create submissions given the current max page constraint.')
                print('Please adjust your defaults.')
                exit(1)
            max_submissions = int(max_submissions)
        diff = pdf.page_no() - start_page

        if diff < expected_pages:
            missing_questions.append(v.uid)
        elif diff > expected_pages:
            print(
                f'Submission {i}, {v.uid} exceeds the sample template. Please make sure that the first submission is complete')
            exit(1)
        while pdf.page_no() - start_page < expected_pages:
            pdf.add_page()
            pdf.cell(0, 20, f'THIS IS A BLANK PAGE', ln=1, align='C')

        if i != 0 and i % max_submissions == 0:
            pdf_output(pdf, f'{i - max_submissions + 1}-{i + 1}')
            prev = i + 1
            pdf = PDF()

    if prev < len(submissions) or len(submissions) == 1:
        pdf_output(pdf, f'{prev}-{len(submissions)}')
    if len(missing_questions) > 0:
        print(f'{len(missing_questions)} submissions are missing question submissions. Please make sure to manually pair them in gradescope!', missing_questions, sep="\n")

    json.dump({k: v.list_questions(config)
               for k, v in submissions.items()}, open(f'{out_file}_qmap.json', 'w'))
