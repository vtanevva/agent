# Railway Deployment Guide

This guide will help you deploy your application to Railway with automatic deployments from Git pushes.

## 🚀 Quick Answer to Your Questions

### Can I do local updates and have them automatically deploy on Railway?

**YES!** Railway supports automatic deployments from Git. Here's how it works:
- Connect your GitHub/GitLab/Bitbucket repository to Railway
- Every time you push to your main branch, Railway automatically:
  1. Detects the push
  2. Builds your Docker image
  3. Deploys the new version
  4. Restarts your service with zero downtime

### Is this recommended?

**YES!** This is the standard practice (CI/CD - Continuous Integration/Continuous Deployment) because:
- ✅ **Fast deployments** - No manual steps needed
- ✅ **Consistency** - Same build process every time
- ✅ **Safety** - Easy rollbacks if something breaks
- ✅ **Collaboration** - Team members see changes immediately
- ✅ **Version control** - Every deployment is tied to a git commit

## 📋 Prerequisites

1. **GitHub/GitLab/Bitbucket account** - Your code should be in a repository
2. **Railway account** - Sign up at [railway.app](https://railway.app)
3. **Railway CLI** (optional) - For easier management

## 🛠️ Setup Steps

### Step 1: Push Your Code to Git

Make sure your code is in a Git repository (GitHub, GitLab, or Bitbucket):

```bash
git add .
git commit -m "Prepare for Railway deployment"
git push origin main  # or your main branch name
```

### Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"** (or GitLab/Bitbucket)
4. Choose your repository
5. Railway will automatically detect the `Dockerfile`

### Step 3: Configure Environment Variables

Railway needs your environment variables. Go to your Railway project → **Variables** tab and add:

#### Required Variables:
```
OPENAI_API_KEY=your_openai_key
MONGO_URI=your_mongodb_connection_string
FLASK_SECRET_KEY=generate_a_secure_random_key
```

#### Google OAuth (if using Gmail/Calendar):
```
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_PROJECT_ID=your_project_id
```

#### Optional but Recommended:
```
PINECONE_API_KEY=your_pinecone_key
PINECONE_INDEX_NAME=your_index_name
PORT=10000
```

**Important**: After your first deployment, Railway will automatically set `RAILWAY_PUBLIC_DOMAIN` which will be used for OAuth callbacks.

### Step 4: Update Google OAuth Redirect URI

After Railway deploys your app, you'll get a public URL like:
- `https://your-app-name.up.railway.app`

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Navigate to **APIs & Services** → **Credentials**
3. Edit your OAuth 2.0 Client ID
4. Add authorized redirect URI: `https://your-app-name.up.railway.app/google/oauth2callback`
5. Update the `GOOGLE_REDIRECT_URI` variable in Railway to match

### Step 5: Set Production URL (Optional but Recommended)

Add this environment variable in Railway:
```
PRODUCTION_URL=https://your-app-name.up.railway.app
```

Or Railway will automatically use `RAILWAY_PUBLIC_DOMAIN`.

## 🔄 How Automatic Deployments Work

1. **Make changes locally**
2. **Commit and push**:
   ```bash
   git add .
   git commit -m "Your changes"
   git push origin main
   ```
3. **Railway automatically**:
   - Detects the push
   - Builds a new Docker image
   - Runs your tests (if configured)
   - Deploys to production
   - Restarts the service

### View Deployment Status

- **Railway Dashboard**: See deployment logs and status
- **Railway CLI**: `railway logs` to view real-time logs
- **GitHub Actions** (if configured): See build status in your repo

## 📝 Workflow Recommendations

### Recommended Git Workflow:

```
main branch (production)
  ↓
  - Always deployable
  - Automatic deployment to Railway

feature branches
  ↓
  - Develop features locally
  - Test on your machine
  - Create pull request
  - Merge to main → auto-deploys
```

### Branch-Based Deployments (Optional):

Railway can deploy different branches to different environments:
- `main` → Production
- `staging` → Staging environment
- `develop` → Development environment

## 🔧 Configuration Files

### `railway.toml`
This file configures Railway-specific settings (already created for you).

### `Dockerfile`
Already configured to:
- Use Python 3.10
- Install dependencies from `requirements.txt`
- Use dynamic PORT from Railway environment
- Start with Gunicorn

## 🚨 Troubleshooting

### Deployment fails

1. **Check build logs** in Railway dashboard
2. **Verify environment variables** are set correctly
3. **Check Dockerfile** syntax
4. **Ensure requirements.txt** has all dependencies

### OAuth not working

1. **Update Google Console** with new Railway URL
2. **Set `RAILWAY_PUBLIC_DOMAIN`** or `PRODUCTION_URL` environment variable
3. **Check redirect URI** matches exactly

### Service won't start

1. **Check PORT** - Railway provides this automatically
2. **View logs**: `railway logs` or Railway dashboard
3. **Test locally** with `docker build` and `docker run`

## 📚 Useful Commands

### Railway CLI (if installed)

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link

# View logs
railway logs

# Deploy manually (though auto-deploy is usually better)
railway up
```

### Local Testing

```bash
# Test Docker build locally
docker build -t my-app .
docker run -p 10000:10000 -e PORT=10000 my-app
```

## ✅ Checklist

Before deploying, make sure:

- [ ] Code is pushed to Git repository
- [ ] Railway project is created
- [ ] Environment variables are set in Railway
- [ ] Google OAuth redirect URI is updated (if using Google services)
- [ ] MongoDB connection string is valid
- [ ] First deployment succeeded
- [ ] OAuth callbacks work
- [ ] Automatic deployments are enabled

## 🎉 You're All Set!

After setup:
- Push to `main` branch → Automatic deployment
- Changes go live in ~2-5 minutes
- View logs in Railway dashboard
- Rollback if needed with one click

Happy deploying! 🚀

