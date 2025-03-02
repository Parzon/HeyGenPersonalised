# Use lightweight Node.js image
FROM node:18-alpine

# Install dependencies for node-gyp
RUN apk add --no-cache python3 py3-pip make g++ && \
    ln -sf python3 /usr/bin/python

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy the rest of the frontend code
COPY . .

# Disable ESLint in Next.js build
ENV NEXT_DISABLE_ESLINT=true

# Run Next.js build
RUN npm run build

# Expose port
EXPOSE 3000

CMD ["npm", "run", "start"]
