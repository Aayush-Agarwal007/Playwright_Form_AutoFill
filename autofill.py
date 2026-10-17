import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from winotify import Notification

BASE_DIR = Path(__file__).resolve().parent
PROFILE_FILE = BASE_DIR / "profile.json"
DEBUGGING_URL = "http://127.0.0.1:9222"

# Put specific patterns before general patterns.
FIELD_RULES = [
    (r"\b(alternate email|secondary email)\b", "alternate_email"),
    (r"\b(email address|e-mail address|e-mail|email|mail id)\b", "email"),
    (r"\b(alternate phone|secondary phone)\b", "alternate_phone"),
    (r"\b(phone number|mobile number|contact number|telephone|phone|mobile)\b", "phone"),
    (r"\b(college name|institution name|college|institution)\b", "college"),
    (r"\b(university name|university)\b", "university"),
    (r"\b(department|specialization|specialisation)\b", "department"),
    (r"\b(branch|stream)\b", "branch"),
    (r"\b(current semester|semester)\b", "semester"),
    (r"\b(current year|year of study|academic year)\b", "current_year"),
    (r"\b(graduation year|year of graduation|year of passing|passing year)\b", "graduation_year"),
    (r"\b(10th percentage|class 10 percentage|10th marks|class 10 marks)\b", "tenth_percentage"),
    (r"\b(12th percentage|class 12 percentage|12th marks|class 12 marks)\b", "twelfth_percentage"),
    (r"\b(cgpa|cumulative grade point average)\b", "cgpa"),
    (r"\b(first name|given name)\b", "first_name"),
    (r"\b(last name|surname|family name)\b", "last_name"),
    (r"\b(full name|candidate name|applicant name|your name|name)\b", "full_name"),
    (r"\b(linkedin profile|linkedin url|linkedin)\b", "linkedin_url"),
    (r"\b(github profile|github url|github)\b", "github_url"),
    (r"\b(portfolio url|portfolio website|portfolio)\b", "portfolio_url"),
    (r"\b(city|town)\b", "city"),
    (r"\b(state|province)\b", "state"),
    (r"\b(country)\b", "country"),
    (r"\b(preferred role|desired role|job role|position applying for)\b", "preferred_role"),
    (r"\b(experience level|years of experience)\b", "experience_level"),
    (r"\b(technical skills|programming languages|skills)\b", "skills"),
    (r"\b(additional information|anything else|other details)\b", "additional_information"),
]

OTHER_PERSON_RE = re.compile(
    r"\b(parent|father|mother|guardian|placement officer|emergency contact|"
    r"reference person|friend|spouse|sibling|brother|sister)\b",
    re.IGNORECASE,
)


def notify(title: str, message: str) -> None:
    try:
        Notification(
            app_id="Google Forms Autofill",
            title=title,
            msg=message[:250],
            duration="long",
        ).show()
    except Exception as error:
        print(f"Desktop notification unavailable: {error}")


def load_profile() -> dict:
    with PROFILE_FILE.open("r", encoding="utf-8") as file:
        profile = json.load(file)
    if not isinstance(profile, dict):
        raise ValueError("profile.json must contain a JSON object.")
    return profile


def is_google_form_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return False
    if host == "forms.gle":
        return True
    return host == "docs.google.com" and parsed.path.startswith("/forms/")


def find_value(question_text: str, profile: dict):
    question = re.sub(r"\s+", " ", question_text.lower()).strip()

    # Avoid filling details for another person.
    if OTHER_PERSON_RE.search(question):
        return None, None

    for pattern, key in FIELD_RULES:
        if not re.search(pattern, question, re.IGNORECASE):
            continue

        # Use the specific name field if the question asks for it.
        if key == "full_name":
            if re.search(r"\b(first name|given name)\b", question):
                key = "first_name"
            elif re.search(r"\b(last name|surname|family name)\b", question):
                key = "last_name"

        value = profile.get(key)
        if value is None or value == "" or isinstance(value, (list, dict)):
            continue

        return key, str(value)

    return None, None


def get_question_text(question) -> str:
    for selector in (".M7eMe", "[role='heading']", ".HoXoMd"):
        title = question.locator(selector).first
        try:
            if title.count() and title.is_visible():
                text = title.inner_text(timeout=1500).strip()
                if text:
                    return text
        except Exception:
            pass

    try:
        return question.inner_text(timeout=1500).strip()
    except Exception:
        return ""


def fill_supported_field(question, value: str) -> bool:
    fields = question.locator(
        'input:not([type="hidden"]):not([type="radio"]):'
        'not([type="checkbox"]):not([type="file"]):'
        'not([type="submit"]), textarea'
    )

    candidates = []
    for index in range(fields.count()):
        field = fields.nth(index)
        try:
            if not field.is_visible() or not field.is_enabled():
                continue
            if field.get_attribute("readonly") is not None:
                continue

            tag = field.evaluate("(el) => el.tagName.toLowerCase()")
            field_type = (field.get_attribute("type") or "text").lower()
            if tag == "textarea" or field_type in {
                "text", "email", "tel", "number", "url"
            }:
                candidates.append(field)
        except Exception:
            continue

    # Never guess when a question has multiple possible inputs.
    if len(candidates) != 1:
        return False

    candidates[0].fill(value, timeout=3000)
    return True


def main() -> None:
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

    filled = []
    skipped = []
    failed = []

    try:
        with sync_playwright() as playwright:
            print(f"Connecting to the already-open Brave session at {DEBUGGING_URL}...")
            browser = playwright.chromium.connect_over_cdp(DEBUGGING_URL)

            if not browser.contexts:
                print("No browser context was found. Check that debugging-enabled Brave is running.")
                return

            context = browser.contexts[0]
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")

            print("\nGoogle Form opened in a new tab in the connected Brave window.")
            print("If the form requires sign-in, use Google's normal supported sign-in flow.")
            input("When the form is fully loaded and visible, press Enter here...")

            questions = page.locator('[role="listitem"]')
            total = questions.count()
            print(f"\nFound {total} possible question containers.")

            for index in range(total):
                question = questions.nth(index)
                try:
                    if not question.is_visible():
                        continue

                    question_text = get_question_text(question)
                    if not question_text:
                        skipped.append("Unreadable question")
                        continue

                    key, value = find_value(question_text, profile)
                    if key is None:
                        skipped.append(question_text[:100])
                        print(f"SKIPPED (no saved answer): {question_text[:80]}")
                        continue

                    try:
                        did_fill = fill_supported_field(question, value)
                    except Exception as error:
                        failed.append(key)
                        print(f"FAILED: {key} — {error}")
                        continue

                    if did_fill:
                        filled.append(key)
                        print(f"FILLED: {key}")
                    else:
                        skipped.append(question_text[:100])
                        print(f"SKIPPED (unsupported or ambiguous): {question_text[:80]}")

                except Exception as error:
                    failed.append(f"Question {index + 1}")
                    print(f"FAILED: question {index + 1} — {error}")

            print("\n========== AUTOFILL REPORT ==========")
            print(f"Filled:  {len(filled)}")
            print(f"Skipped: {len(skipped)}")
            print(f"Failed:  {len(failed)}")

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
                f"Filled {len(filled)}, skipped {len(skipped)}, "
                f"failed {len(failed)}. Review the open form.",
            )

            print("\nReview every answer. The script will NOT submit the form.")
            input("Press Enter here when finished. The browser will remain open...")

            # Intentionally do not close the CDP browser/context. That would
            # risk closing the user's connected Brave session.

    except Exception as error:
        print(f"Automation error: {error}")
        notify("Autofill error", "Check the terminal for details.")


if __name__ == "__main__":
    main()
