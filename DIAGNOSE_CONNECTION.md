# DIAGNOSING CONNECTION REFUSED ERROR

## Quick Diagnostic Steps

Run these commands on your Lightsail instance:

```bash
# 1. SSH into instance
ssh -i /path/to/narrativeai-key.pem ubuntu@3.89.255.78

# Once connected, run these checks:

# 2. Check if service is running
sudo systemctl status narrativeai

# 3. If not running, check why
sudo journalctl -u narrativeai -n 50

# 4. Try to start it
sudo systemctl start narrativeai

# 5. Check status again
sudo systemctl status narrativeai

# 6. Test locally
curl http://localhost:8000/health

# 7. Check if process is listening on port 8000
sudo lsof -i :8000

# 8. Check systemd service file
sudo cat /etc/systemd/system/narrativeai.service

# 9. View all recent logs
sudo journalctl -u narrativeai -f
```

---

## Most Likely Issues

### Issue 1: Service Won't Start (Check Logs)
```bash
sudo journalctl -u narrativeai -n 100
```

**Look for errors like:**
- `AWS_ACCESS_KEY_ID not found`
- `ModuleNotFoundError`
- `Address already in use`

### Issue 2: AWS Credentials Missing
The systemd service file might be missing AWS environment variables.

```bash
sudo nano /etc/systemd/system/narrativeai.service
```

Should have:
```
Environment="AWS_ACCESS_KEY_ID=YOUR_KEY"
Environment="AWS_SECRET_ACCESS_KEY=YOUR_SECRET"
Environment="AWS_REGION=us-east-1"
```

If missing, add them, then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart narrativeai
```

### Issue 3: Port Already In Use
```bash
sudo lsof -i :8000
```

If another process is using port 8000:
```bash
sudo kill -9 <PID>
sudo systemctl restart narrativeai
```

### Issue 4: Check Firewall Rules
```bash
sudo ufw status
```

Make sure port 8000 is allowed.

---

## Recovery Steps

If service won't start, try this:

```bash
cd /home/ubuntu/NarrativeAI

# Activate venv
source venv/bin/activate

# Try running manually to see errors
python main.py

# If that works, restart service
sudo systemctl restart narrativeai
```

---

## Report Back With:

1. Output of: `sudo systemctl status narrativeai`
2. Output of: `sudo journalctl -u narrativeai -n 50`
3. Output of: `sudo lsof -i :8000`
4. Output of: `curl http://localhost:8000/health`

Then I can help fix the specific issue!
