import sqlite3
import pandas as pd

conn = sqlite3.connect('output/scraper.db')

query = """
SELECT c.name as Company, c.website as Website, e.email as Email, 
       e.priority_score as Score, e.page_found_on as Source
FROM companies c
JOIN emails e ON c.id = e.company_id
WHERE e.mx_status = 'Valid - MX confirmed'
  AND e.email NOT LIKE '%.png'
  AND e.email NOT LIKE '%example%'
ORDER BY e.priority_score DESC
"""

df = pd.read_sql(query, conn)
conn.close()

# Exclude unsuited emails (security, privacy, grievance, complaints, press, legal, accounts)
avoid_keywords = ['security@', 'privacy@', 'grievance', 'complaints@', 'press@', 'legal@', 'accounts.', 'customercare@']

def categorize_email(row):
    email = str(row['Email']).lower()
    score = row['Score']
    
    for kw in avoid_keywords:
        if kw in email:
            return 'Avoid (Non-Hiring Department)'
            
    if any(k in email for k in ['hr@', 'career', 'talent', 'jobs', 'hiring', 'people@']):
        return 'Tier 1: Best Target (HR / Talent / Careers)'
    elif any(k in email for k in ['hello@', 'contact@', 'info@', 'support@', 'team@', 'partner@']):
        return 'Tier 2: Good Target (General / Direct Contact)'
    elif '@' in email and score >= 50:
        return 'Tier 2: Direct Email'
    else:
        return 'Tier 3: Low Priority'

df['Category'] = df.apply(categorize_email, axis=1)

# Filter out Avoid
rec_df = df[df['Category'] != 'Avoid (Non-Hiring Department)'].copy()
rec_df.to_csv('output/recommended_cold_emails.csv', index=False)

print(f"Total verified emails: {len(df)}")
print(f"Recommended outreach emails: {len(rec_df)}")
print("\nBreakdown:")
print(rec_df['Category'].value_counts())
