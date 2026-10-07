from bs4 import BeautifulSoup

with open('output/debug_internshala.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

cards = soup.select('div.internship_meta')
print(f"Total cards: {len(cards)}\n")

for i, c in enumerate(cards):
    title_el = c.select_one('a.job-title-href')
    company_el = c.select_one('p.company-name')
    loc_el = c.select_one('div.locations')
    
    title = title_el.get_text(strip=True) if title_el else "?"
    company = company_el.get_text(strip=True) if company_el else "?"
    location = loc_el.get_text(strip=True) if loc_el else "MISSING"
    
    print(f"  {i+1}. {title} @ {company} | Loc: {location}")
