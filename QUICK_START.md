# NarrativeAI - Quick Start Guide

## ✅ Project Ready for Deployment!

All files created in: `/Users/karthiksankaran/PS-Scripts/NarrativeAI/`

### Files Created:
✅ main.py - FastAPI application
✅ requirements.txt - Dependencies  
✅ test_main.py - Unit tests
✅ Dockerfile - Container setup
✅ docker-compose.yml - Dev environment
✅ .env.example - Config template
✅ .gitignore - Git rules
✅ README.md - Documentation
✅ .github/workflows/deploy.yml - CI/CD pipeline

---

## 🚀 STEP 1: Push to GitHub

```bash
cd /Users/karthiksankaran/PS-Scripts/NarrativeAI
git init
git config user.name "Your Name"
git config user.email "your@email.com"
git add .
git commit -m "Initial NarrativeAI MVP"
git remote add origin https://github.com/karlondon/NarrativeAI.git
git branch -M main
git push -u origin main
```

---

## 🌐 STEP 2: Create AWS Lightsail Instance

1. Go to: https://console.aws.amazon.com
2. Search "Lightsail" → Click it
3. Click "Create instance"
4. Settings:
   - Location: us-east-1
   - OS: Ubuntu 24.04 LTS
   - Plan: Small ($5/month)
   - Name: narrativeai-instance
5. Create new key pair: "narrativeai-key"
6. Click "Create instance"
7. ⏱️ Wait 2-3 minutes (green "Running" status)
8. 📝 **Copy instance IP address** (you'll need it!)

---

## ⚙️ STEP 3: Setup Lightsail

```bash
# On your machine:
chmod 600 /path/to/narrativeai-key.pem
ssh -i /path/to/narrativeai-key.pem ubuntu@YOUR_IP

# On Lightsail instance:
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git

cd /home/ubuntu
git clone https://github.com/karlondon/NarrativeAI.git
cd NarrativeAI

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
```

Edit .env with AWS credentials, save (Ctrl+X, Y, Enter)

Continue on instance:
```bash
deactivate
sudo nano /etc/systemd/system/narrativeai.service
```

Paste this service file (replace YOUR_KEY and YOUR_SECRET):
```ini
[Unit]
Description=NarrativeAI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/NarrativeAI
ExecStart=/home/ubuntu/NarrativeAI/venv/bin/python main.py
Restart=always
RestartSec=10
Environment="AWS_ACCESS_KEY_ID=YOUR_KEY"
Environment="AWS_SECRET_ACCESS_KEY=YOUR_SECRET"

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable narrativeai
sudo systemctl start narrativeai
sudo systemctl status narrativeai
```

✅ Service is running!

---

## 🔑 STEP 4: Add GitHub Secrets

1. Get SSH key: `cat /path/to/narrativeai-key.pem`
2. Go to GitHub repo Settings → Secrets and variables → Actions
3. Add 5 secrets:

| Name | Value |
|------|-------|
| AWS_ACCESS_KEY_ID | Your AWS access key |
| AWS_SECRET_ACCESS_KEY | Your AWS secret |
| LIGHTSAIL_HOST | Your instance IP |
| LIGHTSAIL_USER | ubuntu |
| LIGHTSAIL_SSH_KEY | Full SSH key content |

---

## 🚀 STEP 5: Deploy

Make a test commit:
```bash
cd /Users/karthiksankaran/PS-Scripts/NarrativeAI
echo "# Live on AWS! 🚀" >> README.md
git add README.md
git commit -m "Test deploy"
git push origin main
```

Watch GitHub Actions tab (2-3 minutes to complete)

---

## ✅ STEP 6: Verify

```bash
# Health check
curl http://YOUR_IP:8000/health

# API docs
http://YOUR_IP:8000/docs (open in browser)

# Test upload
curl -X POST "http://YOUR_IP:8000/upload" -F "file=@test.pdf"

# Check status
curl http://YOUR_IP:8000/jobs/JOB_ID_HERE

# Download audio
curl http://YOUR_IP:8000/jobs/JOB_ID_HERE/download -o audio.mp3
```

---

## 🔧 STEP 7: Troubleshooting

Service not working?
```bash
sudo systemctl status narrativeai
sudo journalctl -u narrativeai -n 50
sudo systemctl restart narrativeai
```

---

## 💰 STEP 8: Cost

| Service | Cost/Month |
|---------|-----------|
| Lightsail | $5 |
| Polly | $0 (5M chars free) |
| S3 | $0 (5GB free) |
| GitHub | $0 |
| **TOTAL** | **$5** |

---

## 🎉 Done!

Your NarrativeAI is live at: `http://YOUR_IP:8000`

Auto-deploys on: git push, daily, or manual trigger

**Next:** Upload PDFs and generate audiobooks! 🎤📚
