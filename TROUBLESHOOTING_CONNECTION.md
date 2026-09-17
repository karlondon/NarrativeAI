# TROUBLESHOOTING DEPLOYMENT ERROR
## "Couldn't connect to server" on port 8000

---

## STEP 1: SSH INTO YOUR LIGHTSAIL INSTANCE

On your local machine:

```bash
ssh -i /path/to/narrativeai-key.pem ubuntu@YOUR_LIGHTSAIL_IP
```

Replace `YOUR_LIGHTSAIL_IP` with your actual Lightsail instance IP.

---

## STEP 2: CHECK SERVICE STATUS

Once SSH'd in, run:

```bash
sudo systemctl status narrativeai
```

**Look for one of these:**

### ✅ If service is RUNNING:
```
● narrativeai.service - NarrativeAI PDF to Audiobook Converter
     Loaded: loaded
     Active: active (running)
```

**Then go to STEP 3**

### ❌ If service is NOT RUNNING:
```
● narrativeai.service
     Active: inactive (dead)
```

**Then run:**
```bash
sudo systemctl start narrativeai
sudo systemctl status narrativeai
```

---

## STEP 3: CHECK SERVICE LOGS

If service won't start, check logs:

```bash
sudo journalctl -u narrativeai -n 100
```

**Look for error messages. Common errors:**

### Error: "AWS_ACCESS_KEY_ID not found"
**Solution:** Make sure environment variables in systemd service file are set.
```bash
sudo nano /etc/systemd/system/narrativeai.service
```
Verify these lines exist:
```
Environment="AWS_ACCESS_KEY_ID=YOUR_KEY"
Environment="AWS_SECRET_ACCESS_KEY=YOUR_SECRET"
```

### Error: "ModuleNotFoundError"
**Solution:** Virtual environment not activated. Reinstall:
```bash
cd /home/ubuntu/NarrativeAI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Error: "Address already in use"
**Solution:** Another process is using port 8000. Kill it:
```bash
sudo lsof -i :8000
sudo kill -9 <PID>
sudo systemctl restart narrativeai
```

---

## STEP 4: TEST LOCALLY

If service is running, test it locally on the instance:

```bash
curl http://localhost:8000/health
```

**You should see:**
```json
{"status":"healthy","version":"0.1.0","aws_ok":true}
```

### ✅ If this works:
The service is running fine. Go to STEP 5.

### ❌ If this fails:
The app crashed. Check logs again:
```bash
sudo journalctl -u narrativeai -f
# This shows live logs. Try making a curl request and watch for errors
```

---

## STEP 5: CHECK LIGHTSAIL FIREWALL

The instance might be blocking port 8000. Let's open it:

1. **Go to AWS Lightsail Console:** https://console.aws.amazon.com/lightsail/
2. **Click on your instance:** "narrativeai-instance"
3. **Click "Networking"** tab
4. **Under "Firewall"** section:**
   - Click **"+ Add rule"**
   - **Protocol:** TCP
   - **Port or port range:** 8000
   - **Allowed sources:** All IPv4 (0.0.0.0/0)
   - Click **"Create"**

5. **Verify rule was added** - you should see:
   ```
   TCP    8000    0.0.0.0/0 (All IPv4)
   ```

✅ Port 8000 is now open!

---

## STEP 6: TEST REMOTE CONNECTION

Back on your local machine, test the remote API:

```bash
curl http://YOUR_LIGHTSAIL_IP:8000/health
```

**You should see:**
```json
{"status":"healthy","version":"0.1.0","aws_ok":true}
```

✅ If this works, your deployment is actually fine!

---

## STEP 7: RETRY GITHUB DEPLOYMENT

Now that everything is working:

```bash
cd /Users/karthiksankaran/PS-Scripts/NarrativeAI

# Make a test commit
echo "# Deployment retry after fix" >> README.md

# Commit and push
git add README.md
git commit -m "Retry deployment"
git push origin main
```

**Then:**
1. Go to: https://github.com/karlondon/NarrativeAI/actions
2. Watch the workflow
3. It should succeed ✅

---

## SUMMARY OF FIXES

| Issue | Solution |
|-------|----------|
| Service not running | `sudo systemctl start narrativeai` |
| AWS credentials missing | Add to systemd service file |
| Port 8000 blocked | Add firewall rule in Lightsail |
| App crashes on start | Check logs: `sudo journalctl -u narrativeai -f` |
| GitHub health check fails | Make sure API responds: `curl http://IP:8000/health` |

---

## QUICK CHECKLIST

Run through these on your Lightsail instance:

```bash
# 1. Check service status
sudo systemctl status narrativeai
# Should show: Active: active (running)

# 2. Test locally
curl http://localhost:8000/health
# Should return: {"status":"healthy",...}

# 3. Check firewall rule exists
# Go to AWS Lightsail → Networking → check port 8000 is listed

# 4. Test remote
curl http://YOUR_LIGHTSAIL_IP:8000/health
# Should return: {"status":"healthy",...}
```

If all 4 pass, your deployment is working! ✅

---

## NEED HELP?

**Most likely cause:** Port 8000 is blocked by Lightsail firewall.

**Quick fix:**
1. Go to AWS Lightsail Console
2. Click your instance
3. Click "Networking"
4. Add firewall rule: TCP port 8000, allow all IPv4
5. Wait 1 minute for rule to apply
6. Retry deployment

**If it still fails:**
SSH into instance and run:
```bash
sudo journalctl -u narrativeai -n 50
```
Share the error messages and I'll help debug!
