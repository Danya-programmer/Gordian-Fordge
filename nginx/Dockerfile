
FROM nginx:1.31.2-alpine

# Удаляем дефолтный конфиг
RUN rm /etc/nginx/conf.d/default.conf

# Копируем наш конфиг
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Создаём директорию для certbot challenge
RUN mkdir -p /var/www/certbot

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]