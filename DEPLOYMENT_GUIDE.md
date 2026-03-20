# Deployment Guide - FlaskWebHub on Render

The deployment failed because Render couldn't authenticate with your GitHub repository. Here's how to fix it.

---

## ❌ Problem

```
fatal: could not read Username for 'https://github.com': terminal prompts disabled
ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'
```

**Root cause**: Your GitHub repo is **private** and Render needs authentication to clone it.

---

## ✅ Solution: 2 Options

### **Option 1: Make Repository Public (Easier)**

1. Go to GitHub: https://github.com/iamearht/FlaskWebHub/settings
2. Scroll to "Danger Zone"
3. Click "Change repository visibility"
4. Select "Public"
5. Confirm
6. Redeploy on Render (it will auto-detect changes)

**Pros**: Simple, no extra setup
**Cons**: Code is public

---

### **Option 2: Use GitHub Deploy Token (Recommended for Private Repos)**

1. **Create a GitHub Personal Access Token**:
   - Go to https://github.com/settings/tokens/new
   - Name: "Render Deploy Token"
   - Scopes: `repo` (Full control of private repositories)
   - Expiration: 90 days
   - Click "Generate token"
   - **Copy the token** (you won't see it again!)

2. **Add to Render Environment**:
   - Go to your Render service settings
   - Go to "Environment"
   - Add new variable:
     ```
     GITHUB_TOKEN = <your-token-from-step-1>
     ```

3. **Update Render configuration** to use the token (already done in `render.yaml`)

**Pros**: Repo stays private
**Cons**: Token expires after 90 days

---

## 🚀 How to Deploy

### **If using Render.com:**

1. **Connect GitHub** (if not already):
   - Go to https://dashboard.render.com
   - Click "New +"
   - Select "Web Service"
   - Connect your GitHub account
   - Select repository: `iamearht/FlaskWebHub`

2. **Configure Service**:
   - Name: `flaskwebhub`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn --workers 4 --worker-class sync --timeout 120 --bind 0.0.0.0:8080 main:app`

3. **Set Environment Variables**:
   - `FLASK_ENV`: `production`
   - `DATABASE_URL`: Your PostgreSQL URL (Render provides one)
   - `SESSION_SECRET`: Generate a random string

4. **Deploy**:
   - Click "Create Web Service"
   - Wait for build to complete (~3-5 minutes)
   - Visit your app URL

### **Manual Deploy (if Render.com has issues):**

Use Render's CLI:
```bash
# Install Render CLI
npm install -g @render-com/cli

# Login
render login

# Deploy from project directory
render deploy --repo iamearht/FlaskWebHub
```

---

## 📋 Requirements.txt

Your `requirements.txt` is minimal but should work. If you need additional dependencies, add them:

```txt
flask>=3.1.2
flask-sqlalchemy>=3.1.1
flask-login>=0.6.3
gunicorn>=25.1.0
psycopg2-binary>=2.9.11
```

Optional additions:
```txt
python-dotenv>=1.0.0  # For .env file support
redis>=5.0.0          # For caching/sessions
celery>=5.3.0         # For background jobs
```

---

## 🗄️ Database Setup

Render provides a free PostgreSQL database:

1. **Create PostgreSQL on Render**:
   - Dashboard → New + → PostgreSQL
   - Name: `flaskwebhub-db`
   - Take note of the connection string

2. **Get DATABASE_URL**:
   ```
   postgresql://user:password@host:5432/dbname
   ```

3. **Add to Web Service Environment**:
   - Go to Web Service settings
   - Add `DATABASE_URL` environment variable
   - Paste the connection string from PostgreSQL service

4. **Run migrations** (after first deploy):
   ```bash
   # Via SSH or Render shell:
   python migrate.py
   ```

---

## 🔒 Environment Variables Required

Set these in Render dashboard:

| Variable | Example | Required |
|----------|---------|----------|
| `FLASK_ENV` | `production` | ✅ Yes |
| `DATABASE_URL` | `postgresql://user:pass@host/db` | ✅ Yes |
| `SESSION_SECRET` | (random string, 32+ chars) | ✅ Yes |
| `DEBUG` | `False` | No |

**To generate SESSION_SECRET:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## ✨ Features in Render.yaml

The `render.yaml` file I created includes:

- ✅ Python 3.11 runtime
- ✅ Automatic dependency installation
- ✅ Gunicorn as production server
- ✅ Environment variable configuration
- ✅ Auto-deploy on GitHub pushes
- ✅ Static file serving
- ✅ Proper start command

---

## 🧪 Test Locally First

Before deploying:

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py

# Test in browser
http://localhost:5000
```

---

## ❌ Common Errors & Fixes

### **"Could not open requirements.txt"**
- **Fix**: Ensure `requirements.txt` is in repo root
- Verify: `git ls-files requirements.txt`

### **"fatal: could not read Username"**
- **Fix**: Make repo public OR add GitHub deploy token
- See "Solution" section above

### **"ModuleNotFoundError"**
- **Fix**: Add missing module to `requirements.txt`
- Example: `pip freeze | grep module-name >> requirements.txt`

### **"Permission denied: gunicorn"**
- **Fix**: Ensure `gunicorn` is in `requirements.txt`
- Already included ✅

### **"SQLALCHEMY_DATABASE_URI not set"**
- **Fix**: Set `DATABASE_URL` environment variable in Render
- App code should handle this automatically

---

## 📊 Monitoring

After deployment:

1. **View logs**: Render Dashboard → Service → Logs
2. **Check health**: Service shows "Live" status
3. **Test endpoint**: Visit your Render URL
4. **Monitor database**: Check Postgres service health

---

## 🔄 Redeploy

Every time you push to GitHub:
```bash
git add .
git commit -m "Update"
git push origin main
```

Render auto-redeploys (if auto-deploy enabled).

Manual redeploy:
- Render Dashboard → Service → Manual Deploy

---

## 📈 Scaling

Free tier includes:
- ✅ 750 hours/month compute
- ✅ 100GB bandwidth
- ✅ PostgreSQL database
- ✅ Auto-scaling (if needed)

For production:
- Upgrade to paid tier
- Enable auto-scaling
- Use Redis for sessions
- Add CDN for static files

---

## 🎯 Next Steps

1. ✅ Choose Option 1 or 2 above (make public or add token)
2. ✅ Verify `requirements.txt` exists in root
3. ✅ Ensure `render.yaml` is committed
4. ✅ Set DATABASE_URL in Render environment
5. ✅ Deploy!

---

## Need Help?

- **Render Docs**: https://render.com/docs
- **GitHub Tokens**: https://github.com/settings/tokens
- **Flask Deployment**: https://flask.palletsprojects.com/deployment/

---

**Choose Option 1 or 2, then redeploy!** 🚀
