# ─────────────────────────────────────────────────────────────
#  TPCODL Dashboard — Render.com cloud worker
#  Base: Python 3.11 slim + Chrome headless + ChromeDriver
#  Fixed: uses modern .deb direct download (no apt-key needed)
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System deps ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates unzip curl git \
    fonts-liberation libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libnspr4 libnss3 libxcomposite1 libxdamage1 libxfixes3 \
    libxkbcommon0 libxrandr2 xdg-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Chrome — direct .deb download (no apt-key, no repo needed) ──
RUN wget -q -O /tmp/chrome.deb \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
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
