# ─────────────────────────────────────────────────────────────
#  TPCODL Dashboard — Render.com cloud worker
#  Python 3.11 + Chrome + ChromeDriver (system install, no webdriver-manager)
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    git \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libx11-xcb1 \
    xdg-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Google Chrome (direct .deb) ───────────────────────────────
RUN wget -q -O /tmp/chrome.deb \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── ChromeDriver — matching version via Chrome for Testing ────
# Reads the installed Chrome version and downloads exact matching ChromeDriver
RUN CHROME_VER=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+') \
    && echo "Chrome version: $CHROME_VER" \
    && MAJOR=$(echo $CHROME_VER | cut -d. -f1) \
    && DRIVER_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VER}/linux64/chromedriver-linux64.zip" \
    && echo "Downloading ChromeDriver from: $DRIVER_URL" \
    && wget -q -O /tmp/chromedriver.zip "$DRIVER_URL" \
    && unzip -q /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64 \
    && chromedriver --version

# ── Python dependencies ───────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────
COPY . .

# ── Runtime directories ───────────────────────────────────────
RUN mkdir -p /app/downloads /app/repo

# ── Entry point ───────────────────────────────────────────────
CMD ["python", "main.py"]
