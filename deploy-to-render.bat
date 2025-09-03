@echo off
echo ========================================
echo Mental Health Chatbot - Render Deployment
echo ========================================
echo.

echo 1. Checking if git is initialized...
if not exist ".git" (
    echo Initializing git repository...
    git init
    git add .
    git commit -m "Initial commit for Render deployment"
    echo.
    echo Please create a GitHub repository and run:
    echo git remote add origin YOUR_GITHUB_REPO_URL
    echo git push -u origin main
    echo.
    pause
    exit
)

echo 2. Checking git status...
git status

echo.
echo 3. Ready to deploy! Here's what to do next:
echo.
echo a) Push your code to GitHub:
echo    git add .
echo    git commit -m "Prepare for Render deployment"
echo    git push
echo.
echo b) Go to https://dashboard.render.com/
echo c) Click "New +" → "Blueprint"
echo d) Connect your GitHub repository
echo e) Render will auto-detect render.yaml
echo.
echo 4. Don't forget to:
echo    - Set up MongoDB Atlas
echo    - Configure environment variables
echo    - Upload google_client_secret.json
echo.
echo See RENDER_DEPLOYMENT.md for detailed instructions
echo.
pause
