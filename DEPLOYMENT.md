# AWS EC2 Deployment Guide for SuperBryn Backend

## Prerequisites

- AWS Account (free tier eligible)
- GitHub repo with your backend code
- SSH client (Terminal on Mac)

---

## Step 1: Launch EC2 Instance

1. **Go to AWS Console** → EC2 → **Launch Instance**

2. **Configure:**

   | Setting | Value |
   |---------|-------|
   | Name | `superbryn-backend` |
   | AMI | **Ubuntu Server 24.04 LTS** (Free tier) |
   | Instance type | **t2.micro** (Free tier) or **t3.micro** |
   | Key pair | Create new → Download `.pem` file |
   | Network | Allow SSH (22), HTTP (80), HTTPS (443), Custom TCP (8000) |

3. **Launch instance**

---

## Step 2: Connect to EC2

```bash
# Make key file secure
chmod 400 ~/Downloads/your-key.pem

# Connect via SSH
ssh -i ~/Downloads/your-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
```

---

## Step 3: Install Dependencies

Run these commands on EC2:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12
sudo apt install -y python3.12 python3.12-venv python3-pip git

# Install UV (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Install nginx (reverse proxy)
sudo apt install -y nginx
```

---

## Step 4: Clone Your Repo

```bash
# Clone your backend
cd ~
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO/backend

# OR if private repo, use SSH key or token
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

---

## Step 5: Setup Environment

```bash
# Create .env file
nano .env
```

Paste your environment variables (copy from `env.txt`):

```env
DATABASE_URL=postgresql+asyncpg://postgres:Arora%409359580847@db.dpygpqtqnpnktxanrfho.supabase.co:5432/postgres?ssl=require
LIVEKIT_URL=wss://my-testing-project-a0z1jqsb.livekit.cloud
LIVEKIT_API_KEY=APIMZSgqVvhTVFh
LIVEKIT_API_SECRET=vUITv8TFgHU4TXBKfaev9QK3JGdu1RZueXllTW6I2VSB
DEEPGRAM_API_KEY=34c8039441dfb44faf1fe1bb74338554b7107a58
CARTESIA_API_KEY=sk_car_u6ckk5ypLth32CR7o7RgzV
OPENAI_API_KEY=your_openai_key
BEYOND_PRESENCE_API_KEY=sk-ZLJMpNCvWf4-8Gz0JhvYX7zHcQOv5GyiMTEyP1pTvJY
BEYOND_PRESENCE_AVATAR_ID=b5bebaf9-ae80-4e43-b97f-4506136ed926
APP_ENV=production
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## Step 6: Install Python Dependencies

```bash
# Install dependencies with UV
uv sync

# Run database migrations
uv run alembic upgrade head
```

---

## Step 7: Create Systemd Service (Auto-start on reboot)

```bash
sudo nano /etc/systemd/system/superbryn.service
```

Paste:

```ini
[Unit]
Description=SuperBryn Voice Agent Backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/YOUR_REPO/backend
ExecStart=/home/ubuntu/.local/bin/uv run start.py
Restart=always
RestartSec=10
Environment=PATH=/home/ubuntu/.local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable superbryn
sudo systemctl start superbryn

# Check status
sudo systemctl status superbryn
```

---

## Step 8: Configure Nginx (Reverse Proxy)

```bash
sudo nano /etc/nginx/sites-available/superbryn
```

Paste:

```nginx
server {
    listen 80;
    server_name YOUR_EC2_PUBLIC_IP;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/superbryn /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Step 9: Test Your Deployment

```bash
# Check if service is running
sudo systemctl status superbryn

# Check logs
sudo journalctl -u superbryn -f

# Test API
curl http://YOUR_EC2_PUBLIC_IP/health
```

---

## Step 10: Update Frontend

Update your frontend `.env` to point to EC2:

```env
VITE_API_URL=http://YOUR_EC2_PUBLIC_IP
```

---

## Optional: Add HTTPS with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## Useful Commands

| Command | Description |
|---------|-------------|
| `sudo systemctl restart superbryn` | Restart backend |
| `sudo journalctl -u superbryn -f` | View logs |
| `sudo systemctl status superbryn` | Check status |
| `cd ~/YOUR_REPO && git pull && uv sync` | Update code |

---

## Cost Estimate

| Resource | Free Tier | After Free Tier |
|----------|-----------|-----------------|
| t2.micro EC2 | 750 hrs/month for 12 months | ~$8.50/month |
| Data transfer | 100GB/month | $0.09/GB |
