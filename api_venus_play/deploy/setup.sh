#!/usr/bin/env bash
set -e

DOMAIN="venusmovel.space"

# 1. Pacotes de sistema
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv build-essential git nginx certbot python3-certbot-nginx

# 2. Usuário dedicado
id api &>/dev/null || sudo adduser api --disabled-password --gecos ""

# 3. Clonar/atualizar repo
sudo -iu api bash <<'INNER'
  if [ ! -d ~/venus-api ]; then
    git clone https://github.com/Venusofcxp/VenusPlay-.git ~/VenusPlay-
  else
    cd ~/VenusPlay- && git pull
  fi

  cd ~/VenusPlay-
  python3.11 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip wheel
  pip install -r requirements.txt
INNER

# 4. Copiar serviço systemd
sudo cp deploy/venus.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now venus

# 5. Copiar bloco Nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/venus
sudo ln -sf /etc/nginx/sites-available/venus /etc/nginx/sites-enabled/venus
sudo nginx -t && sudo systemctl reload nginx

# 6. Gerar / renovar certificado Let’s Encrypt
sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@"$DOMAIN" --redirect
