# ─────────────────────────────────────────────────────────────
#  TPCODL Dashboard — Render.com cloud worker
#  Key fix: Xvfb virtual display — Chrome runs as if it has a
#  real screen, exactly like your PC. No headless mode.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System dependencies + Xvfb virtual display ───────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl git unzip gnupg ca-certificates \
    xvfb \
    x11-utils \
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
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Google Chrome (direct .deb) ───────────────────────────────
RUN wget -q -O /tmp/chrome.deb \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── ChromeDriver — exact version match ───────────────────────
RUN CHROME_VER=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+\.\d+') \
    && echo "Chrome: $CHROME_VER" \
    && wget -q -O /tmp/chromedriver.zip \
       "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VER}/linux64/chromedriver-linux64.zip" \
    && unzip -q /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64 \
    && chromedriver --version

# ── Python dependencies ───────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App source ────────────────────────────────────────────────
COPY . .
RUN mkdir -p /app/downloads /app/repo

# ── Startup: launch Xvfb virtual display then run app ────────
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
