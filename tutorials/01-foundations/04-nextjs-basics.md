# Post 4: Next.js Frontend Basics

**Part 4 of 50** | ⏱️ 60 minutes | [← Previous](03-fastapi-basics.md) | [Next: Database Setup →](05-database-setup.md)

---

## 🎯 What You'll Learn

- Next.js 15 App Router fundamentals
- React Server Components vs Client Components
- File-based routing
- Data fetching patterns
- Real DevChat frontend examples

---

## 📖 What is Next.js?

**Next.js** is a React framework that adds:
- 🗂️ **File-based routing**: `app/chat/page.tsx` → `/chat`
- 🚀 **Server-side rendering**: Better performance and SEO
- 📦 **API routes**: Backend endpoints alongside frontend
- ⚡ **Automatic code splitting**: Only load what's needed

### Why Next.js for DevChat?

```typescript
// Traditional React SPA (loads everything upfront)
// ❌ Slow initial load
// ❌ Poor SEO
// ❌ All JS runs in browser

// Next.js (loads progressively)
// ✅ Fast initial load
// ✅ Great SEO
// ✅ Server-rendered content
// ✅ Client-only when needed
```

---

## 🗂️ File-Based Routing

Next.js 15 uses the **App Router** in the `app/` directory.

### Basic Routes

```
app/
├── page.tsx              → /
├── about/
│   └── page.tsx          → /about
├── projects/
│   ├── page.tsx          → /projects
│   └── [id]/
│       └── page.tsx      → /projects/:id
└── api/
    └── chat/
        └── route.ts      → /api/chat
```

### DevChat Structure

```
frontend/src/app/
├── page.tsx                    → / (homepage)
├── layout.tsx                  → Root layout
├── chat/
│   ├── page.tsx                → /chat (chat interface)
│   └── [projectId]/
│       └── page.tsx            → /chat/:projectId
├── projects/
│   ├── page.tsx                → /projects (list)
│   ├── new/
│   │   └── page.tsx            → /projects/new
│   └── [id]/
│       ├── page.tsx            → /projects/:id
│       └── documents/
│           └── page.tsx        → /projects/:id/documents
└── admin/
    ├── page.tsx                → /admin (dashboard)
    └── users/
        └── page.tsx            → /admin/users
```

---

## 🎨 Server vs Client Components

### Understanding the Traditional SPA Problem

Traditional React apps (like Create React App) work like this:

```
1. User visits example.com
2. Browser downloads HUGE JavaScript bundle (2MB+)
3. JavaScript runs and builds the entire page
4. User can finally interact

Result: Slow initial load, poor SEO
```

Next.js 15 solves this with **Server Components**.

### Server Components: The Default

**What happens:**

```
1. User requests /projects
2. Next.js runs component on server
3. Fetches data from database (fast - no network latency)
4. Renders HTML on server
5. Sends ready-to-display HTML to browser
6. User sees page immediately!

Result: Fast, SEO-friendly, less JavaScript
```

**Example:**

```typescript
// app/projects/page.tsx
// This is a SERVER COMPONENT (default)
// It runs on the server, NOT in the browser!

import { getProjects } from '@/lib/api'

export default async function ProjectsPage() {
  // This database call happens on the SERVER
  // The browser never sees your database credentials
  const projects = await getProjects()
  
  // This HTML is built on the server
  return (
    <div>
      <h1>Projects</h1>
      {projects.map(p => (
        <div key={p.id}>{p.name}</div>
      ))}
    </div>
  )
}
```

**What the browser receives:** Just plain HTML! No database calls, no JavaScript needed for this component.

### Client Components: When You Need Interactivity

Server Components can't handle:
- Button clicks
- Form inputs
- State (`useState`)
- Browser APIs (localStorage, etc.)

For these, you need **Client Components**:

```typescript
// components/ChatInput.tsx
'use client'  // ← This tells Next.js: "run this in the browser"

import { useState } from 'react'

export default function ChatInput() {
  // useState only works in Client Components
  const [query, setQuery] = useState('')
  
  const handleSubmit = () => {
    // User interaction = needs client-side JavaScript
    fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ query })
    })
  }
  
  return (
    <input 
      value={query}
      onChange={(e) => setQuery(e.target.value)}  // Interactive!
      onSubmit={handleSubmit}
    />
  )
}
```

### The Rule of Thumb

**Use Server Component (default) when:**
- ✅ Fetching data
- ✅ Displaying static content
- ✅ No user interaction needed
- ✅ Want fast initial load

**Use Client Component (`'use client'`) when:**
- ✅ Need `useState`, `useEffect`
- ✅ Handling clicks, forms, inputs
- ✅ Using browser APIs
- ✅ Need event listeners

**Pro tip:** Keep Client Components small! Wrap only the interactive parts:

```typescript
// ❌ Bad: Entire page is client-side
'use client'
export default function Page() {
  const [query, setQuery] = useState('')
  return (
    <div>
      <Header />  {/* Doesn't need to be client-side! */}
      <Sidebar />  {/* Doesn't need to be client-side! */}
      <ChatInput value={query} onChange={setQuery} />  {/* Only this needs it */}
    </div>
  )
}

// ✅ Good: Only interactive part is client-side
export default function Page() {  // Server Component
  return (
    <div>
      <Header />  {/* Server Component - fast! */}
      <Sidebar />  {/* Server Component - fast! */}
      <ChatInput />  {/* Client Component - interactive! */}
    </div>
  )
}
```

---

## 🎯 DevChat Homepage

From `frontend/src/app/page.tsx`:

```typescript
import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function HomePage() {
  return (
    <div className="container mx-auto px-4 py-16">
      <div className="max-w-3xl mx-auto text-center">
        <h1 className="text-5xl font-bold mb-6">
          Research Powered by AI
        </h1>
        
        <p className="text-xl text-gray-600 mb-8">
          DevChat helps you explore academic literature with 
          AI-powered search and synthesis.
        </p>
        
        <div className="flex gap-4 justify-center">
          <Link href="/chat">
            <Button size="lg">
              Start Chatting
            </Button>
          </Link>
          
          <Link href="/projects/new">
            <Button size="lg" variant="outline">
              Create Project
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
```

**Key features:**
- Server component (no state needed)
- `Link` for client-side navigation
- shadcn/ui components (`Button`)
- Tailwind CSS for styling

---

## 🔄 Data Fetching

### Server-Side Fetching

```typescript
// app/projects/[id]/page.tsx

import { notFound } from 'next/navigation'
import { getProject } from '@/lib/api'

export default async function ProjectPage({
  params
}: {
  params: { id: string }
}) {
  const project = await getProject(params.id)
  
  if (!project) {
    notFound()  // Shows 404 page
  }
  
  return (
    <div>
      <h1>{project.name}</h1>
      <p>{project.description}</p>
    </div>
  )
}
```

### Client-Side Fetching

```typescript
'use client'

import { useState, useEffect } from 'react'

export default function ProjectStats({ projectId }: { projectId: string }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  
  useEffect(() => {
    fetch(`/api/projects/${projectId}/stats`)
      .then(r => r.json())
      .then(data => {
        setStats(data)
        setLoading(false)
      })
  }, [projectId])
  
  if (loading) return <div>Loading...</div>
  
  return (
    <div>
      <p>Documents: {stats.document_count}</p>
      <p>Queries: {stats.query_count}</p>
    </div>
  )
}
```

---

## 💬 DevChat Chat Interface

From `frontend/src/app/chat/page.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { ChatMessage } from '@/components/ChatMessage'
import { ChatInput } from '@/components/ChatInput'
import { useChatStream } from '@/lib/hooks/useChatStream'

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const { sendMessage, isLoading } = useChatStream()
  
  const handleSend = async (query: string) => {
    // Add user message
    setMessages(prev => [...prev, {
      role: 'user',
      content: query
    }])
    
    // Stream AI response
    const response = await sendMessage(query)
    
    setMessages(prev => [...prev, {
      role: 'assistant',
      content: response.answer,
      citations: response.citations
    }])
  }
  
  return (
    <div className="flex flex-col h-screen">
      {/* Chat history */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
      </div>
      
      {/* Input area */}
      <div className="border-t p-4">
        <ChatInput 
          onSend={handleSend}
          disabled={isLoading}
        />
      </div>
    </div>
  )
}
```

### ChatMessage Component

From `frontend/src/components/ChatMessage.tsx`:

```typescript
'use client'

import { cn } from '@/lib/utils'
import { CitationLink } from './CitationLink'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
}

export function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  
  return (
    <div className={cn(
      "mb-4 p-4 rounded-lg",
      isUser ? "bg-blue-50 ml-12" : "bg-gray-50 mr-12"
    )}>
      <div className="font-semibold mb-2">
        {isUser ? 'You' : 'DevChat'}
      </div>
      
      <div className="prose prose-sm max-w-none">
        {message.content}
      </div>
      
      {/* Show citations for assistant messages */}
      {!isUser && message.citations && (
        <div className="mt-4 pt-4 border-t">
          <p className="text-sm font-semibold mb-2">Sources:</p>
          <div className="space-y-2">
            {message.citations.map((cite, i) => (
              <CitationLink key={i} citation={cite} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

---

## 🎨 Styling with Tailwind

DevChat uses **Tailwind CSS** for styling.

### Utility Classes

```typescript
// Flexbox
<div className="flex items-center justify-between">

// Spacing
<div className="p-4 m-2 gap-4">
  // p-4 = padding: 1rem
  // m-2 = margin: 0.5rem
  // gap-4 = gap: 1rem

// Colors
<div className="bg-blue-500 text-white border-gray-300">

// Responsive
<div className="w-full md:w-1/2 lg:w-1/3">
  // w-full on mobile
  // w-1/2 on tablets (md)
  // w-1/3 on desktop (lg)
```

### shadcn/ui Components

DevChat uses **shadcn/ui** for pre-built components.

```typescript
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'

<Card className="p-6">
  <Input 
    type="text" 
    placeholder="Search..."
    className="mb-4"
  />
  <Button>Submit</Button>
</Card>
```

---

## 🔗 API Client

From `frontend/src/lib/api.ts`:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  
  if (!res.ok) {
    const error = await res.text()
    throw new Error(error)
  }
  
  return res.json()
}

export const api = {
  // Projects
  getProjects: () => 
    apiRequest<Project[]>('/api/projects'),
  
  getProject: (id: string) =>
    apiRequest<Project>(`/api/projects/${id}`),
  
  createProject: (data: CreateProjectRequest) =>
    apiRequest<Project>('/api/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  // Chat
  chat: (query: string, projectId: string) =>
    apiRequest<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ query, project_id: projectId }),
    }),
}
```

---

## 🎯 Real Example: Project Creation

From `frontend/src/app/projects/new/page.tsx`:

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'

export default function NewProjectPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    name: '',
    description: '',
  })
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    
    try {
      const project = await api.createProject(form)
      router.push(`/projects/${project.id}`)
    } catch (error) {
      alert(`Error: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="container max-w-2xl mx-auto py-8">
      <h1 className="text-3xl font-bold mb-6">
        Create New Project
      </h1>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block mb-2 font-medium">
            Project Name
          </label>
          <Input
            value={form.name}
            onChange={(e) => setForm(prev => ({
              ...prev,
              name: e.target.value
            }))}
            placeholder="My Research Project"
            required
          />
        </div>
        
        <div>
          <label className="block mb-2 font-medium">
            Description (optional)
          </label>
          <Textarea
            value={form.description}
            onChange={(e) => setForm(prev => ({
              ...prev,
              description: e.target.value
            }))}
            placeholder="What is this project about?"
            rows={4}
          />
        </div>
        
        <Button 
          type="submit" 
          disabled={loading || !form.name}
          className="w-full"
        >
          {loading ? 'Creating...' : 'Create Project'}
        </Button>
      </form>
    </div>
  )
}
```

**What's happening:**
1. Client component for interactivity
2. Form state with `useState`
3. API call on submit
4. Navigate to new project with `useRouter`
5. Loading/error states
6. shadcn/ui components for UI

---

## ✅ Knowledge Check

1. What's the difference between Server and Client Components?
2. How do you make a Client Component?
3. What does the file `app/chat/[id]/page.tsx` create?
4. When should you use `'use client'`?
5. How do you navigate programmatically in Next.js?

<details>
<summary>Answers</summary>

1. Server Components run on server (default), Client Components run in browser
2. Add `'use client'` at the top of the file
3. A dynamic route at `/chat/:id`
4. When you need state, effects, or browser APIs
5. Use `useRouter()` hook: `router.push('/path')`

</details>

---

**Next:** [Post 5: Database Setup →](05-database-setup.md)

Learn how to set up Supabase PostgreSQL with Row-Level Security.

---

[🏠 Back to Index](../README.md) | [← Previous](03-fastapi-basics.md) | [Next: Database Setup →](05-database-setup.md)
