"""
Quick script to inspect the current HTML structure of Indeed, Naukri, and Internshala
to identify the correct CSS selectors for job listing cards.
"""
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def inspect_site(name, url, page):
    print(f"\n{'='*60}")
    print(f"INSPECTING: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        page.goto(url, timeout=15000)
        page.wait_for_timeout(5000)
        html = page.content()
    except Exception as e:
        print(f"  ERROR loading page: {e}")
        return
    
    soup = BeautifulSoup(html, "html.parser")
    
    if name == "Indeed":
        selectors_to_check = {
            "div.cardOutline": "div.cardOutline",
            "div.job_seen_beacon": "div.job_seen_beacon",
            "div.resultContent": "div.resultContent",
            "div[data-jk]": "div[data-jk]",
            "a[data-jk]": "a[data-jk]",
            "td.resultContent": "td.resultContent",
            "div.tapItem": "div.tapItem",
            "a.tapItem": "a.tapItem",
            "li.css-5lfssm": "li.css-5lfssm",
            "div.mosaic-provider-jobcards": "div.mosaic-provider-jobcards",
            "div.slider_item": "div.slider_item",
            "div.cardOutline.tapItem": "div.cardOutline.tapItem",
        }
        # also check for elements containing job-related text
        title_selectors = ["a.jcs-JobTitle", "h2.jobTitle", "span[id^='jobTitle']", "a[data-jk]"]
        company_selectors = ["[data-testid='company-name']", "span.css-1x7txa1", "span.companyName"]
        location_selectors = ["[data-testid='text-location']", "div.companyLocation", "span.companyLocation"]
        
    elif name == "Naukri":
        selectors_to_check = {
            "div.srp-jobtuple-wrapper": "div.srp-jobtuple-wrapper",
            "article.jobTuple": "article.jobTuple",
            "div.cust-job-tuple": "div.cust-job-tuple",
            "div.listContainer": "div.listContainer",
        }
        title_selectors = ["a.title", "a.ellipsis", "h2 a"]
        company_selectors = ["a.comp-name", "span.comp-name", "a.subTitle"]
        location_selectors = ["span.locWdth", "li.location", "span.loc"]
        
    elif name == "Internshala":
        selectors_to_check = {
            "div.internship_meta": "div.internship_meta",
            "div.individual_internship": "div.individual_internship",
        }
        title_selectors = ["h3.job-internship-name", "a.job-title-href"]
        company_selectors = ["p.company-name", "a.link_display_like_text"]
        location_selectors = ["p.locations", "a.location_link", "div.locations", "span.locations", "#location_names"]
    
    # Check card containers
    print("\n  CARD CONTAINER SELECTORS:")
    for label, sel in selectors_to_check.items():
        found = soup.select(sel)
        print(f"    {label}: {len(found)} found")
    
    # Try to find any elements with relevant class patterns
    print("\n  CLASS PATTERN SEARCH:")
    for pattern in ["job", "result", "card", "listing", "tuple", "internship"]:
        elements = soup.find_all(attrs={"class": re.compile(pattern, re.I)})
        if elements:
            unique_classes = set()
            for el in elements[:20]:
                cls = el.get("class", [])
                unique_classes.add(f"{el.name}.{'.'.join(cls)}")
            print(f"    Pattern '{pattern}': {len(elements)} elements")
            for c in sorted(unique_classes)[:10]:
                print(f"      {c}")
    
    # Check specific selectors
    print("\n  TITLE SELECTORS:")
    for sel in title_selectors:
        found = soup.select(sel)
        if found:
            print(f"    {sel}: {len(found)} found, first text = '{found[0].get_text(strip=True)[:60]}'")
        else:
            print(f"    {sel}: 0 found")
    
    print("\n  COMPANY SELECTORS:")
    for sel in company_selectors:
        found = soup.select(sel)
        if found:
            print(f"    {sel}: {len(found)} found, first text = '{found[0].get_text(strip=True)[:60]}'")
        else:
            print(f"    {sel}: 0 found")
    
    print("\n  LOCATION SELECTORS:")
    for sel in location_selectors:
        found = soup.select(sel)
        if found:
            print(f"    {sel}: {len(found)} found, first text = '{found[0].get_text(strip=True)[:60]}'")
        else:
            print(f"    {sel}: 0 found")
    
    # Save HTML for manual inspection
    with open(f"output/debug_{name.lower()}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  Full HTML saved to output/debug_{name.lower()}.html")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        
        inspect_site("Internshala", "https://internshala.com/internships/keywords-AI%20ML%20internship%20Bangalore/", page)
        inspect_site("Indeed", "https://in.indeed.com/jobs?q=AI+ML+internship+Bangalore", page)
        inspect_site("Naukri", "https://www.naukri.com/ai-ml-internship-bangalore-jobs", page)
        
        context.close()
        browser.close()

if __name__ == "__main__":
    main()
