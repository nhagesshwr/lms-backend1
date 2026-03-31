"""
Automatic Railway Deployment Script
Run: python deploy.py
"""

import subprocess
import sys
import os
import json
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────
GITHUB_REPO = "https://github.com/nhagesshwr/lms-backend1.git"
BRANCH = "main"

ENV_VARS = {
    "DATABASE_URL": "postgresql://neondb_owner:npg_HRDB8Q3TWMua@ep-late-mud-a1t6nbkc-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    "SECRET_KEY": "8ccfca8a127df6e2ccf7a3382a35585e1edcef4233cfaf6a1fdfb888b4ca0cbec",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
    "B2_KEY_ID": "005180f06915c310000000001",
    "B2_APP_KEY": "K0058h/HYMyXp7I4CqMSVxxQPbSCxZQ",
    "B2_BUCKET_NAME": "Lmsportal",
    "B2_ENDPOINT": "https://s3.us-east-005.backblazeb2.com",
    "ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000,https://frontendmodified.vercel.app,https://*.vercel.app",
}
# ─────────────────────────────────────────────────────────────────────────────


def run(cmd, check=True, capture=False):
    """Run a shell command and print output."""
    print(f"\n$ {cmd}")
    result = subprocess.run(
        cmd, shell=True, check=check,
        capture_output=capture, text=True
    )
    if capture:
        return result.stdout.strip()
    return result


def step(msg):
    print(f"\n{'='*55}")
    print(f"  {msg}")
    print(f"{'='*55}")


# ── STEP 1: Install Railway CLI ───────────────────────────────────────────────
def install_railway_cli():
    step("1/5  Installing Railway CLI")
    result = subprocess.run("railway --version", shell=True,
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Railway CLI already installed: {result.stdout.strip()}")
        return
    # Install via npm (cross-platform)
    run("npm install -g @railway/cli")
    print("Railway CLI installed.")


# ── STEP 2: Git init + push to GitHub ────────────────────────────────────────
def push_to_github():
    step("2/5  Pushing code to GitHub")

    # Init git if not already
    if not os.path.exists(".git"):
        run("git init")
        run(f"git remote add origin {GITHUB_REPO}")
    else:
        # Make sure remote is set
        remotes = run("git remote", capture=True)
        if "origin" not in remotes:
            run(f"git remote add origin {GITHUB_REPO}")
        else:
            run(f"git remote set-url origin {GITHUB_REPO}")

    run("git add .")
    run('git commit -m "Auto deploy: Railway config" --allow-empty')
    run(f"git push -u origin {BRANCH} --force")
    print("Code pushed to GitHub.")


# ── STEP 3: Railway login ─────────────────────────────────────────────────────
def railway_login():
    step("3/5  Logging in to Railway")
    # Check if already logged in
    result = subprocess.run("railway whoami", shell=True,
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Already logged in as: {result.stdout.strip()}")
        return
    # Opens browser for login
    run("railway login")


# ── STEP 4: Create project + link ─────────────────────────────────────────────
def create_and_link_project():
    step("4/5  Creating Railway project and linking")

    # Check if already linked
    result = subprocess.run("railway status", shell=True,
                            capture_output=True, text=True)
    if result.returncode == 0 and "Project" in result.stdout:
        print("Already linked to a Railway project.")
    else:
        # Create new project from GitHub repo
        run(f"railway init --name lms-backend")

    # Set all environment variables
    print("\nSetting environment variables...")
    for key, value in ENV_VARS.items():
        run(f'railway variables set {key}="{value}"')
        print(f"  ✓ {key}")


# ── STEP 5: Deploy ────────────────────────────────────────────────────────────
def deploy():
    step("5/5  Deploying to Railway")
    run("railway up --detach")

    print("\nWaiting for deployment to start...")
    time.sleep(5)

    # Get the public URL
    result = subprocess.run("railway domain", shell=True,
                            capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        url = result.stdout.strip()
        print(f"\n✅ Deployed! Your API is live at: https://{url}")
    else:
        # Generate a domain if none exists
        run("railway domain", check=False)
        print("\n✅ Deployment triggered. Check your Railway dashboard for the live URL.")
        print("   https://railway.com/dashboard")


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🚀 LMS Backend — Automatic Railway Deployment")
    print("=" * 55)

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    try:
        install_railway_cli()
        push_to_github()
        railway_login()
        create_and_link_project()
        deploy()
        print("\n🎉 All done! Your backend is deployed on Railway.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error at step: {e}")
        print("Fix the issue above and re-run: python deploy.py")
        sys.exit(1)
