import pandas as pd

# Check job listings for Bangalore
df = pd.read_csv('output/job_listings.csv')
print(f"Total job listings: {len(df)}")
print(f"Columns: {list(df.columns)}")
print()

# Check if search_keyword column exists
if 'search_keyword' in df.columns:
    blr = df[df['search_keyword'].str.contains('Bangalore|Bengaluru', case=False, na=False)]
    print(f"Listings from Bangalore search keywords: {len(blr)}")
    if len(blr) > 0:
        print(blr[['source_portal','company_name','job_title','location','company_email']].to_string(index=False))
    print()

# Check all locations broadly
print("All unique locations:")
for loc in sorted(df['location'].dropna().unique()):
    print(f"  {loc}")
print()

# Check source portals
print("Listings per portal:")
print(df['source_portal'].value_counts().to_string())
print()

# Check contacts with emails - specifically Bangalore companies from DB
import sqlite3
conn = sqlite3.connect('output/scraper.db')

# Check total emails
cur = conn.execute("SELECT COUNT(*) FROM emails")
print(f"\nTotal emails in DB: {cur.fetchone()[0]}")

# Get all companies with emails  
query = """
SELECT c.name, c.website, e.email, e.priority_score, e.mx_status
FROM companies c
JOIN emails e ON c.id = e.company_id
WHERE e.mx_status = 'Valid - MX confirmed'
ORDER BY e.priority_score DESC
"""
results = conn.execute(query).fetchall()
print(f"\nVerified emails: {len(results)}")
for r in results:
    print(f"  {r[0]} | {r[1]} | {r[2]} | score={r[3]} | {r[4]}")

conn.close()
