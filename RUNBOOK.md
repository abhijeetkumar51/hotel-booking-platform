# Deployment & Operations Runbook

This guide contains deployment, configuration, backup, restore, and rollback procedures for the Hotel Booking Platform on an AWS EC2 instance.

---

## 1. AWS EC2 Setup

### Instance Specs
- **OS:** Ubuntu Server 24.04 LTS (HVM)
- **Instance Type:** `t2.micro` or `t3.micro` (Free-tier eligible)
- **Storage:** 20 GB gp3 root volume
- **Key Pair:** RSA key pair for SSH access

### Security Group Inbound Rules
| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP | SSH administration |
| 80 | TCP | 0.0.0.0/0 | HTTP (Nginx reverse proxy) |
| 443 | TCP | 0.0.0.0/0 | HTTPS (if domain configured) |

*Note: Application port (5000) and Database port (5432) must NOT be exposed publicly.*

---

## 2. Server Configuration

Connect via SSH:
```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

### 2.1 Install Docker and Nginx
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release nginx git

# Install Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Run docker without sudo
sudo usermod -aG docker ubuntu
newgrp docker
```

---

## 3. Reverse Proxy Setup (Nginx)

Create `/etc/nginx/sites-available/hotel-booking`:
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000/health;
        access_log off;
    }
}
```

Enable site:
```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/hotel-booking /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 4. Application Deployment

```bash
# Clone the repository
git clone https://github.com/abhijeetkumar51/hotel-booking-platform.git /home/ubuntu/app
cd /home/ubuntu/app

# Set production environment variables
cp .env.example .env
# Edit .env with strong production credentials
nano .env

# Start services
docker compose up -d --build
```

Verify status:
```bash
docker compose ps
curl http://localhost/health
curl http://localhost/ready
```

---

## 5. Database Backup and Restore

### Create Backup
```bash
mkdir -p /home/ubuntu/backups
BACKUP_FILE="/home/ubuntu/backups/db_backup_$(date +%Y%m%d_%H%M%S).dump"

docker exec -t hotel_db pg_dump -U hotel_user -d hotel_booking -F c -f /tmp/backup.dump
docker cp hotel_db:/tmp/backup.dump "$BACKUP_FILE"
echo "Backup saved to $BACKUP_FILE"
```

### Restore Backup
```bash
# Verify restore on a fresh test database
docker exec -it hotel_db psql -U hotel_user -d postgres -c "DROP DATABASE IF EXISTS hotel_restore_test; CREATE DATABASE hotel_restore_test;"
docker exec -i hotel_db pg_restore -U hotel_user -d hotel_restore_test < "$BACKUP_FILE"

# Verify tables
docker exec -it hotel_db psql -U hotel_user -d hotel_restore_test -c "SELECT COUNT(*) FROM reservations;"
```

---

## 6. Rollback Strategy

If a newly deployed image encounters an issue, rollback to the previous version tag:

```bash
# Set rollback image version
export ROLLBACK_TAG=v1.0.0

# Pull the stable image from Docker Hub
docker pull abhijeetkumar51/hotel-booking-platform:${ROLLBACK_TAG}

# Restart with previous image
docker compose up -d app

# Verify health
curl -f http://localhost/health
```

---

## 7. Troubleshooting Commands

- **Check logs:** `docker compose logs -f app`
- **Check database logs:** `docker compose logs -f db`
- **Restart container:** `docker compose restart app`
- **Check Nginx status:** `sudo systemctl status nginx`
- **Check disk usage:** `df -h` and `docker system df`
