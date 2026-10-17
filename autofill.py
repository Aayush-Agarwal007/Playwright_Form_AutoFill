import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from winotify import Notification

BASE_DIR = Path(__file__).resolve().parent
PROFILE_FILE = BASE_DIR / "profile.json"
BROWSER_PROFILE = BASE_DIR / "browser_profile"

# More specific question patterns must appear before general patterns.
FIELD_RULES = [
    (r"\b(alternate email|secondary email)\b", "alternate_email"),
    (r"\b(email address|e-mail|email|mail id)\b", "email"),
    (r"\b(alternate phone|secondary phone)\b", "alternate_phone"),
    (
        r"\b(phone number|mobile number|contact number|telephone|phone|mobile)\b",
        "phone",
    ),
    (r"\b(college name|college|institution name|institution)\b", "college"),
    (r"\b(university name|university)\b", "university"),
    (r"\b(department|specialization|specialisation)\b", "department"),
    (r"\b(branch|stream)\b", "branch"),
    (r"\b(current semester|semester)\b", "semester"),
    (r"\b(current year|year of study|academic year)\b", "current_year"),
    (r"\b(graduation year|passing year|year of graduation)\b", "graduation_year"),
    (r"\b(10th percentage|class 10 percentage|10th marks)\b", "tenth_percentage"),
    (r"\b(12th percentage|class 12 percentage|12th marks)\b", "twelfth_percentage"),
    (r"\b(cgpa|cumulative grade point average)\b", "cgpa"),
    (r"\b(first name)\b", "first_name"),
    (r"\b(last name|surname)\b", "last_name"),
    (
        r"\b(full name|candidate name|applicant name|your name|name)\b",
        "full_name",
    ),
    (r"\b(linkedin profile|linkedin url|linkedin)\b", "linkedin_url"),
    (r"\b(github profile|github url|github)\b", "github_url"),
    (r"\b(portfolio url|portfolio website|portfolio)\b", "portfolio_url"),
    (r"\b(city|town)\b", "city"),
    (r"\b(state|province)\b", "state"),
    (r"\b(country)\b", "country"),
    (r"\b(preferred role|desired role|job role)\b", "preferred_role"),
    (r"\b(experience level)\b", "experience_level"),
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
        return json.load(file)


def is_google_form_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host in {"docs.google.com", "forms.gle"}


def find_value(question_text, profile):
    question = re.sub(r"\s+", " ", question_text.lower()).strip()

    # Avoid assigning your details to another person's information.
    if re.search(
        r"\b(parent|father|mother|guardian|placement officer|"
        r"emergency contact|reference person)\b",
        question,
    ):
        return None, None

    for pattern, key in FIELD_RULES:
        value = profile.get(key)

        if value in (None, ""):
            continue

        if isinstance(value, (list, dict)):
            continue

        if re.search(pattern, question):
            return key, str(value)

    return None, None


def main():
    try:
        profile = load_profile()
    except (OSError, json.JSONDecodeError) as error:
        print(f"Cannot read profile.json: {error}")
        notify("Autofill error", "Check profile.json.")
        return

    url = input("Paste your Google Forms URL: ").strip()

    if not is_google_form_url(url):
        print("Please enter a valid HTTPS Google Forms URL.")
        return

    filled = []
    skipped = []
    failed = []

    try:
        with sync_playwright() as p:
            BRAVE_PATH = (
                r"C:\Program Files\BraveSoftware"
                r"\Brave-Browser\Application\brave.exe"
            )

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE),
                executable_path=BRAVE_PATH,
                headless=False,
                viewport={"width": 1280, "height": 900},
            )

            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded")

                print("Sign in manually if necessary.")
                input("When the form is visible, press Enter here...")

                questions = page.locator('[role="listitem"]')
                total = questions.count()
                print(f"Found {total} possible question containers.")

                for i in range(total):
                    question = questions.nth(i)

                    if not question.is_visible():
                        continue

                    try:
                        question_text = question.inner_text(timeout=2000)
                    except Exception:
                        skipped.append("Unreadable question")
                        continue

                    key, value = find_value(question_text, profile)

                    if not key:
                        skipped.append(question_text[:100])
                        print(f"SKIPPED: {question_text[:80]}")
                        continue

                    fields = question.locator(
                        'input:not([type="hidden"]):'
                        'not([type="radio"]):'
                        'not([type="checkbox"]):'
                        'not([type="file"]), textarea'
                    )

                    candidates = []

                    for j in range(fields.count()):
                        field = fields.nth(j)

                        if not field.is_visible() or not field.is_enabled():
                            continue

                        tag = field.evaluate(
                            "(el) => el.tagName.toLowerCase()"
                        )
                        field_type = (
                            field.get_attribute("type") or "text"
                        ).lower()

                        if tag == "textarea" or field_type in {
                            "text",
                            "email",
                            "tel",
                            "number",
                            "url",
                        }:
                            candidates.append(field)

                    if len(candidates) != 1:
                        skipped.append(question_text[:100])
                        print(f"SKIPPED (ambiguous): {question_text[:80]}")
                        continue

                    try:
                        candidates[0].fill(value, timeout=3000)
                        filled.append(key)
                        print(f"FILLED: {key}")
                    except Exception as error:
                        failed.append(key)
                        print(f"FAILED: {key} — {error}")

                print("\n========== AUTOFILL REPORT ==========")
                print(f"Filled:  {len(filled)}")
                print(f"Skipped: {len(skipped)}")
                print(f"Failed:  {len(failed)}")

                if skipped:
                    print("\nQuestions to review:")
                    for question in skipped:
                        print(f"- {question}")

                if failed:
                    print("\nFields that failed:")
                    for field in failed:
                        print(f"- {field}")

                notify(
                    "Autofill complete — review required",
                    f"Filled {len(filled)}, skipped {len(skipped)}, "
                    f"failed {len(failed)}. Check the open form.",
                )

                print("\nReview the browser and submit manually.")
                input("Press Enter here when you are ready to close it...")

            finally:
                context.close()

    except Exception as error:
        print(f"Automation error: {error}")
        notify("Autofill error", "Check the terminal for details.")


if __name__ == "__main__":
    main()