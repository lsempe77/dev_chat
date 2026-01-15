# DevChat Frontend

Next.js 15 application for the DevChat research workbench.

## Quick Start

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Environment Variables

Create `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
```

## Key Features

- **Chat Interface** - RAG-powered Q&A with citations
- **PDF Viewer** - Inline viewer with citation highlighting
- **Dashboard** - Document management, metadata editing
- **Auth** - Supabase authentication

## Deployment

Deployed on Vercel: https://dev-chat-frontend.vercel.app/

## Stack

- Next.js 15 (App Router)
- Tailwind CSS + shadcn/ui
- Supabase Auth
- Vercel AI SDK
