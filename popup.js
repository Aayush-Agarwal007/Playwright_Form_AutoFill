
const urlInput = document.getElementById("formUrl");
const profileInput = document.getElementById("profile");
const status = document.getElementById("status");

const starterProfile = {
  "full_name": "",
  "first_name": "",
  "last_name": "",
  "email": "",
  "phone": "",
  "college": "",
  "university": "",
  "degree": "",
  "branch": "",
  "semester": "",
  "graduation_year": "",
  "cgpa": "",
  "tenth_percentage": "",
  "twelfth_percentage": "",
  "city": "",
  "state": "",
  "country": "",
  "linkedin_url": "",
  "github_url": "",
  "portfolio_url": "",
  "skills": "",
  "preferred_role": "",
  "experience_level": "",
  "additional_information": ""
};

function showStatus(message) {
  status.textContent = message;
}

async function loadProfile() {
  const saved = await chrome.storage.local.get("profile");
  profileInput.value = JSON.stringify(
    saved.profile || starterProfile,
    null,
    2
  );
}

document.getElementById("saveProfile").addEventListener("click", async () => {
  try {
    const profile = JSON.parse(profileInput.value);

    if (
      profile === null ||
      Array.isArray(profile) ||
      typeof profile !== "object"
    ) {
      throw new Error("Profile must be a JSON object.");
    }

    await chrome.storage.local.set({ profile });
    showStatus("Profile saved on this browser.");
  } catch (error) {
    showStatus("Invalid JSON: " + error.message);
  }
});

document.getElementById("openForm").addEventListener("click", async () => {
  const url = urlInput.value.trim();

  try {
    const parsed = new URL(url);
    const allowedHosts = [
      "docs.google.com",
      "forms.gle"
    ];

    if (
      parsed.protocol !== "https:" ||
      !allowedHosts.includes(parsed.hostname) ||
      (parsed.hostname === "docs.google.com" &&
       !parsed.pathname.startsWith("/forms/"))
    ) {
      throw new Error("Enter a valid Google Forms URL.");
    }

    await chrome.tabs.create({ url });
    showStatus(
      "Form opened in a new tab in this Brave window. " +
      "Wait for it to load, then click the extension again."
    );
  } catch (error) {
    showStatus(error.message || "Please check the form URL.");
  }
});

document.getElementById("autofill").addEventListener("click", async () => {
  try {
    const profile = JSON.parse(profileInput.value);
    await chrome.storage.local.set({ profile });

    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });

    if (!tab || !tab.id || !tab.url) {
      throw new Error("No active tab found.");
    }

    const host = new URL(tab.url).hostname;

    if (host !== "docs.google.com" ||
        !new URL(tab.url).pathname.startsWith("/forms/")) {
      throw new Error(
        "Open the Google Form tab first, then click Autofill."
      );
    }

    const result = await chrome.tabs.sendMessage(tab.id, {
      action: "AUTOFILL_FORM",
      profile
    });

    showStatus(result?.message || "Autofill finished.");
  } catch (error) {
    showStatus(
      "Could not autofill: " + error.message +
      "\nIf the form just opened, wait a few seconds and try again."
    );
  }
});

loadProfile().catch(error => {
  showStatus("Could not load profile: " + error.message);
});
