# NarrativeAI - DEPLOYMENT EXECUTION GUIDE
## Ready to Deploy! 🚀

**Status:** ✅ Code on GitHub
**Time:** ~30 minutes
**Cost:** $5/month

---

## STEP 1: CREATE AWS LIGHTSAIL INSTANCE (5 min)

1. Go to: https://console.aws.amazon.com
2. Search "Lightsail" → Click it
3. Click "Create instance"
4. **Settings:**
   - Location: `us-east-1`
   - OS: `Ubuntu 24.04 LTS`
   - Plan: `Small ($5/month)` - 1GB RAM, 1 vCPU
   - Name: `narrativeai-instance`
5. **Create Key Pair:**
   - Click "Create new key pair"
   - Name: `narrativeai-key`
   - ⚠️ Download and save securely!
6. Click "Create instance"
7. ⏳ Wait 2-3 min for green "Running" status
8. 📝 **Copy your public IP** (e.g., 54.123.45.67)

✅ **Instance created!**

---

## STEP 2: SECURE SSH KEY (2 min)

On your machine where you downloaded the key:

```bash
chmod 600 /path/to/narrativeai-key.pem
ls -la /path/to/narrativeai-key.pem
# Should show: -rw------- (600)
```

✅ **SSH key secured!**

---

## STEP 3: SSH INTO INSTANCE (3 min)

```bash
ssh -i /path/to/narrativeai-key.pem ubuntu@YOUR_LIGHTSAIL_IP
```

Replace `YOUR_LIGHTSAIL_IP` with your actual IP.

You should see: `ubuntu@ip-xxx:~$`

✅ **Connected!**

---

## STEP 4: SETUP INSTANCE (10 min)

Run these commands on the Lightsail instance:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git

cd /home/ubuntu
git clone https://github.com/karlondon/NarrativeAI.git
cd NarrativeAI

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

⏳ Wait 2-3 minutes for pip to install dependencies.

```bash
cp .env.example .env
nano .env
```

Edit `.env` with your AWS credentials:
```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=YOUR_AWS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET
PORT=8000
HOST=0.0.0.0
ENV=production
```

Save: `Ctrl+X → Y → Enter`

Test locally:
```bash
python main.py
# Should show: INFO: Uvicorn running on http://0.0.0.0:8000
```

Press `Ctrl+C` to stop.

✅ **App works!**

---

## STEP 5: CREATE SYSTEMD SERVICE (5 min)

```bash
deactivate
sudo nano /etc/systemd/system/narrativeai.service
```

Paste this (replace YOUR_AWS_KEY and YOUR_AWS_SECRET):

```ini
[Unit]
Description=NarrativeAI PDF to Audiobook Converter
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/NarrativeAI
ExecStart=/home/ubuntu/NarrativeAI/venv/bin/python main.py
Restart=always
RestartSec=10
Environment="PORT=8000"
Environment="HOST=0.0.0.0"
Environment="AWS_REGION=us-east-1"
Environment="AWS_ACCESS_KEY_ID=YOUR_AWS_KEY"
Environment="AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET"

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+X → Y → Enter`

```bash
sudo systemctl daemon-reload
sudo systemctl enable narrativeai
sudo systemctl start narrativeai
sudo systemctl status narrativeai
```

Should show: `Active: active (running)`

```bash
exit
```

✅ **Service running!**

---

## STEP 6: ADD GITHUB SECRETS (5 min)

### Get SSH Private Key
```bash
cat /path/to/narrativeai-key.pem
```
Copy the entire output.

### Add to GitHub
1. Go to: https://github.com/karlondon/NarrativeAI/settings/secrets/actions
2. Click "New repository secret" for each:

| Name | Value |
|------|-------|
| AWS_ACCESS_KEY_ID | Your AWS access key |
| AWS_SECRET_ACCESS_KEY | Your AWS secret |
| LIGHTSAIL_HOST | Your instance IP |
| LIGHTSAIL_USER | ubuntu |
| LIGHTSAIL_SSH_KEY | Full SSH private key |

✅ **Secrets configured!**

---

## STEP 7: TEST DEPLOYMENT (5 min)

```bash
cd /Users/karthiksankaran/PS-Scripts/NarrativeAI

echo "# Live on AWS! 🚀" >> README.md
git add README.md
git commit -m "Test deployment"
git push origin main
```

Watch GitHub:
1. Go to: https://github.com/karlondon/NarrativeAI/actions
2. Click running workflow
3. Wait 2-3 minutes

Should show: ✅ All checks passed

✅ **Auto-deployment works!**

---

## STEP 8: VERIFY API (5 min)

Test endpoints:

```bash
# Health check
curl http://YOUR_LIGHTSAIL_IP:8000/health
# Should return: {"status": "healthy", "version": "0.1.0", "aws_ok": true}

# API docs (open in browser)
http://YOUR_LIGHTSAIL_IP:8000/docs
```

Try uploading a PDF:
```bash
curl -X POST "http://YOUR_LIGHTSAIL_IP:8000/upload" \
  -F "file=@/path/to/test.pdf"
```

You should get a `job_id` back. ✅ **Live!**

---

## 🎉 DEPLOYMENT COMPLETE!

### Your API is LIVE at:
```
http://YOUR_LIGHTSAIL_IP:8000
```

### API Endpoints:
- `GET /health` - Health check
- `GET /docs` - Swagger documentation
- `POST /upload` - Upload PDF
- `GET /jobs/{id}` - Check status
- `GET /jobs/{id}/download` - Download audio

### Auto-Deploys On:
- Every git push to main
- Daily at 2 AM UTC
- Manual GitHub Actions trigger

---

## 💰 MONTHLY COST

| Service | Cost |
|---------|------|
| Lightsail | $5.00 |
| Polly (Free) | $0.00 |
| S3 (Free) | $0.00 |
| GitHub | $0.00 |
| **TOTAL** | **$5.00** |

---

## 📊 QUICK COMMANDS

Monitor service:
```bash
ssh -i narrativeai-key.pem ubuntu@YOUR_IP
sudo journalctl -u narrativeai -f
```

Update code (just push to GitHub):
```bash
# Edit code locally
git add .
git commit -m "Your changes"
git push origin main
# Auto-deploys in ~3 minutes!
```

---

## ✨ YOUR NARRATIVEAI IS NOW LIVE! 🚀

- 24/7 production server
- Auto-deploy on every git push
- Daily scheduled backups
- Monitoring via logs
- Cost: $5/month
- Status: ✅ PRODUCTION READY
