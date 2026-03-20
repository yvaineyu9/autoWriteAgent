# Claude Workflows Web UI

## Backend

```bash
cd web-ui/backend
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic
python run.py
```

## Frontend

```bash
cd web-ui/frontend
npm install
npm run dev
```

默认地址：
- Backend: `http://127.0.0.1:8765`
- Frontend: `http://127.0.0.1:5173`
