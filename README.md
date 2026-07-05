# 💎 Jewel Manager Pro

Full-stack jewellery business management system built with Streamlit.

## Features
- 📋 **Estimation builder** — gold, diamond (with Google Sheet price lookup), making, hallmark, GST
- 💎 **Diamond auto-pricing** — reads your Google Sheet (one tab per shape) and auto-fills price by sieve + quality
- 🖼️ **Image uploads** — item photo, customer reference, CAD design via Cloudinary
- 📄 **PDF quotes** — branded with your logo
- 📦 **Order tracking** — status pipeline, search, filter, export CSV
- 🏠 **Dashboard** — KPIs, revenue charts, overdue alerts
- 🍃 **MongoDB** — all orders, prices, settings stored in Atlas

---

## Project Structure

```
jewel_manager/
│
├── app.py                      ← Entry point (run this)
│
├── config/
│   ├── __init__.py
│   └── settings.py             ← All constants, GOLD_PURITY, CSS, col aliases
│
├── services/
│   ├── __init__.py
│   ├── database.py             ← MongoDB CRUD (orders, prices, settings)
│   ├── cloudinary.py           ← Image upload via Cloudinary REST API
│   ├── diamond_sheet.py        ← Google Sheets diamond price reader
│   └── pdf_generator.py        ← ReportLab PDF quote builder
│
├── components/
│   ├── __init__.py
│   ├── sidebar.py              ← Sidebar nav + price controls + sheet loader
│   └── image_uploader.py       ← 3-slot image upload + gallery widgets
│
├── pages/
│   ├── __init__.py
│   ├── dashboard.py            ← KPI cards, charts, recent orders
│   ├── estimation.py           ← Full quote builder
│   ├── orders.py               ← Order management
│   └── settings.py             ← Business profile, logo, secrets guide
│
├── .streamlit/
│   └── secrets.toml.template   ← Copy → secrets.toml and fill in values
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Quick Start (VS Code / Local)

### 1. Clone / open project
```bash
cd jewel_manager
```

### 2. Create virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up secrets
```bash
# Create the secrets file
mkdir -p .streamlit
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```
Then open `.streamlit/secrets.toml` and fill in all your credentials.

### 5. Run the app
```bash
streamlit run app.py
```
Opens at **http://localhost:8501** 🚀

---

## Credentials You Need

| Credential | Where to get it |
|---|---|
| `mongodb_uri` | MongoDB Atlas → Connect → Drivers |
| `cloudinary_*` | cloudinary.com → Dashboard |
| `diamond_sheet_id` | From your Google Sheet URL |
| `gcp_service_account` | Google Cloud Console → Service Account → JSON key |

> After creating the service account, **share your diamond price Google Sheet** with the `client_email` as **Editor**.

---

## Diamond Price Sheet Format

Each sheet tab = one diamond shape (Round, Princess, Oval, etc.)

| Seive | SizeMM | SizeRound | Carat Weight | VVS EF (INR) | VVS VS EF | VS FG (INR) |
|-------|--------|-----------|--------------|--------------|-----------|-------------|
| 8/0   | 1.00   | ...       | 0.006        | 2,100        | 1,800     | 1,500       |
| 9/0   | 1.10   | ...       | 0.007        | 2,400        | ...       | ...         |

The app reads sieve sizes and prices automatically. Select shape → sieve → quality and the price auto-fills. ✅

---

## MongoDB Collections (auto-created)

| Collection | Created when | Contents |
|---|---|---|
| `orders` | First order saved | All order data + image URLs |
| `prices` | First price save | Gold 24K rate + Diamond rate |
| `settings` | First settings save | Business name, etc. |

No setup needed — collections are created automatically on first write.
