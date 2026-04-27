# ─────────────────────────────────────────────────────────────
#  TPCODL Dashboard — Render.com cloud worker
#  Base: Python 3.11 slim + Chrome headless + ChromeDriver
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System deps + Chrome ──────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip curl git \
    fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libnspr4 libnss3 libxcomposite1 libxdamage1 libxfixes3 \
    libxkbcommon0 libxrandr2 xdg-utils \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App source ────────────────────────────────────────────────
COPY . .

# ── Directories used at runtime ───────────────────────────────
RUN mkdir -p /app/downloads /app/repo

# ── Entry point ───────────────────────────────────────────────
CMD ["python", "main.py"]
