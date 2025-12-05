# Deploy to Render - Quick Guide

## Prerequisites

1. **GitHub Repository** - Your code should be pushed to GitHub
2. **Render Account** - Sign up at [render.com](https://render.com)
3. **API Keys**:
   - Anthropic API Key
   - GitHub Personal Access Token (with `repo` scope)

## Deployment Steps

### Option 1: Using Blueprint (Recommended)

1. Push your code to GitHub:
   ```bash
   git add .
   git commit -m "Add Claude Agent SDK poem generator"
   git push
   ```

2. Go to [Render Dashboard](https://dashboard.render.com)
3. Click **New** → **Blueprint**
4. Connect your GitHub repository
5. Render will detect `render.yaml` and create the cron job automatically

### Option 2: Manual Setup

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Cron Job**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `taiwan-poem-generator`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python generate_taiwan_poem.py`
   - **Schedule**: `0 9 * * *` (daily at 9 AM UTC)

## Environment Variables

Set these in Render dashboard → Your Cron Job → Environment:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | ✅ | Your Anthropic API key | `sk-ant-...` |
| `GITHUB_TOKEN` | ✅ | GitHub PAT with repo access | `ghp_...` |
| `GITHUB_REPO` | ✅ | Your repo (owner/repo) | `yu-shengkuo/signup-enrichment` |
| `GIT_USER_EMAIL` | ❌ | Your GitHub email | `you@example.com` |
| `GIT_USER_NAME` | ❌ | Your name | `Your Name` |

## Schedule Examples

Edit `schedule` in `render.yaml`:

- Every hour: `0 * * * *`
- Daily at 9 AM UTC: `0 9 * * *`
- Every Monday at 8 AM: `0 8 * * 1`
- Every 6 hours: `0 */6 * * *`

## Testing

After deployment, you can manually trigger a run:
1. Go to your cron job in Render dashboard
2. Click **Manual Deploy** or **Run Now**

## Files Included

- `generate_taiwan_poem.py` - Main script
- `random_number_generator.py` - Random number generator
- `requirements.txt` - Python dependencies
- `render.yaml` - Render Blueprint configuration

