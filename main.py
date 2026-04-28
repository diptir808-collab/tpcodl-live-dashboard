# -*- coding: utf-8 -*-
"""
TPCODL Dashboard – GitHub Actions version
Runs on GitHub's 2GB Ubuntu runner. No Render, no Flask.
Downloads reports, generates index.html, pushes to gh-pages.
"""

import os, re, time, glob, logging, shutil, subprocess, json
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# ========== CONFIGURATION (from environment variables) ==========
USERNAME = os.environ["TPCODL_USER"]
PASSWORD = os.environ["TPCODL_PASS"]
GITHUB_TOKEN = os.environ["GH_TOKEN"]
REPO_NAME = os.environ["GITHUB_REPOSITORY"]   # e.g. diptir808-collab/tpcdl-live-dashboard
BRANCH = "gh-pages"

DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# ========== Helper functions ==========
def get_column(df, keywords):
    if df is None or df.empty:
        return None
    for col in df.columns:
        for kw in keywords:
            if kw.upper() in col.upper():
                return col
    return None

def get_col_by_index(df, col_index, fallback_keywords=None):
    if df is None or df.empty:
        return None
    cols = list(df.columns)
    if col_index < len(cols):
        return cols[col_index]
    if fallback_keywords:
        return get_column(df, fallback_keywords)
    return None

def assign_shift(dt):
    if dt is None or pd.isnull(dt):
        return "Unknown"
    t = dt.hour * 60 + dt.minute
    if 7*60 <= t <= 14*60+30:
        return "A"
    elif 14*60+31 <= t <= 22*60:
        return "B"
    else:
        return "C"

def load_ptw_data(file_path):
    df = pd.read_excel(file_path)
    date_col = get_column(df, ['PTW ISSUED DATE'])
    time_col = get_column(df, ['PTW ISSUED TIME'])
    if date_col and time_col:
        df['datetime'] = pd.to_datetime(
            df[date_col].astype(str) + ' ' + df[time_col].astype(str),
            format='mixed', dayfirst=True, errors='coerce'
        )
        df = df.dropna(subset=['datetime'])
        df['shift'] = df['datetime'].apply(assign_shift)
        df['hour'] = df['datetime'].dt.hour
    return df

def load_tripping_data(file_path):
    df = pd.read_excel(file_path)
    dt_col = get_column(df, ['INTERRUPTION START TIME', 'START TIME'])
    if dt_col:
        df['start_dt'] = pd.to_datetime(df[dt_col], format='mixed', dayfirst=True, errors='coerce')
        end_col = get_column(df, ['INTERRUPTION END TIME', 'END TIME',
                                   'RESTORATION TIME', 'RECOVERY TIME'])
        if end_col:
            df['end_dt'] = pd.to_datetime(df[end_col], format='mixed', dayfirst=True, errors='coerce')
            df['duration_min'] = (df['end_dt'] - df['start_dt']).dt.total_seconds() / 60.0
        df = df.dropna(subset=['start_dt'])
        df['shift'] = df['start_dt'].apply(assign_shift)
        df['hour'] = df['start_dt'].dt.hour
    return df

def df_to_json_safe(df):
    if df.empty:
        return "[]"
    d = df.copy()
    for col in d.select_dtypes(include=['datetime64[ns]', 'datetimetz']).columns:
        d[col] = d[col].astype(str)
    return d.where(pd.notnull(d), other=None).to_json(orient='records', force_ascii=False)

def solve_captcha(text):
    m = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', text)
    return str(eval(m.group(1) + m.group(2) + m.group(3))) if m else ""

def login(driver, wait):
    log.info("Logging in …")
    driver.get("https://kavach.tpodisha.com/LoginPage")
    time.sleep(3)
    try:
        wait.until(EC.presence_of_element_located((By.ID, "txtLogin"))).send_keys(USERNAME)
        driver.find_element(By.ID, "txtPassword").send_keys(PASSWORD)
        try:
            cb = driver.find_element(By.XPATH, "//input[@type='checkbox']")
            if not cb.is_selected():
                driver.execute_script("arguments[0].click();", cb)
        except:
            pass
        try:
            cap = wait.until(EC.presence_of_element_located((By.ID, "lblCaptcha")))
            ans = solve_captcha(cap.get_attribute("value") or cap.text)
            if ans:
                driver.find_element(By.XPATH, "//input[contains(@placeholder,'captcha')]").send_keys(ans)
                log.info(f"Captcha solved: {ans}")
        except Exception as e:
            log.warning(f"Captcha skip: {e}")
        try:
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'SUBMIT')]")))
            driver.execute_script("arguments[0].click();", btn)
        except:
            driver.find_element(By.ID, "txtPassword").send_keys(Keys.ENTER)
        time.sleep(5)
        if "LoginPage" in driver.current_url:
            log.error("Login failed")
            return False
        log.info("Login OK ✓")
        return True
    except Exception as e:
        log.error(f"Login error: {e}")
        return False

def download_report(driver, wait, report_type):
    today = datetime.now().strftime("%Y-%m-%d")
    log.info(f"Downloading {report_type} …")
    try:
        rm = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@href,'#') and contains(.,'Reports')]")))
        ActionChains(driver).move_to_element(rm).click().perform()
        time.sleep(2)
        ro = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//ul[contains(@class,'dropdown-menu')]//a[normalize-space(text())='Reports']")))
        driver.execute_script("arguments[0].click();", ro)
        time.sleep(4)
        Select(wait.until(EC.presence_of_element_located(
            (By.ID, "MainContent_ddl_ptwtripping")))).select_by_visible_text(report_type)
        time.sleep(2)

        if "Tripping" in report_type:
            try:
                status_ddl = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//select[contains(@id,'Status') or contains(@id,'status') "
                               "or contains(@id,'ddl_status') or contains(@id,'ddlStatus')]")))
                Select(status_ddl).select_by_visible_text("LIVE")
                log.info("Tripping STATUS → LIVE ✓")
                time.sleep(1)
            except Exception as e:
                log.warning(f"STATUS LIVE failed: {e}")
                try:
                    status_ddl = driver.find_element(By.XPATH,
                        "//select[contains(@id,'Status') or contains(@id,'status') "
                        "or contains(@id,'ddl_status') or contains(@id,'ddlStatus')]")
                    Select(status_ddl).select_by_value("LIVE")
                    log.info("Tripping STATUS → LIVE (by value) ✓")
                    time.sleep(1)
                except Exception as e2:
                    log.warning(f"STATUS fallback failed: {e2}")

        for fid, val in [("MainContent_txt_from_date", today), ("MainContent_txt_to_date", today)]:
            el = wait.until(EC.presence_of_element_located((By.ID, fid)))
            driver.execute_script("arguments[0].value=arguments[1];", el, val)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", el)
        time.sleep(2)
        for fid, val in [("MainContent_txt_from_time", "00:00"), ("MainContent_txt_to_time", "23:59")]:
            try:
                el = driver.find_element(By.ID, fid)
                driver.execute_script("arguments[0].value=arguments[1];", el, val)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", el)
            except:
                pass

        eb = wait.until(EC.element_to_be_clickable((By.ID, "MainContent_btnExport")))
        driver.execute_script("arguments[0].scrollIntoView(true);", eb)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", eb)
        log.info("Export clicked — waiting for file …")

        existing = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*.xls*")))
        deadline = time.time() + 120
        while time.time() < deadline:
            current = set(glob.glob(os.path.join(DOWNLOAD_DIR, "*.xls*")))
            nf = [f for f in (current - existing) if not f.endswith(".crdownload")]
            if nf:
                latest = max(nf, key=os.path.getmtime)
                log.info(f"Downloaded → {latest}")
                return latest
            time.sleep(2)
        log.error(f"Timeout waiting for {report_type}")
    except Exception as e:
        log.error(f"download_report error: {e}")
    return None

def generate_dashboard(ptw_file, trip_file, output_html):
    ptw_df = load_ptw_data(ptw_file) if ptw_file and os.path.exists(ptw_file) else pd.DataFrame()
    trip_df = load_tripping_data(trip_file) if trip_file and os.path.exists(trip_file) else pd.DataFrame()

    circle_col_p = get_column(ptw_df, ['CIRCLE NAME', 'CIRCLE'])
    circle_col_t = get_column(trip_df, ['CIRCLE NAME', 'CIRCLE'])
    div_col_p = get_column(ptw_df, ['DIVISION NAME', 'DIVISION'])
    div_col_t = get_column(trip_df, ['DIVISION NAME', 'DIVISION'])
    status_col_p = get_column(ptw_df, ['STATUS'])
    status_col_t = get_column(trip_df, ['STATUS'])
    iso_col_p = get_col_by_index(ptw_df, 31, ['ISOLATION TYPE', 'ISOLATION'])
    iso_col_t = get_column(trip_df, ['ISOLATION TYPE', 'ISOLATION'])
    gss_col = get_column(ptw_df, ['GSS/PSS NAME', 'GSS NAME', 'PSS NAME', 'GSS'])
    outage_col = get_column(ptw_df, ['OUTAGE TYPE'])
    cons_col_p = get_col_by_index(ptw_df, 32, ['NO. OF CONS. AFFECTED', 'NO OF CONS', 'CONS. AFFECTED', 'CONSUMER', 'CUSTOMER', 'AFFECTED'])
    cons_col_t = get_col_by_index(trip_df, 31, ['TOTAL CONNECTED CONSUMERS', 'TOTAL CONNECTED', 'CONNECTED CONSUMERS', 'CONSUMER', 'CUSTOMER', 'AFFECTED'])
    mw_col_p = get_column(ptw_df, ['MW', 'LOAD', 'DEMAND'])
    mw_col_t = get_column(trip_df, ['MW', 'LOAD', 'DEMAND'])

    circles = sorted(ptw_df[circle_col_p].dropna().unique().tolist()) if circle_col_p and not ptw_df.empty else []
    ptw_json = df_to_json_safe(ptw_df)
    trip_json = df_to_json_safe(trip_df)

    col_cfg = {
        "p_circle": circle_col_p or "", "t_circle": circle_col_t or "",
        "p_div": div_col_p or "", "t_div": div_col_t or "",
        "p_status": status_col_p or "", "t_status": status_col_t or "",
        "p_iso": iso_col_p or "", "t_iso": iso_col_t or "",
        "p_gss": gss_col or "", "p_outage": outage_col or "",
        "p_cons": cons_col_p or "", "t_cons": cons_col_t or "",
        "p_mw": mw_col_p or "", "t_mw": mw_col_t or "",
        "p_shift": "shift", "t_shift": "shift",
        "p_hour": "hour", "t_hour": "hour", "t_dur": "duration_min",
    }
    col_cfg_json = json.dumps(col_cfg)

    circle_btns = '<button class="cbtn active" onclick="setCircle(this,\'ALL\')">ALL CIRCLES</button>\n'
    for c in circles:
        safe = c.replace("'", "\\'")
        circle_btns += f'<button class="cbtn" onclick="setCircle(this,\'{safe}\')">{c}</button>\n'

    last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    public_url = f"https://{REPO_NAME.split('/')[0]}.github.io/{REPO_NAME.split('/')[1]}/"

    ptw_show_cols = [c for c in ptw_df.columns if c not in ('shift','hour','datetime','start_dt','end_dt','duration_min')][:12]
    trip_show_cols = [c for c in trip_df.columns if c not in ('shift','hour','datetime','start_dt','end_dt')][:12]
    ptw_modal_cols = json.dumps(ptw_show_cols)
    trip_modal_cols = json.dumps(trip_show_cols)

    # Produce final HTML – reuse the same style as your original dashboard
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta http-equiv="refresh" content="120"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TPCODL Live Dashboard</title><script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:'Segoe UI',Arial,sans-serif;background:#eef2f7;color:#333}}header{{background:linear-gradient(90deg,#1a237e,#283593);color:#fff;padding:14px 26px;display:flex;align-items:center;gap:14px}}header h1{{font-size:1.4em}}header .sub{{font-size:.8em;opacity:.8;margin-top:3px}}.live-badge{{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7;border-radius:20px;padding:2px 10px;font-size:.72em;margin-left:8px}}.fbar{{background:#fff;padding:12px 22px;box-shadow:0 2px 6px rgba(0,0,0,.08);display:flex;flex-wrap:wrap;gap:10px;align-items:center;border-bottom:3px solid #e8eaf6}}.fbar label{{font-weight:700;font-size:.82em;color:#1a237e;margin-right:4px;white-space:nowrap}}.cbtn{{padding:5px 13px;border:2px solid #1a237e;border-radius:20px;background:#fff;color:#1a237e;cursor:pointer;font-size:.8em;font-weight:600;transition:all .15s}}.cbtn.active{{background:#1a237e;color:#fff}}.cbtn:hover{{background:#283593;color:#fff}}.fsel{{padding:6px 10px;border:2px solid #1a237e;border-radius:8px;font-size:.8em;color:#1a237e;cursor:pointer;outline:none;background:#fff}}.fsep{{width:1px;height:28px;background:#ddd;margin:0 4px}}.wrap{{max-width:1750px;margin:20px auto;padding:0 16px}}.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:22px}}.kpi{{background:#fff;border-radius:10px;padding:18px 14px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.09);border-top:4px solid;cursor:pointer;transition:transform .15s,box-shadow .15s;position:relative}}.kpi:hover{{transform:translateY(-3px);box-shadow:0 6px 18px rgba(0,0,0,.14)}}.kpi .click-hint{{position:absolute;top:6px;right:8px;font-size:.65em;color:#aaa;font-style:italic}}.kpi.blue{{border-color:#1565c0}} .kpi.red{{border-color:#c62828}}.kpi.green{{border-color:#2e7d32}} .kpi.orange{{border-color:#e65100}}.kpi.purple{{border-color:#6a1b9a}} .kpi.teal{{border-color:#00695c}}.kpi.brown{{border-color:#4e342e}} .kpi.lime{{border-color:#827717}}.kpi.pink{{border-color:#880e4f}}.kpi .val{{font-size:2em;font-weight:700;line-height:1.2}}.kpi .lbl{{font-size:.71em;color:#666;margin-top:5px;text-transform:uppercase;letter-spacing:.5px}}.chart-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:18px;margin-bottom:22px}}.card{{background:#fff;border-radius:10px;padding:14px;box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden}}.card h3{{font-size:.9em;color:#1a237e;margin-bottom:8px;padding-bottom:7px;border-bottom:2px solid #e8eaf6}}.modal-bg{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;align-items:flex-start;justify-content:center;padding-top:60px}}.modal-bg.open{{display:flex}}.modal{{background:#fff;border-radius:12px;width:92vw;max-width:1100px;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,.25)}}.modal-head{{background:#1a237e;color:#fff;padding:14px 20px;border-radius:12px 12px 0 0;display:flex;justify-content:space-between;align-items:center}}.modal-head h2{{font-size:1em;font-weight:700}}.modal-close{{background:none;border:none;color:#fff;font-size:1.4em;cursor:pointer;line-height:1;padding:0 4px}}.modal-body{{overflow:auto;padding:16px}}.modal-search{{margin-bottom:10px}}.modal-search input{{width:100%;padding:7px 12px;border:1px solid #ccc;border-radius:6px;font-size:.85em;outline:none}}.dtable{{width:100%;border-collapse:collapse;font-size:.8em}}.dtable th{{background:#e8eaf6;color:#1a237e;padding:7px 10px;text-align:left;position:sticky;top:0;white-space:nowrap}}.dtable td{{padding:6px 10px;border-bottom:1px solid #f0f0f0;white-space:nowrap}}.dtable tr:hover td{{background:#f5f7fa}}.modal-footer{{padding:10px 16px;border-top:1px solid #eee;font-size:.78em;color:#888;display:flex;justify-content:space-between;align-items:center}}footer{{text-align:center;padding:16px;color:#888;font-size:.78em}}
</style>
</head>
<body>
<header><div>⚡</div><div><h1>TPCODL LIVE DASHBOARD <span class="live-badge">● LIVE</span></h1><div class="sub">Auto-refreshes every 2 min &nbsp;|&nbsp; Last updated: {last_update}</div></div></header>
<div class="fbar"><label>🔵 Circle:</label>{circle_btns}<div class="fsep"></div><label>📂 Division:</label><select class="fsel" id="divSel" onchange="applyFilters()"><option value="ALL">All Divisions</option></select><div class="fsep"></div><label>🔌 Isolation Type:</label><select class="fsel" id="isoSel" onchange="applyFilters()"><option value="ALL">All Types</option></select></div>
<div class="wrap"><div class="kpi-grid"><div class="kpi blue" onclick="openModal('ptw_all')"><span class="click-hint">click to view ▼</span><div class="val" id="kTotalPTW">0</div><div class="lbl">Total PTWs</div></div><div class="kpi pink" onclick="openModal('ptw_live')"><span class="click-hint">click to view ▼</span><div class="val" id="kLivePTW">0</div><div class="lbl">🔴 Live PTWs (Issued)</div></div><div class="kpi red" onclick="openModal('trip_all')"><span class="click-hint">click to view ▼</span><div class="val" id="kTotalTrip">0</div><div class="lbl">Total Trippings</div></div><div class="kpi lime" onclick="openModal('trip_live')"><span class="click-hint">click to view ▼</span><div class="val" id="kLiveTrip">0</div><div class="lbl">🔴 Live Trippings (Live)</div></div><div class="kpi orange" onclick="openModal('consumers')"><span class="click-hint">click to view ▼</span><div class="val" id="kConsumers">0</div><div class="lbl">Consumers Affected (Live)</div></div><div class="kpi green" onclick="openModal('mw')"><span class="click-hint">click to view ▼</span><div class="val" id="kLoadMW">0</div><div class="lbl">Load Loss MW (Live)</div></div><div class="kpi teal" onclick="openModal('trip_all')"><span class="click-hint">click to view ▼</span><div class="val" id="kAvgDur">0 min</div><div class="lbl">Avg Trip Duration</div></div><div class="kpi brown" onclick="openModal('ptw_all')"><span class="click-hint">click to view ▼</span><div class="val" id="kPeakHr">N/A</div><div class="lbl">Peak Hour</div></div></div>
<div class="chart-grid"><div class="card"><h3>Hourly PTW Trend</h3><div id="cHourly" style="height:300px"></div></div><div class="card"><h3>Outage Type Trend over Hours</h3><div id="cOutageTrend" style="height:300px"></div></div></div>
<div class="chart-grid"><div class="card"><h3>Top 10 GSS by PTW</h3><div id="cGSS" style="height:360px"></div></div><div class="card"><h3>Top 5 Divisions by PTW</h3><div id="cDiv" style="height:360px"></div></div></div>
<div class="chart-grid"><div class="card"><h3>Outage Type Distribution</h3><div id="cPie" style="height:340px"></div></div><div class="card" style="display:flex;flex-direction:column;justify-content:center;align-items:center;gap:10px;padding:28px;"><div style="font-size:2.2em">📡</div><div style="font-weight:700;color:#1a237e">Live Dashboard</div><div style="color:#555;text-align:center;line-height:1.9;font-size:.88em">Data updates every <strong>5 minutes</strong><br>Page auto-reloads every <strong>2 minutes</strong><br><a href="{public_url}" style="color:#1565c0">{public_url}</a></div></div></div></div>
<footer>TPCODL Shift Dashboard &nbsp;|&nbsp; {last_update} &nbsp;|&nbsp; Auto-refreshes every 2 min</footer>
<div class="modal-bg" id="modalBg" onclick="bgClick(event)"><div class="modal"><div class="modal-head"><h2 id="modalTitle">Detail View</h2><button class="modal-close" onclick="closeModal()">✕</button></div><div class="modal-body"><div class="modal-search"><input type="text" id="modalSearch" placeholder="🔍 Search in table…" oninput="filterModal()"></div><div id="modalContent"></div></div><div class="modal-footer"><span id="modalCount"></span><span>Click outside or ✕ to close</span></div></div></div>
<script>
const PTW_RAW = {ptw_json};
const TRIP_RAW = {trip_json};
const C = {col_cfg_json};
const PTW_COLS = {ptw_modal_cols};
const TRIP_COLS = {trip_modal_cols};
let SEL_CIRCLE='ALL', _modalRows=[], _modalCols=[];
function byCircle(data,isTrip){{if(SEL_CIRCLE==='ALL')return data;const col=isTrip?C.t_circle:C.p_circle;return col?data.filter(r=>r[col]===SEL_CIRCLE):data;}}
function byDiv(data,isTrip){{const v=document.getElementById('divSel').value;if(v==='ALL')return data;const col=isTrip?C.t_div:C.p_div;return col?data.filter(r=>r[col]===v):data;}}
function byIso(data,isTrip){{const v=document.getElementById('isoSel').value;if(v==='ALL')return data;const col=isTrip?C.t_iso:C.p_iso;return col?data.filter(r=>r[col]===v):data;}}
function isIssued(r,isTrip){{const col=isTrip?C.t_status:C.p_status;if(!col)return false;const val=(r[col]||'').toString().toUpperCase().trim();return isTrip?val==='LIVE':val==='ISSUED';}}
function numSum(arr,col){{if(!col)return 0;return arr.reduce((s,r)=>s+(parseFloat(r[col])||0),0);}}
function fmt(n,d=0){{return n.toLocaleString('en-IN',{{maximumFractionDigits:d}});}}
function filteredPTW(){{return byIso(byDiv(byCircle(PTW_RAW,false),false),false);}}
function filteredTRIP(){{return byIso(byDiv(byCircle(TRIP_RAW,true),true),true);}}
function setCircle(btn,val){{SEL_CIRCLE=val;document.querySelectorAll('.cbtn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');rebuildDivDropdown();rebuildIsoDropdown();applyFilters();}}
function rebuildDivDropdown(){{const ptw=byCircle(PTW_RAW,false);const divs=[...new Set(ptw.map(r=>r[C.p_div]).filter(Boolean))].sort();const sel=document.getElementById('divSel');sel.innerHTML='<option value="ALL">All Divisions</option>';divs.forEach(d=>{{const o=document.createElement('option');o.value=d;o.text=d;sel.appendChild(o);}});}}
function rebuildIsoDropdown(){{const ptw=byDiv(byCircle(PTW_RAW,false),false);const types=[...new Set(ptw.map(r=>r[C.p_iso]).filter(Boolean))].sort();const sel=document.getElementById('isoSel');sel.innerHTML='<option value="ALL">All Types</option>';types.forEach(t=>{{const o=document.createElement('option');o.value=t;o.text=t;sel.appendChild(o);}});}}
function applyFilters(){{const ptw=filteredPTW(),trip=filteredTRIP();const livePTW=ptw.filter(r=>isIssued(r,false)),liveTrip=trip.filter(r=>isIssued(r,true));const totalPTW=ptw.length,totalTrip=trip.length,lPTWcnt=livePTW.length,lTripcnt=liveTrip.length,consumers=numSum(livePTW,C.p_cons)+numSum(liveTrip,C.t_cons),mw=numSum(livePTW,C.p_mw)+numSum(liveTrip,C.t_mw);let avgDur=0;if(C.t_dur&&trip.length>0){{const durs=trip.map(r=>parseFloat(r[C.t_dur])).filter(v=>!isNaN(v));avgDur=durs.length?durs.reduce((a,b)=>a+b,0)/durs.length:0;}}const hc={{}};ptw.forEach(r=>{{const h=r[C.p_hour];if(h!=null)hc[h]=(hc[h]||0)+1;}});let peakHr='N/A';const hEntries=Object.entries(hc);if(hEntries.length){{const top=hEntries.sort((a,b)=>b[1]-a[1])[0];peakHr=String(top[0]).padStart(2,'0')+':00 ('+top[1]+')';}}document.getElementById('kTotalPTW').textContent=fmt(totalPTW);document.getElementById('kLivePTW').textContent=fmt(lPTWcnt);document.getElementById('kTotalTrip').textContent=fmt(totalTrip);document.getElementById('kLiveTrip').textContent=fmt(lTripcnt);document.getElementById('kConsumers').textContent=fmt(consumers);document.getElementById('kLoadMW').textContent=fmt(mw,2);document.getElementById('kAvgDur').textContent=fmt(avgDur,1)+' min';document.getElementById('kPeakHr').textContent=peakHr;drawCharts(ptw,trip);}}
const COLORS=['#1565c0','#c62828','#2e7d32','#e65100','#6a1b9a','#00695c','#4e342e','#827717','#880e4f','#01579b'];
function countBy(arr,col){{const m={{}};arr.forEach(r=>{{const v=r[col]||'Unknown';m[v]=(m[v]||0)+1;}});return m;}}
function drawCharts(ptw,trip){{const hm={{}};ptw.forEach(r=>{{const h=r[C.p_hour];if(h!=null)hm[h]=(hm[h]||0)+1;}});const hk=Object.keys(hm).map(Number).sort((a,b)=>a-b);Plotly.react('cHourly',[{{type:'scatter',mode:'lines+markers',x:hk,y:hk.map(h=>hm[h]),line:{{color:'#1565c0',width:2}},marker:{{size:7}}}}],{{margin:{{t:10,b:40,l:40,r:10}},xaxis:{{title:'Hour'}},yaxis:{{title:'PTWs'}}}},{{responsive:true}});const traces=[];if(C.p_outage){{const types=[...new Set(ptw.map(r=>r[C.p_outage]).filter(Boolean))];types.forEach((ot,i)=>{{const om={{}};ptw.filter(r=>r[C.p_outage]===ot).forEach(r=>{{const h=r[C.p_hour];if(h!=null)om[h]=(om[h]||0)+1;}});const ok=Object.keys(om).map(Number).sort((a,b)=>a-b);traces.push({{type:'scatter',mode:'lines+markers',name:ot,x:ok,y:ok.map(h=>om[h]),marker:{{color:COLORS[i%COLORS.length]}}}});}});}}Plotly.react('cOutageTrend',traces.length?traces:[{{type:'scatter',x:[],y:[]}}],{{margin:{{t:10,b:40,l:40,r:10}},xaxis:{{title:'Hour'}},yaxis:{{title:'PTWs'}}}},{{responsive:true}});if(C.p_gss){{const gm=countBy(ptw,C.p_gss);const gs=Object.entries(gm).sort((a,b)=>b[1]-a[1]).slice(0,10);Plotly.react('cGSS',[{{type:'bar',orientation:'h',x:gs.map(e=>e[1]),y:gs.map(e=>e[0]),marker:{{color:'#1565c0'}},text:gs.map(e=>e[1]),textposition:'outside'}}],{{margin:{{t:10,l:190,r:50,b:40}},xaxis:{{title:'PTWs'}}}},{{responsive:true}});}}if(C.p_div){{const dm=countBy(ptw,C.p_div);const ds=Object.entries(dm).sort((a,b)=>b[1]-a[1]).slice(0,5);Plotly.react('cDiv',[{{type:'bar',orientation:'h',x:ds.map(e=>e[1]),y:ds.map(e=>e[0]),marker:{{color:'#2e7d32'}},text:ds.map(e=>e[1]),textposition:'outside'}}],{{margin:{{t:10,l:190,r:50,b:40}},xaxis:{{title:'PTWs'}}}},{{responsive:true}});}}if(C.p_outage){{const om=countBy(ptw,C.p_outage);Plotly.react('cPie',[{{type:'pie',labels:Object.keys(om),values:Object.values(om),marker:{{colors:COLORS}},textinfo:'label+percent'}}],{{margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true}});}}}}
function openModal(type){{const ptw=filteredPTW(),trip=filteredTRIP();let rows=[],cols=[],title='';if(type==='ptw_all'){{rows=ptw;cols=PTW_COLS;title=`All PTWs (${{ptw.length}} records)`;}}else if(type==='ptw_live'){{rows=ptw.filter(r=>isIssued(r,false));cols=PTW_COLS;title=`Live PTWs — STATUS=ISSUED (${{rows.length}} records)`;}}else if(type==='trip_all'){{rows=trip;cols=TRIP_COLS;title=`All Trippings (${{trip.length}} records)`;}}else if(type==='trip_live'){{rows=trip.filter(r=>isIssued(r,true));cols=TRIP_COLS;title=`Live Trippings — STATUS=LIVE (${{rows.length}} records)`;}}else if(type==='consumers'){{const lp=ptw.filter(r=>isIssued(r,false)),lt=trip.filter(r=>isIssued(r,true));rows=[...lp,...lt];cols=[...new Set([...PTW_COLS,...TRIP_COLS])].slice(0,12);title=`Consumers Affected — Live PTW + Live Tripping (${{rows.length}} records)`;}}else if(type==='mw'){{const lp=ptw.filter(r=>isIssued(r,false)),lt=trip.filter(r=>isIssued(r,true));rows=[...lp,...lt];cols=[...new Set([...PTW_COLS,...TRIP_COLS])].slice(0,12);title=`Load Loss (MW) — Live PTW + Live Tripping (${{rows.length}} records)`;}}_modalRows=rows;_modalCols=cols;document.getElementById('modalTitle').textContent=title;document.getElementById('modalSearch').value='';renderModalTable(rows,cols);document.getElementById('modalBg').classList.add('open');}}
function renderModalTable(rows,cols){{if(!rows.length){{document.getElementById('modalContent').innerHTML='<p style="padding:20px;color:#888">No records found.</p>';document.getElementById('modalCount').textContent='0 records';return;}}let th=cols.map(c=>`<th>${{c}}</th>`).join('');let tb=rows.map(r=>'<td>'+cols.map(c=>`<td>${{r[c]===null||r[c]===undefined?'':r[c]}}</td>`).join('')+'</tr>').join('');document.getElementById('modalContent').innerHTML=`<table class="dtable"><thead><tr>${{th}}</tr></thead><tbody>${{tb}}</tbody><table>`;document.getElementById('modalCount').textContent=`${{rows.length}} records`;}}
function filterModal(){{const q=document.getElementById('modalSearch').value.toLowerCase();const filtered=q?_modalRows.filter(r=>_modalCols.some(c=>(r[c]||'').toString().toLowerCase().includes(q))):_modalRows;renderModalTable(filtered,_modalCols);}}
function closeModal(){{document.getElementById('modalBg').classList.remove('open');}}
function bgClick(e){{if(e.target.id==='modalBg')closeModal();}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeModal();}});
rebuildDivDropdown();rebuildIsoDropdown();applyFilters();
</script>
</body>
</html>"""

    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html)
    log.info(f"Dashboard saved → {output_html}")

# ========== Main job ==========
def run_job():
    log.info("Starting TPCODL dashboard refresh")
    driver = get_driver()
    wait = WebDriverWait(driver, 90)
    try:
        if not login(driver, wait):
            log.error("Login failed – aborting")
            return
        # Clean old Excel files
        for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.xls*")):
            try: os.remove(f)
            except: pass
        ptw_file = trip_file = None
        for report in ["PTW 11KV", "Tripping 11KV"]:
            path = download_report(driver, wait, report)
            if path:
                if "PTW" in report:
                    ptw_file = path
                else:
                    trip_file = path
            else:
                log.error(f"Failed to download {report}")
        driver.quit()
        if ptw_file and trip_file:
            generate_dashboard(ptw_file, trip_file, "./index.html")
            log.info("Dashboard generated, ready to publish")
        else:
            log.error("Missing report files – skipping publish")
    except Exception as e:
        log.error(f"Job failed: {e}")
        try: driver.quit()
        except: pass

def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    prefs = {"download.default_directory": os.path.abspath(DOWNLOAD_DIR),
             "download.prompt_for_download": False}
    opts.add_experimental_option("prefs", prefs)
    # In GitHub Actions, chromedriver is at /usr/bin/chromedriver
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=opts)

if __name__ == "__main__":
    run_job()
