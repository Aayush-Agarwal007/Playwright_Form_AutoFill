
const FIELD_RULES = [
  { keys: ["full_name", "name"], patterns: [/full name/, /^name$/, /your name/, /candidate name/] },
  { keys: ["first_name"], patterns: [/first name/, /given name/] },
  { keys: ["last_name"], patterns: [/last name/, /surname/, /family name/] },
  { keys: ["email"], patterns: [/e-mail/, /email address/, /^email$/] },
  { keys: ["phone"], patterns: [/phone/, /mobile number/, /contact number/] },
  { keys: ["college", "university"], patterns: [/college name/, /university name/, /college or university/, /institution name/] },
  { keys: ["degree"], patterns: [/degree/, /qualification/] },
  { keys: ["branch"], patterns: [/branch/, /speciali[sz]ation/, /major/, /department/] },
  { keys: ["semester"], patterns: [/semester/, /current year of study/, /study year/] },
  { keys: ["graduation_year"], patterns: [/graduation year/, /year of passing/, /passing year/, /expected graduation/] },
  { keys: ["cgpa"], patterns: [/cgpa/, /cumulative grade/, /grade point average/] },
  { keys: ["tenth_percentage"], patterns: [/10th.*percent/, /class 10.*percent/, /10th.*marks/] },
  { keys: ["twelfth_percentage"], patterns: [/12th.*percent/, /class 12.*percent/, /12th.*marks/] },
  { keys: ["city"], patterns: [/^city$/, /current city/] },
  { keys: ["state"], patterns: [/^state$/, /state of residence/] },
  { keys: ["country"], patterns: [/^country$/, /country of residence/] },
  { keys: ["linkedin_url"], patterns: [/linkedin/] },
  { keys: ["github_url"], patterns: [/github/] },
  { keys: ["portfolio_url"], patterns: [/portfolio website/, /personal website/, /website url/] },
  { keys: ["skills"], patterns: [/technical skills/, /^skills$/, /programming languages/] },
  { keys: ["preferred_role"], patterns: [/preferred role/, /job role/, /position applying/, /role applying/] },
  { keys: ["experience_level"], patterns: [/experience level/, /years of experience/] },
  { keys: ["additional_information"], patterns: [/additional information/, /anything else/, /other details/] }
];

function normalize(text) {
  return (text || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function getQuestionText(question) {
  const title = question.querySelector(
    ".M7eMe, [role='heading'], .HoXoMd"
  );
  return normalize(title?.innerText || question.innerText || "");
}

function findProfileValue(questionText, profile) {
  for (const rule of FIELD_RULES) {
    if (rule.patterns.some(pattern => pattern.test(questionText))) {
      for (const key of rule.keys) {
        const value = profile[key];
        if (value !== undefined && value !== null &&
            String(value).trim() !== "") {
          return String(value);
        }
      }
    }
  }

  return null;
}

function fillControl(control, value) {
  if (control.disabled || control.readOnly) return false;

  const tag = control.tagName.toLowerCase();
  const type = (control.getAttribute("type") || "text").toLowerCase();

  if (tag === "textarea") {
    // Supported
  } else if (
    tag === "input" &&
    ["text", "email", "tel", "url", "number"].includes(type)
  ) {
    // Supported
  } else {
    return false;
  }

  const prototype = tag === "textarea"
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;

  const setter = Object.getOwnPropertyDescriptor(
    prototype, "value"
  )?.set;

  if (setter) {
    setter.call(control, value);
  } else {
    control.value = value;
  }

  control.dispatchEvent(new Event("input", { bubbles: true }));
  control.dispatchEvent(new Event("change", { bubbles: true }));

  return true;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action !== "AUTOFILL_FORM") return;

  try {
    const profile = request.profile || {};
    const questions = Array.from(
      document.querySelectorAll('[role="listitem"]')
    );

    let filled = 0;
    let skipped = 0;
    const report = [];

    for (const question of questions) {
      const questionText = getQuestionText(question);

      const controls = Array.from(
        question.querySelectorAll("input, textarea")
      ).filter(control => {
        const type = (control.getAttribute("type") || "text").toLowerCase();
        return !["hidden", "radio", "checkbox", "file", "submit"].includes(type);
      });

      if (!controls.length) continue;

      const value = findProfileValue(questionText, profile);

      if (value === null) {
        skipped++;
        report.push("Skipped: " + (questionText || "Unlabelled question"));
        continue;
      }

      let didFill = false;

      for (const control of controls) {
        if (fillControl(control, value)) {
          didFill = true;
        }
      }

      if (didFill) {
        filled++;
        report.push("Filled: " + questionText);
      } else {
        skipped++;
        report.push("Skipped unsupported field: " + questionText);
      }
    }

    const message =
      `Autofill complete.\nFilled: ${filled}\nSkipped: ${skipped}\n\n` +
      (report.length ? report.join("\n") : "No supported fields were found.") +
      "\n\nReview every answer before submitting.";

    sendResponse({ message });
  } catch (error) {
    sendResponse({ message: "Autofill error: " + error.message });
  }

  return true;
});
