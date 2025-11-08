#!/bin/bash


sudo apt-get install ffmpeg


# Exit immediately on error
set -e


# Update package list
sudo apt update

# Install curl if not already installed
sudo apt install curl -y

# Install Node.js (LTS version) using NodeSource
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# Verify installations
node -v
npm -v


echo "📦 Installing base dependencies..."
npm install

echo "🎨 Installing Tailwind CSS and related packages..."
npm install -D tailwindcss@3.4.17 postcss autoprefixer @tailwindcss/postcss @radix-ui/react-switch @fontsource/chakra-petch


echo "💫 Installing animations and routing..."
npm install framer-motion react-router-dom

# Only initialize Tailwind config if not present
if [ ! -f tailwind.config.js ]; then
  echo "🛠️ Initializing Tailwind config..."
  npx tailwindcss init -p
fi

# Ensure shadcn components are scaffolded
if [ ! -f components.json ]; then
  echo "🧱 Setting up shadcn components..."
  npx shadcn@latest init
fi

echo "🧩 Adding common UI components (label, textarea)..."
npx shadcn@latest add label textarea switch dialog


echo "✅ Tailwind & shadcn-ui configured."
echo "🚀 You're ready! Run the dev server with:"
echo "   npm run dev"
