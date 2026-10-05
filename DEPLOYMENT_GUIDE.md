# 🚀 Free Production Deployment Guide: Nagpur Estates AI Voice CRM

This guide provides step-by-step instructions to deploy the **Nagpur Estates AI Voice CRM** 100% freely using cloud providers that offer free tiers.

---

## 📋 Required Free Cloud Accounts & API Keys

Before deploying, ensure you have the following free keys:

### 1. Google AI Studio (Gemini 3.1 Live & Embeddings)
- Go to [Google AI Studio](https://aistudio.google.com/)
- Click **"Get API Key"** and create a new key.
- Key name: `GOOGLE_API_KEY`
- *Cost: Free tier available with generous rate limits.*

### 2. LiveKit Cloud (Telephony WebRTC & SIP Trunking)
- Go to [LiveKit Cloud](https://cloud.livekit.io/)
- Create a free project.
- Copy from Project Settings -> Keys:
  - `LIVEKIT_URL` (e.g. `wss://your-project.livekit.cloud`)
  - `LIVEKIT_API_KEY`
  - `LIVEKIT_API_SECRET`
- In **SIP** section, create an Outbound Trunk (connected to your SIP provider like Twilio/Telnyx/Vobiz or LiveKit SIP):
  - `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`
- *Cost: Free tier gives 50 GB/month bandwidth and 100 concurrent participants free.*

---

## 🔐 Security & Admin Login Credentials

The CRM is protected with a secure single login screen and token-based authentication.

| Setting | Default Value | Notes |
| :--- | :--- | :--- |
| **Admin Email** | `admin@nagpurestates.com` | Configurable via `ADMIN_EMAIL` |
| **Admin Password** | `admin123` | Configurable via `ADMIN_PASSWORD` |
| **Session Secret** | Auto-fallback | Set `AUTH_SECRET_KEY` in environment for production |

---

## 🌐 Deployment Options (100% Free)

---

### Option 1: Deploy on Render.com (Recommended - 1 Click Docker/Python)

Render offers **750 free instance hours per month** for web services.

1. **Push your code to GitHub / GitLab**.
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **"New +"** -> **"Web Service"**.
4. Connect your GitHub repository.
5. Configure the service:
   - **Name**: `nagpur-estates-crm`
   - **Region**: Choose closest to your users (e.g., Singapore or Frankfurt).
   - **Branch**: `main`
   - **Runtime**: **Docker** (Render will automatically use the `Dockerfile`)
   - **Instance Type**: **Free**
6. Scroll down to **Environment Variables** and add:
   ```env
   GOOGLE_API_KEY=your_google_api_key_here
   LIVEKIT_URL=wss://your_project.livekit.cloud
   LIVEKIT_API_KEY=your_livekit_api_key
   LIVEKIT_API_SECRET=your_livekit_api_secret
   LIVEKIT_SIP_OUTBOUND_TRUNK_ID=your_trunk_id
   AGENT_NAME=ai-calling-agent
   AUTH_SECRET_KEY=change-this-to-a-random-32-char-string
   ADMIN_EMAIL=admin@nagpurestates.com
   ADMIN_PASSWORD=YourStrongPasswordHere!
   RUN_AGENT_IN_BACKGROUND=true
   ```
7. Click **"Create Web Service"**.
8. Render will build the container and provide your live HTTPS URL (e.g. `https://nagpur-estates-crm.onrender.com`).

---

### Option 2: Deploy on Hugging Face Spaces (Free Docker 16 GB RAM / 2 vCPU 24/7)

Hugging Face Spaces provides free Docker hosting with **2 vCPUs and 16 GB of RAM** with no automatic cold shutdown if traffic is steady.

1. Create a free account on [Hugging Face](https://huggingface.co/).
2. Go to **Spaces** -> **"Create new Space"**.
3. Choose:
   - **Space Name**: `nagpur-estates-crm`
   - **License**: `MIT` or `Open Source`
   - **SDK**: **Docker** -> **Blank**
   - **Space Hardware**: **CPU basic (Free, 2 vCPU, 16 GB RAM)**
4. In your Space's **Settings** tab -> **Variables and secrets**, add:
   - `GOOGLE_API_KEY`
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`
   - `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`
   - `AUTH_SECRET_KEY`
   - `ADMIN_EMAIL`
   - `ADMIN_PASSWORD`
   - `RUN_AGENT_IN_BACKGROUND=true`
5. Clone your space repository locally and push your project files to it:
   ```bash
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/nagpur-estates-crm
   git push space main
   ```
6. Hugging Face will automatically build and launch the application.

---

### Option 3: Deploy on Railway.app / Koyeb / Fly.io

1. **Railway**:
   - Create a project -> **Deploy from GitHub repo**.
   - Add environment variables in the **Variables** tab.
   - Railway automatically detects the `Dockerfile` and runs `start.sh`.

2. **Koyeb**:
   - Create an app -> **GitHub Repository** -> Free nano tier ($0/mo).
   - Set environment variables and deploy.

---

## 🧪 Local Testing & Verification

To run locally on your development machine:

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Fill in your `GOOGLE_API_KEY` and `LIVEKIT_*` keys.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the CRM server:
   ```bash
   python main.py
   ```
5. (Optional) In a second terminal, run the LiveKit agent worker:
   ```bash
   python agent.py start
   ```
   *(Or set `RUN_AGENT_IN_BACKGROUND=true` in `.env` so `main.py` starts both automatically!)*
6. Open your browser at `http://localhost:8000`.
7. Sign in with:
   - **Email**: `admin@nagpurestates.com`
   - **Password**: `admin123`

---

## 🔒 Production Checklist

- [x] Secured API with signed HMAC-SHA256 bearer tokens.
- [x] Built responsive Single Page Login Interface with password visibility toggle & session persistence.
- [x] Added user profile & 1-click logout in sidebar footer.
- [x] Pinned and verified all Python dependencies in `requirements.txt`.
- [x] Built production `Dockerfile` with system libraries (`ffmpeg`, `curl`, `build-essential`).
- [x] Created `start.sh` entrypoint supporting dual FastAPI + Voice Agent worker execution on a single free container.
- [x] Tested SQLite WAL mode with concurrency and thread safety.
