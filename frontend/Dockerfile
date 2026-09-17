FROM node:20-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV BACKEND_URL=http://backend:8000
RUN npm run build
EXPOSE 3000
CMD ["npx", "next", "start", "--port", "3000", "--hostname", "0.0.0.0"]
