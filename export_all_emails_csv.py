import sqlite3
import pandas as pd
import os

# Connect to database
db_path = 'output/scraper.db'
conn = sqlite3.connect(db_path)

# Query all emails along with company details
query = """
SELECT 
    c.name as "Company Name",
    c.website as "Website",
    e.email as "Email",
    e.priority_score as "Priority Score",
    e.mx_status as "MX Status",
    e.page_found_on as "Source Page"
FROM companies c
JOIN emails e ON c.id = e.company_id
ORDER BY e.priority_score DESC, c.name ASC
"""

df_emails = pd.read_sql(query, conn)
conn.close()

# Try to merge location & job title info from job_listings.csv if available
job_listings_path = 'output/job_listings.csv'
if os.path.exists(job_listings_path):
    listings_df = pd.read_csv(job_listings_path)
    # Aggregate job titles and locations per company
    comp_info = listings_df.groupby('company_name').agg({
        'job_title': lambda x: ' | '.join(set(x.dropna())),
        'location': lambda x: ', '.join(set(x.dropna()))
    }).reset_index()
    comp_info.columns = ['Company Name', 'Job Roles Listed', 'Location']
    
    df_merged = pd.merge(df_emails, comp_info, on='Company Name', how='left')
else:
    df_merged = df_emails
    df_merged['Job Roles Listed'] = 'N/A'
    df_merged['Location'] = 'N/A'

# Add recommendation category
avoid_keywords = ['security@', 'privacy@', 'grievance', 'complaints@', 'press@', 'legal@', 'accounts.', 'customercare@', '.png', 'example']

def categorize_outreach(row):
    email = str(row['Email']).lower()
    mx = str(row['MX Status'])
    
    if any(kw in email for kw in avoid_keywords):
        return 'Avoid (Non-Hiring / Security / Legal)'
    if mx != 'Valid - MX confirmed':
        return 'Unverified / Invalid MX'
    if any(k in email for k in ['hr@', 'career', 'talent', 'jobs', 'hiring', 'people@']):
        return 'Tier 1: HR & Talent Target'
    elif any(k in email for k in ['hello@', 'contact@', 'info@', 'support@', 'team@', 'partner@']):
        return 'Tier 2: General Company Target'
    else:
        return 'Tier 2: Direct Contact Email'

df_merged['Outreach Category'] = df_merged.apply(categorize_outreach, axis=1)

# Reorder columns logically
cols = [
    'Company Name', 'Email', 'Outreach Category', 'Priority Score', 
    'MX Status', 'Website', 'Location', 'Job Roles Listed', 'Source Page'
]
df_final = df_merged[[c for c in cols if c in df_merged.columns]]

# Save to single master CSV
output_path = 'output/all_cold_email_targets.csv'
df_final.to_csv(output_path, index=False)

print(f"Master CSV created successfully with {len(df_final)} email rows: {output_path}")
