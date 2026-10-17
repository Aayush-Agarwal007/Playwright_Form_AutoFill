from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(
        "http://127.0.0.1:9222"
    )

    print("Connected to Brave successfully!")
    print("Open tabs:")

    for context in browser.contexts:
        for page in context.pages:
            print(page.url)

    # Do not close the browser or its contexts.