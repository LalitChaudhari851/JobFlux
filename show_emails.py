import sqlite3
import pandas as pd
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

conn = sqlite3.connect('output/scraper.db')

# Get all companies with emails
query = """
SELECT c.name as Company, c.website as Website, e.email as Email, 
       e.priority_score as Score, e.mx_status as MX_Status
FROM companies c
JOIN emails e ON c.id = e.company_id
WHERE e.mx_status = 'Valid - MX confirmed'
ORDER BY e.priority_score DESC
"""
df = pd.read_sql(query, conn)
print(f"=== ALL VERIFIED EMAILS IN DATABASE ===")
print(f"Total: {len(df)}")
print()

# Show all with nice formatting
for _, row in df.iterrows():
    print(f"  {row['Company']:<40} | {row['Email']:<40} | Score: {row['Score']}")

print(f"\n=== BANGALORE-SPECIFIC COMPANIES ===")
# Check job listings for Bangalore companies
try:
    listings = pd.read_csv('output/job_listings.csv')
    blr = listings[listings['location'].str.contains('Bangalore|Bengaluru|Banglore', case=False, na=False)]
    if len(blr) > 0:
        blr_companies = blr['company_name'].unique()
        print(f"Companies with Bangalore listings: {len(blr_companies)}")
        for comp in blr_companies:
            emails = df[df['Company'].str.lower() == comp.lower()]
            if len(emails) > 0:
                for _, e in emails.iterrows():
                    print(f"  ✅ {comp}: {e['Email']} (Score: {e['Score']})")
            else:
                print(f"  ❌ {comp}: No email found yet")
    else:
        print("No Bangalore listings in current CSV yet (scraper may still be running)")
except Exception as e:
    print(f"Could not read job listings: {e}")

conn.close()
