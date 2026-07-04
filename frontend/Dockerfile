FROM node:24-alpine

WORKDIR /app

# Сначала только package.json для кэширования слоя
COPY package.json package-lock.json* ./

RUN npm install

# Копируем остальной код
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]