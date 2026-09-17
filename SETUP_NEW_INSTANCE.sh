#!/bin/bash
# NarrativeAI Setup for New Lightsail Medium Instance
# Run this script on your new instance: bash SETUP_NEW_INSTANCE.sh

echo "🚀 Setting up NarrativeAI on new Medium instance..."

# Step 1: Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git

# Step 2: Clone repository
echo "📥 Cloning NarrativeAI repository..."
cd /home/ubuntu
git clone https://github.com/karlondon/NarrativeAI.git
cd NarrativeAI

# Step 3: Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Step 4: Install dependencies
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

# Step 5: Configure environment
echo "⚙️ Configuring .env file..."
cp .env.example .env
echo ""
echo "⚠️  IMPORTANT: Edit your AWS credentials in .env"
echo "Run: nano /home/ubuntu/NarrativeAI/.env"
echo "Add your AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
echo ""

# Step 6: Create systemd service
echo "🔧 Creating systemd service..."
cat > /tmp/narrativeai.service << 'EOF'
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
Environment="AWS_ACCESS_KEY_ID=YOUR_AWS_ACCESS_KEY"
Environment="AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET_KEY"

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/narrativeai.service /etc/systemd/system/narrativeai.service

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your AWS credentials:"
echo "   nano /home/ubuntu/NarrativeAI/.env"
echo ""
echo "2. Edit systemd service with your AWS credentials:"
echo "   sudo nano /etc/systemd/system/narrativeai.service"
echo "   Replace: YOUR_AWS_ACCESS_KEY and YOUR_AWS_SECRET_KEY"
echo ""
echo "3. Start the service:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable narrativeai"
echo "   sudo systemctl start narrativeai"
echo "   sudo systemctl status narrativeai"
echo ""
echo "4. Test health check:"
echo "   curl http://localhost:8000/health"
echo ""
