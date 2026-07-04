#!/bin/bash
# Скрипт инициализации Let's Encrypt сертификатов

set -e

DOMAIN="gordian-forge.ru"  # ← ЗАМЕНИТЕ НА СВОЙ ДОМЕН
EMAIL="danbgavindv90835@gmail.com"   # ← ВАШ EMAIL

echo "🔐 Инициализация SSL для $DOMAIN"

# 1. Создаём временный self-signed сертификат для первого запуска Nginx
echo "📜 Создаём временный сертификат..."
mkdir -p ./nginx/certbot-conf/live/$DOMAIN
openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
    -keyout ./nginx/certbot-conf/live/$DOMAIN/privkey.pem \
    -out ./nginx/certbot-conf/live/$DOMAIN/fullchain.pem \
    -subj "/CN=localhost"

# Копируем необходимые файлы для Nginx
cat > ./nginx/certbot-conf/options-ssl-nginx.conf << 'EOF'
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
ssl_prefer_server_ciphers off;
EOF

touch ./nginx/certbot-conf/ssl-dhparams.pem

# 2. Заменяем домен в nginx.conf
sed -i "s/gordian-forge.ru/$DOMAIN/g" ./nginx/nginx.conf

# 3. Запускаем Nginx с временным сертификатом
echo "🚀 Запускаем Nginx..."
docker compose -f docker-compose.prod.yml up -d nginx

# 4. Ждём, пока Nginx запустится
sleep 5

# 5. Получаем настоящий сертификат через Certbot
echo "🔐 Получаем Let's Encrypt сертификат..."
docker run --rm \
    -v ./nginx/certbot-conf:/etc/letsencrypt \
    -v ./nginx/certbot-www:/var/www/certbot \
    certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email $EMAIL \
    --agree-tos \
    --no-eff-email \
    -d $DOMAIN \
    -d www.$DOMAIN

# 6. Перезапускаем Nginx с настоящим сертификатом
echo "🔄 Перезапускаем Nginx..."
docker compose -f docker-compose.prod.yml restart nginx

echo "✅ SSL сертификат получен и установлен!"
echo "🌐 Ваш сайт доступен по адресу: https://$DOMAIN"