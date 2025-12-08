# Find LinkedIn Profile from Signup Email

## Objective
Given a user's signup email, find their LinkedIn profile URL.

## CRM Schema (write targets)
- `email` (primary match key)
- `linkedin_url` (store the validated profile URL)
- `title` (store the LinkedIn headline / current role)
- `location` (store city/state/country text)
- `enrich_source` (store the method string: `direct_search_validated`, `web_search_validated`, or `not_found`)

❌ Columns that do NOT exist: `headline`, `confidence`, `method`. Do not try to write them.

## Required Input
- User email address (e.g., `ibraedusu@gmail.com`)

## Step-by-Step Process

### Step 1: Direct LinkedIn Search by Email
**Tool:** `search_linkedin_person`
```python
search_linkedin_person(email="user@email.com")
```
- If successful → validate and return LinkedIn URL
- If no results → proceed to Step 2

### Step 2: Get User Location from PostHog
**Tool:** `mcp_Posthog_query_run`

**Optimized Query (extracts only location fields):**
```sql
SELECT
  id,
  properties.$geoip_city_name as city,
  properties.$geoip_subdivision_1_name as state,
  properties.$geoip_country_name as country
FROM persons
WHERE properties.email = 'user@email.com'
LIMIT 1
```

**Alternative (get all properties):**
```sql
SELECT id, properties
FROM persons
WHERE properties.email = 'user@email.com'
LIMIT 1
```

**Extract from properties:**
- `$geoip_city_name` (e.g., "Oak Park")
- `$geoip_subdivision_1_name` (e.g., "Michigan")
- `$geoip_country_name` (e.g., "United States")

**Note:** Use the optimized query for faster, cleaner results. Only use the full properties query if you need additional user data.

### Step 3: Parse Email Username into Name Variations
**Email:** `ibraedusu@gmail.com` → Username: `ibraedusu`

**Generate variations:**
1. Split at obvious boundaries: `ibra` + `edusu`
2. Try common name expansions:
   - `Ibra` → `Ibrahim`
   - `Edu` → `Eduardo`
3. Try combinations:
   - `Ibrahim Edusu`
   - `Ibra Edusu`
   - `Eduardo Ibrahim`
   - `Edusu Ibrahim`
   - `Ibrahim Eduardo`

### Step 4: Web Search with Location + Name Variations
**Tool:** `mcp_Linkup_linkup_search` (preferred) or `mcp_Exa_web_search_exa` (fallback)

**Primary: LinkUp Search**
```python
mcp_Linkup_linkup_search(
    query="[Name Variation] [City] LinkedIn"
)
```

**Examples:**
- `"Ibrahim Edusu Miami LinkedIn"`
- `"Eduardo Ibrahim Miami LinkedIn"`
- `"Ibra Edusu Florida LinkedIn"`

**If LinkUp returns no results, try Exa:**
```python
mcp_Exa_web_search_exa(
    query="[Name Variation] [City] LinkedIn",
    num_results=10
)
```

### Step 5: Identify LinkedIn Profile from Results
**Look for:**
- LinkedIn URLs in search results (format: `linkedin.com/in/username`)
- Match location (city/state) with PostHog data
- Compare LinkedIn username with email username patterns

**Pattern matching:**
- Email: `ibraedusu` might map to LinkedIn: `eduibrahim`
- Look for name components in both

### Step 6: Validate the Match
**Tool:** `get_linkedin_person_data`
```python
get_linkedin_person_data(linkedin_url="https://www.linkedin.com/in/candidate")
```

**Verify:**
- ✅ Location matches PostHog data (city/state)
- ✅ Name components match email username
- ✅ Profile seems legitimate (has work history, connections)

### Step 7: Return Result
If all validations pass (and after updating CRM):
```json
{
  "email": "user@example.com",
  "name": "Eduardo Ibrahim",
  "linkedin_url": "https://www.linkedin.com/in/eduibrahim",
  "location": "Miami, Florida, United States",
  "title": "CEO Humana AI...",
  "enrich_source": "web_search_validated"
}
```

### CRM Update Example (Neon via Datagen MCP)
Use `mcp_Neon_run_sql` with the existing columns:
```sql
UPDATE crm
SET linkedin_url = '{LINKEDIN_URL}',
    title        = '{HEADLINE_OR_ROLE}',
    location     = '{CITY_STATE_COUNTRY}',
    enrich_source = '{direct_search_validated|web_search_validated|not_found}'
WHERE email = '{EMAIL}';
```
If nothing is found, set `enrich_source = 'not_found'` and leave other fields unchanged.

## Fallback Strategy
If Steps 1-6 fail:
1. Try variations with just first name: `"Ibrahim Miami LinkedIn"`
2. Try username directly: `"ibraedusu LinkedIn"`
3. Return "Not Found" if all methods fail

## Key Success Factors
1. **Location is critical** - Narrow down search significantly
2. **Creative name parsing** - Email usernames are often name combinations
3. **Pattern recognition** - Compare email username with LinkedIn username
4. **Always validate** - Confirm location match before declaring success
