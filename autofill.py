import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from winotify import Notification

BASE_DIR = Path(__file__).resolve().parent
PROFILE_FILE = BASE_DIR / "profile.json"
DEBUGGING_URL = "http://127.0.0.1:9222"

# Maps question wording to profile keys. Specific rules precede general rules.
FIELD_RULES = [
    (r"\b(alternate email|secondary email)\b", ["alternate_email"]),
    (r"\b(email address|e-mail address|e-mail|email|mail id)\b", ["email"]),
    (r"\b(alternate phone|secondary phone)\b", ["alternate_phone"]),
    (r"\b(phone number|mobile number|contact number|telephone|phone|mobile|contact)\b", ["phone"]),
    (r"\b(enrollment number|enrolment number|enrollment no\.?|enrolment no\.?|student id|student number|registration number|registration no\.?)\b", ["enrollment_number", "enrollment_no", "student_id"]),
    (r"\b(college name|institution name|college|institution)\b", ["college"]),
    (r"\b(university name|university)\b", ["university"]),
    (r"\b(department|specialization|specialisation)\b", ["department", "branch"]),
    (r"\b(branch|stream|speciality|specialty)\b", ["branch"]),
    (r"\b(current semester|semester)\b", ["semester"]),
    (r"\b(current year|year of study|academic year)\b", ["current_year"]),
    (r"\b(graduation year|year of graduation|year of passing|passing year)\b", ["graduation_year"]),
    (r"\b(10th percentage|class 10 percentage|10th marks|class 10 marks)\b", ["tenth_percentage"]),
    (r"\b(12th percentage|class 12 percentage|12th marks|class 12 marks)\b", ["twelfth_percentage"]),
    (r"\b(cgpa|cumulative grade point average)\b", ["cgpa"]),
    (r"\b(first name|given name)\b", ["first_name"]),
    (r"\b(last name|surname|family name)\b", ["last_name"]),
    (r"\b(full name|candidate name|applicant name|your name|name)\b", ["full_name"]),
    (r"\b(linkedin profile|linkedin url|linkedin)\b", ["linkedin_url"]),
    (r"\b(github profile|github url|github)\b", ["github_url"]),
    (r"\b(portfolio url|portfolio website|portfolio)\b", ["portfolio_url"]),
    (r"\b(city|town)\b", ["city"]),
    (r"\b(state|province)\b", ["state"]),
    (r"\b(country)\b", ["country"]),
    (r"\b(preferred role|desired role|job role|position applying for)\b", ["preferred_role"]),
    (r"\b(experience level|years of experience)\b", ["experience_level"]),
    (r"\b(technical skills|programming languages|skills|technologies)\b", ["skills"]),
    (r"\b(projects|project experience|describe your projects)\b", ["project_experience"]),
    (r"\b(internship experience|internships|work experience)\b", ["internship_experience"]),
    (r"\b(leadership|leadership experience|positions of responsibility)\b", ["leadership"]),
    (r"\b(achievements|academic achievements|awards)\b", ["achievements"]),
    (r"\b(additional information|anything else|other details)\b", ["additional_information"]),
]

OTHER_PERSON_RE = re.compile(
    r"\b(parent|father|mother|guardian|placement officer|emergency contact|"
    r"reference person|friend|spouse|sibling|brother|sister)\b",
    re.IGNORECASE,
)

GENERIC_ANSWER_RULES = [
    (r"\b(tell me about yourself|introduce yourself|brief introduction)\b", "introduction"),
    (r"\b(why (are you )?interested|why do you want to join|why this (role|company)|reason for applying|why are you applying)\b", "motivation"),
    (r"\b(what are your strengths|key strengths|your strengths)\b", "strengths"),
    (r"\b(why should we (hire|select|choose) you|why are you a good fit)\b", "fit"),
    (r"\b(career goals|long.?term goals|professional goals|where do you see yourself)\b", "goals"),
    (r"\b(what can you contribute|how can you contribute|value can you add)\b", "contribution"),
    (r"\b(describe your skills|technical skills|your skill set)\b", "skills_summary"),
    (r"\b(teamwork|working in a team|collaborat(e|ion|ing))\b", "teamwork"),
    (r"\b(learning new (skills|technologies)|how do you learn|learning approach)\b", "learning"),
]


def notify(title, message):
    try:
        Notification(
            app_id="Google Forms Autofill",
            title=title,
            msg=message[:250],
            duration="long",
        ).show()
    except Exception as error:
        print(f"Desktop notification unavailable: {error}")


def load_profile():
    with PROFILE_FILE.open("r", encoding="utf-8") as file:
        profile = json.load(file)
    if not isinstance(profile, dict):
        raise ValueError("profile.json must contain a JSON object.")
    return profile


def is_google_form_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "forms.gle"
        or (host == "docs.google.com" and parsed.path.startswith("/forms/"))
    )


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def usable_value(profile, keys):
    for key in keys:
        value = profile.get(key)
        if value not in (None, "") and not isinstance(value, (list, dict)):
            return key, str(value)
    return None, None


def question_to_value(question_text, profile):
    q = norm(question_text)
    if OTHER_PERSON_RE.search(q):
        return None, None, "skip"

    if re.search(r"\b(first name|given name)\b", q):
        key, value = usable_value(profile, ["first_name"])
        return key, value, "profile"
    if re.search(r"\b(last name|surname|family name)\b", q):
        key, value = usable_value(profile, ["last_name"])
        return key, value, "profile"

    for pattern, keys in FIELD_RULES:
        if re.search(pattern, q, re.IGNORECASE):
            key, value = usable_value(profile, keys)
            if key:
                return key, value, "profile"
            break

    # Do not guess factual, yes/no, eligibility, personal-status or upload answers.
    factual = re.search(
        r"\b(have you|did you|do you have|are you|will you|received|shortlisting|"
        r"shortlist|enrollment|enrolment|registration number|student id|upload|"
        r"attach|screenshot|date of birth|dob|cgpa|percentage|marks|salary|"
        r"notice period|years of experience|work authorization|authorized to work|"
        r"backlogs|arrears|bond|relocate|willing to travel|gender|disability|"
        r"veteran|criminal record)\b", q
    )
    if factual:
        return None, None, "skip"

    for pattern, answer_type in GENERIC_ANSWER_RULES:
        if re.search(pattern, q, re.IGNORECASE):
            skills = profile.get("skills") or "problem-solving and software development"
            degree = profile.get("degree", "")
            branch = profile.get("branch", "")
            education = " ".join(x for x in [degree, branch] if x)
            education_sentence = f"My academic background is in {education}. " if education else ""
            if answer_type == "introduction":
                return "generic:introduction", (
                    f"I am Aayush Mittal, an early-career technology candidate. "
                    f"{education_sentence}My skills include {skills}. "
                    "I enjoy learning new technologies, solving practical problems, "
                    "and building useful software. I am keen to keep improving through "
                    "hands-on work and feedback."
                ), "generic"
            if answer_type == "motivation":
                role = profile.get("preferred_role") or "this opportunity"
                return "generic:motivation", (
                    f"I am interested in {role} because it would let me apply my current "
                    "skills, learn from experienced colleagues, and contribute to practical "
                    "work. I value continuous learning, clear communication, and careful problem-solving."
                ), "generic"
            if answer_type == "strengths":
                return "generic:strengths", (
                    "My strengths include problem-solving, persistence, willingness to learn, "
                    "and breaking unfamiliar tasks into manageable steps. I value feedback and "
                    "try to communicate progress clearly."
                ), "generic"
            if answer_type == "fit":
                return "generic:fit", (
                    f"I can bring a learning mindset, careful problem-solving, and skills in {skills}. "
                    "I am prepared to accept feedback, work responsibly, and keep improving while "
                    "contributing to the team's goals."
                ), "generic"
            if answer_type == "goals":
                return "generic:goals", (
                    "My goal is to strengthen my technical fundamentals, gain practical experience, "
                    "and gradually take ownership of more complex tasks. I want to become a dependable "
                    "professional who delivers useful, high-quality work."
                ), "generic"
            if answer_type == "contribution":
                return "generic:contribution", (
                    f"I can contribute a willingness to learn, careful problem-solving, and my current "
                    f"skills in {skills}. I would first understand the team's needs, communicate clearly, "
                    "and deliver work in manageable, testable steps."
                ), "generic"
            if answer_type == "skills_summary":
                return "generic:skills_summary", (
                    f"My current skills include {skills}. I am improving them through practice and "
                    "project work, and I am open to learning tools required by the role."
                ), "generic"
            if answer_type == "teamwork":
                return "generic:teamwork", (
                    "I approach teamwork by listening to others, clarifying responsibilities, sharing "
                    "progress, and asking for help early when needed. I value constructive feedback "
                    "and focus on the team's shared outcome."
                ), "generic"
            if answer_type == "learning":
                return "generic:learning", (
                    "I start by understanding the fundamentals, practise with a small example, and then "
                    "apply the concept to a practical task. I use documentation, test my work, and record "
                    "what I learned so I can improve."
                ), "generic"

    # User-specified answer map: exact question keyword -> answer.
    custom_answers = profile.get("question_answers", {})
    if isinstance(custom_answers, dict):
        for question_key, answer in custom_answers.items():
            if question_key and answer not in (None, "") and norm(question_key) in q:
                return f"custom:{question_key}", str(answer), "custom"

    return None, None, "skip"


def get_question_text(question):
    for selector in (".M7eMe", "[role='heading']", ".HoXoMd"):
        try:
            loc = question.locator(selector).first
            if loc.count() and loc.is_visible():
                text = loc.inner_text(timeout=1200).strip()
                if text:
                    return text
        except Exception:
            pass
    try:
        return question.inner_text(timeout=1200).strip()
    except Exception:
        return ""


def controls_for(question):
    return question.locator(
        'input:not([type="hidden"]):not([type="submit"]), textarea, [role="radio"], '
        '[role="checkbox"], [role="listbox"]'
    )


def fill_text(question, value):
    loc = question.locator(
        'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):'
        'not([type="file"]):not([type="submit"]), textarea'
    )
    candidates = []
    for i in range(loc.count()):
        el = loc.nth(i)
        try:
            if not el.is_visible() or not el.is_enabled():
                continue
            if el.get_attribute("readonly") is not None:
                continue
            tag = el.evaluate("(e) => e.tagName.toLowerCase()")
            typ = (el.get_attribute("type") or "text").lower()
            if tag == "textarea" or typ in {"text", "email", "tel", "number", "url", "date"}:
                candidates.append(el)
        except Exception:
            pass
    if len(candidates) != 1:
        return False
    candidates[0].fill(value, timeout=2500)
    return True


def visible_option_texts(question):
    texts = []
    # Google Forms commonly exposes labels for options.
    for selector in ("label", "[role='radio']", "[role='checkbox']", "[role='option']"):
        loc = question.locator(selector)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    text = norm(el.inner_text(timeout=700))
                    if text and text not in texts:
                        texts.append(text)
            except Exception:
                pass
    return texts


def normalize_option_answer(question_text, desired_answer):
    """
    Convert known profile values into the labels commonly used by this form.
    This is intentionally limited to clear, deterministic mappings.
    """
    q = norm(question_text)
    answer = norm(str(desired_answer))

    if re.search(r"\b(branch|stream|speciali[sz]ation)\b", q):
        branch_map = {
            "robotics and artificial intelligence": ["B.Tech R&AI", "B.Tech RAI", "R&AI"],
            "robotics & artificial intelligence": ["B.Tech R&AI", "B.Tech RAI", "R&AI"],
            "computer science and engineering": ["B.Tech CSE", "CSE"],
            "artificial intelligence and machine learning": ["B.Tech AIML", "AIML"],
            "artificial intelligence and data science": ["B.Tech AIDS", "AIDS"],
        }
        for key, labels in branch_map.items():
            if answer == key:
                return labels

    if re.search(r"\b(batch|graduation year|passing year|year of graduation)\b", q):
        year = re.search(r"\b(20\d{2})\b", answer)
        if year:
            return [year.group(1)]

    if re.search(r"\b(shortlisting mail|shortlisting email|received.*mail)\b", q):
        if answer in {"yes", "true", "received"}:
            return ["Yes"]
        if answer in {"no", "false", "not received"}:
            return ["No"]

    return [str(desired_answer).strip()]


def choose_option(question, desired_answer, question_text=""):
    wanted_options = [norm(x) for x in normalize_option_answer(question_text, desired_answer)]
    if not any(wanted_options):
        return False

    def matches(label):
        label = norm(label)
        # Exact match first. Also allow a clear containment match for labels
        # such as "B.Tech R&AI" versus "R&AI", but not ambiguous matches.
        return any(label == wanted or (len(wanted) >= 4 and wanted in label) for wanted in wanted_options)

    # Native select element.
    selects = question.locator("select")
    if selects.count() == 1 and selects.first.is_visible():
        select = selects.first
        options = select.locator("option")
        matches_found = []
        for i in range(options.count()):
            opt = options.nth(i)
            label = norm(opt.inner_text())
            value = opt.get_attribute("value") or ""
            if label and matches(label):
                matches_found.append(value or label)
        if len(matches_found) == 1:
            select.select_option(matches_found[0])
            return True

    # Google Forms radio/checkbox labels. Prefer the actual role element.
    candidates = []
    for selector in ('[role="radio"]', '[role="checkbox"]', 'label'):
        loc = question.locator(selector)
        for i in range(loc.count()):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                label = norm(el.inner_text(timeout=700))
                if label and matches(label):
                    candidates.append((label, el))
            except Exception:
                pass

    # De-duplicate by visible label. Duplicate DOM wrappers for the same option
    # should not make an otherwise unique answer look ambiguous.
    unique = {}
    for label, element in candidates:
        unique.setdefault(label, element)

    if len(unique) == 1:
        try:
            next(iter(unique.values())).click(timeout=2000)
            return True
        except Exception:
            pass

    # Google Forms dropdown: click listbox, inspect popup options, and select only
    # if there is exactly one match.
    listbox = question.locator('[role="listbox"]').first
    try:
        if listbox.count() and listbox.is_visible():
            listbox.click()
            options = question.page.locator('[role="option"]')
            found = []
            for i in range(options.count()):
                opt = options.nth(i)
                try:
                    if opt.is_visible() and matches(opt.inner_text(timeout=700)):
                        found.append(opt)
                except Exception:
                    pass
            if len(found) == 1:
                found[0].click()
                return True
            question.page.keyboard.press("Escape")
    except Exception:
        pass

    return False


def find_file_for_question(question_text, profile):
    uploads = profile.get("file_uploads", {})
    if not isinstance(uploads, dict):
        return None

    q = norm(question_text)
    for keyword, path_value in uploads.items():
        if not keyword or not path_value:
            continue

        key_norm = norm(keyword)
        # Permit common aliases for upload prompts without guessing which file to use.
        alias_match = (
            key_norm in q
            or ("shortlisting" in key_norm and ("mail" in q or "screenshot" in q))
            or ("mail" in key_norm and ("screenshot" in q or "received by company" in q))
            or ("resume" in key_norm and ("resume" in q or "cv" in q))
        )
        if alias_match:
            path = Path(str(path_value)).expanduser()
            if not path.is_absolute():
                path = BASE_DIR / path
            if path.is_file():
                return path
    return None


def handle_file_upload(question, question_text, profile):
    path = find_file_for_question(question_text, profile)
    if not path:
        return False, "No matching file path configured in profile.json"

    file_input = question.locator('input[type="file"]')
    if file_input.count() != 1:
        return False, "File input not found or ambiguous"

    file_input.set_input_files(str(path), timeout=3000)
    return True, str(path)


def main():
    try:
        profile = load_profile()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Cannot read profile.json: {error}")
        notify("Autofill error", "Check profile.json.")
        return

    url = input("Paste your Google Forms URL: ").strip()
    if not is_google_form_url(url):
        print("Please enter a valid HTTPS Google Forms URL.")
        return

    filled_profile, filled_generic, filled_choice, filled_files = [], [], [], []
    skipped, failed = [], []

    try:
        with sync_playwright() as playwright:
            print(f"Connecting to Brave at {DEBUGGING_URL}...")
            browser = playwright.chromium.connect_over_cdp(DEBUGGING_URL)
            if not browser.contexts:
                print("No browser context found. Start debugging-enabled Brave first.")
                return

            context = browser.contexts[0]
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            print("\nForm opened in a new tab in the connected Brave window.")
            input("Wait for the form to finish loading, then press Enter here...")

            questions = page.locator('[role="listitem"]')
            print(f"\nFound {questions.count()} question containers.")

            for index in range(questions.count()):
                question = questions.nth(index)
                try:
                    if not question.is_visible():
                        continue
                    question_text = get_question_text(question)
                    if not question_text:
                        skipped.append("Unreadable question")
                        continue

                    # File upload is never guessed; only configured local files are used.
                    file_inputs = question.locator('input[type="file"]')
                    if file_inputs.count():
                        ok, detail = handle_file_upload(question, question_text, profile)
                        if ok:
                            filled_files.append(question_text[:70])
                            print(f"FILE SELECTED: {question_text[:70]} <- {detail}")
                        else:
                            skipped.append(question_text[:100])
                            print(f"SKIPPED FILE UPLOAD: {question_text[:70]} ({detail})")
                        continue

                    key, value, source = question_to_value(question_text, profile)

                    # For factual choices, use only a profile/custom answer.
                    if key is None:
                        skipped.append(question_text[:100])
                        print(f"SKIPPED (no safe answer): {question_text[:80]}")
                        continue

                    # Radio/select/checkbox handling; only exact or unambiguous matching option.
                    has_choices = (
                        question.locator('[role="radio"], [role="checkbox"], [role="listbox"], select').count() > 0
                    )
                    if has_choices:
                        if choose_option(question, value, question_text):
                            filled_choice.append(key)
                            print(f"CHOICE SELECTED: {key} = {value}")
                        else:
                            skipped.append(question_text[:100])
                            print(f"SKIPPED CHOICE (no unique matching option): {question_text[:80]}")
                        continue

                    try:
                        did_fill = fill_text(question, value)
                    except Exception as error:
                        failed.append(key)
                        print(f"FAILED: {key} — {error}")
                        continue

                    if not did_fill:
                        # Some forms use buttons/labels instead of native inputs.
                        if choose_option(question, value, question_text):
                            filled_choice.append(key)
                            print(f"CHOICE SELECTED: {key} = {value}")
                        else:
                            skipped.append(question_text[:100])
                            print(f"SKIPPED (unsupported/ambiguous input): {question_text[:80]}")
                    elif source == "generic":
                        filled_generic.append(key)
                        print(f"GENERIC DRAFT: {key} | {question_text[:65]}")
                    else:
                        filled_profile.append(key)
                        print(f"FILLED FROM PROFILE: {key} | {question_text[:65]}")

                except Exception as error:
                    failed.append(f"Question {index + 1}")
                    print(f"FAILED: question {index + 1} — {error}")

            print("\n========== AUTOFILL REPORT ==========")
            print(f"Filled from profile: {len(filled_profile)}")
            print(f"Generic drafts added: {len(filled_generic)}")
            print(f"Radio/dropdown/checkbox choices: {len(filled_choice)}")
            print(f"Files selected: {len(filled_files)}")
            print(f"Skipped: {len(skipped)}")
            print(f"Failed: {len(failed)}")

            if skipped:
                print("\nQuestions left untouched:")
                for item in skipped:
                    print(f"- {item}")
            if failed:
                print("\nQuestions that failed:")
                for item in failed:
                    print(f"- {item}")

            notify(
                "Autofill complete — review required",
                f"Profile {len(filled_profile)}, drafts {len(filled_generic)}, "
                f"choices {len(filled_choice)}, files {len(filled_files)}, "
                f"skipped {len(skipped)}, failed {len(failed)}.",
            )
            print(
                "\nReview every answer and every selected file. "
                "Generic answers are drafts. The script will NOT submit the form."
            )
            input("Press Enter when done. Brave will remain open.")

    except Exception as error:
        print(f"Automation error: {error}")
        notify("Autofill error", "Check the terminal for details.")


if __name__ == "__main__":
    main()
